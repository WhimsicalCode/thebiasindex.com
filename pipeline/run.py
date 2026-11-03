"""Weekly run: discover comparison pages, fetch them, score them with Luna, and store everything in SQLite.

Usage: uv run pipeline/run.py [--db data/bias_index.sqlite] [--raw data/raw/live] [--companies Miro,Notion]
                              [--max-pages-per-company N] [--workers 8]

- Companies come from pipeline/domains.yml, validated by companies.py; each is keyed by its domain. Candidate URLs
  come from their sitemaps (discover.py), minus user-generated content, non-English paths and URLs on hosts the
  company doesn't own. A company with no readable sitemap is marked no_sitemap, unless its homepage could be read:
  then it publishes no compare pages we can find (if it had some, its navigation or footer would link to them).
- --max-pages-per-company keeps a run small: a stable sample (by URL hash) so the same pages come back each week.
  The number of candidates found is always stored, so the site can say "40 of 1,496 pages scored".
- Pages are fetched politely (fetch_pages.py): one request per second per host, robots.txt honored, hosts that keep
  blocking the crawler are marked unreachable.
- A page is only sent to Luna when its text or the methodology version changed since the last run.
- Non-English pages (by <html lang>), near-empty pages and pages that redirect off the company's domains are
  stored but never scored. A page read before that only fails this week (blocked, rate-limited) keeps its score.
- --skip-read-within-days 6 leaves out the companies read fine in the last 6 days: a quick run for new companies and
  the ones we couldn't read.
- Last, mentions.py records which companies each compare page is aimed at or lists, from its URL, title and
  headings (no AI).

Needs OPENAI_API_KEY (see credentials.py). Raw HTML and text stay under --raw and are not committed.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import classify  # noqa: E402
import companies  # noqa: E402
import discover  # noqa: E402
import fetch_pages  # noqa: E402
import mentions  # noqa: E402
from credentials import openai_api_key  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MIN_TEXT_CHARS = 200
# Short text shared word for word by many of a company's pages is its site template, not the page: DigitalOcean's
# tutorials load their article with JavaScript, so without it every one of them reads as the same footer.
TEMPLATE_MAX_CHARS, TEMPLATE_MIN_PAGES = 1000, 5
# Opting out in robots.txt is for good, unlike a block or a rate limit.
OPTED_OUT = "disallowed by robots.txt"
# Cleared when a page is skipped for good (gone, not English, redirects away...), so it stops counting with an old
# score. A page that only fails this week (blocked, rate-limited, timing out) keeps its data, like a page we ran out
# of time for.
CLASSIFICATION = ("page_type", "page_type_confidence", "p_best_at_everything", "p_no_honest_exit",
                  "p_no_admitted_weakness", "p_vague_attacks", "p_uneven_scrutiny", "score", "unclear",
                  "methodology", "model", "classified_at")
# A company whose every page fails with one of these is marked unreachable ("crawler blocked" on the site), unless
# pages read before keep its scores; a robots.txt opt-out always counts: we don't score what we may not read.
BLOCKED_ERRORS = ("blocked", "host blocked the crawler", "disallowed by robots.txt")

SCHEMA = """
create table if not exists companies (
    slug text primary key,
    company text not null,
    hosts text not null,
    aliases text not null default '[]',
    category text,
    monitored integer not null default 1,
    product_names text not null,
    candidates integer not null default 0,
    sampled integer not null default 0,
    status text not null default 'ok',
    updated_at text
);
create table if not exists pages (
    url text primary key,
    page_id text not null,
    company_slug text not null references companies(slug),
    title text,
    lang text,
    http_status integer,
    final_url text,
    text_hash text,
    text_chars integer,
    first_seen text,
    last_seen text,
    skip_reason text,
    page_type text,
    page_type_confidence real,
    p_best_at_everything real,
    p_no_honest_exit real,
    p_no_admitted_weakness real,
    p_vague_attacks real,
    p_uneven_scrutiny real,
    score integer,
    unclear integer,
    methodology text,
    model text,
    classified_at text
);
-- "Current pages" (seen in the company's latest run) are looked up by company and last_seen everywhere: the export,
-- mentions.csv and the site's build. Without it, each lookup scans the whole table.
create index if not exists pages_company_seen on pages(company_slug, last_seen);
create table if not exists runs (
    run_id integer primary key autoincrement,
    started_at text not null,
    finished_at text,
    methodology text,
    model text,
    companies integer,
    pages_fetched integer,
    pages_classified integer,
    pages_reused integer,
    input_tokens integer
);
"""


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def page_id_for(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def stable_sample(urls, limit):
    """The same pages week after week: order by URL hash and keep the first `limit`."""
    ordered = sorted(urls, key=lambda url: hashlib.sha1(url.encode()).hexdigest())
    return ordered if not limit else ordered[:limit]


def discover_entry(client, entry):
    """Candidate URLs for one company, how many sitemap URLs were read in total, and whether its homepage was read."""
    user_content = re.compile(discover.USER_CONTENT)
    total, urls = 0, set()
    for name in entry["hosts"]:
        _, found = discover.discover_host(client, name, entry.get("sitemaps"))
        total += len(found)
        urls |= {url for url in found
                 if discover.CANDIDATE.search(urlparse(url).path) and discover.is_english_path(url)}
    homepage = discover.homepage_links(client, entry)
    from_homepage = discover.merge_links(urls, homepage)
    urls |= from_homepage | set(entry.get("extra_urls", []))
    foreign = {url for url in urls if not companies.owns(entry, url)}
    urls = sorted(url for url in urls - foreign if not user_content.search(url))
    dropped = f" dropped {len(foreign)} on other hosts" if foreign else ""
    linked = f" ({len(from_homepage)} from the homepage)" if from_homepage else ""
    print(f"{entry['company']:<14} sitemap urls={total:<8} candidates={len(urls)}{linked}{dropped}", flush=True)
    return total, urls, homepage is not None


def discover_all(entries):
    """Per company: (sitemap URLs read, filtered candidate URLs, whether its homepage was read)."""
    with httpx.Client(headers=fetch_pages.HEADERS, timeout=20, follow_redirects=True) as client, \
            ThreadPoolExecutor(min(32, len(entries))) as pool:
        found = list(pool.map(lambda entry: discover_entry(client, entry), entries))
    return {entry["company"]: result for entry, result in zip(entries, found)}


def fetch_all(pages, raw_dir, reuse_since=None, budget_s=None):
    for sub in ("html", "text"):
        (raw_dir / sub).mkdir(parents=True, exist_ok=True)
    by_host = defaultdict(list)
    for page in pages:
        by_host[urlparse(page["url"]).netloc].append(page)
    with httpx.Client(headers=fetch_pages.HEADERS, timeout=20, follow_redirects=True) as client, \
            ThreadPoolExecutor(min(32, max(1, len(by_host)))) as pool:
        chunks = list(pool.map(
            lambda item: fetch_pages.fetch_host(client, item[0], item[1], str(raw_dir), reuse_since, budget_s),
            by_host.items()))
    return {result["page_id"]: result for chunk in chunks for result in chunk}


def is_english(lang):
    return not lang or lang.lower().startswith("en")


def mostly_non_latin(text):
    """Pages that declare English but are written in Japanese, Korean... (postman.com/jp/)."""
    letters = [c for c in text[:5000] if c.isalpha()]
    other = sum(1 for c in letters if not unicodedata.name(c, "").startswith("LATIN"))
    return bool(letters) and other / len(letters) > 0.3


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", default=str(REPO / "data" / "bias_index.sqlite"))
    parser.add_argument("--raw", default=str(REPO / "data" / "raw" / "live"))
    parser.add_argument("--companies", default="", help="Comma-separated company names (default: all)")
    parser.add_argument("--max-pages-per-company", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--host-budget-minutes", type=float, default=60,
                        help="Most time spent fetching one site per run; pages left over keep their previous scores")
    parser.add_argument("--skip-read-within-days", type=float, default=0,
                        help="Skip companies read fine in the last N days (their data stays as it is): a run for new "
                             "companies and the ones we couldn't read")
    parser.add_argument("--reuse-fetched-since", default="",
                        help="ISO time: reuse pages saved under --raw since then instead of fetching them again "
                             "(to resume an interrupted run)")
    args = parser.parse_args()

    api_key = openai_api_key()
    raw_dir = Path(args.raw)
    entries = companies.load()
    only = {name.strip() for name in args.companies.split(",") if name.strip()}
    entries = [entry for entry in entries if not only or entry["company"] in only]

    db = sqlite3.connect(args.db)
    db.executescript(SCHEMA)
    mentions.ensure_schema(db)
    columns = {row[1] for row in db.execute("pragma table_info(companies)")}
    if "aliases" not in columns:
        db.execute("alter table companies add column aliases text not null default '[]'")
    if "category" not in columns:
        db.execute("alter table companies add column category text")
    if "monitored" not in columns:
        db.execute("alter table companies add column monitored integer not null default 1")
    if not args.companies:
        # Companies dropped from domains.yml leave the site; their pages stay in the database as history.
        listed = [entry["domain"] for entry in entries]
        db.execute(f"update companies set monitored = slug in ({','.join('?' * len(listed))})", listed)
    # Names and categories come from domains.yml, also for companies this run doesn't read.
    for entry in entries:
        db.execute("update companies set company = ?, aliases = ?, category = ?, product_names = ? where slug = ?",
                   (entry["company"], json.dumps(entry.get("aliases", [])), entry["category"],
                    json.dumps(entry["product_names"]), entry["domain"]))
    listed_entries = entries
    if args.skip_read_within_days:
        since = (datetime.now(UTC) - timedelta(days=args.skip_read_within_days)).isoformat(timespec="seconds")
        fresh = {slug for (slug,) in db.execute(
            "select slug from companies where status = 'ok' and updated_at >= ?", (since,))}
        entries = [entry for entry in entries if entry["domain"] not in fresh]
        print(f"skipping {len(fresh)} companies read fine since {since[:16]}", flush=True)
    started = now()
    run_id = db.execute("insert into runs (started_at, methodology, model) values (?, ?, ?)",
                        (started, classify.METHODOLOGY_VERSION, classify.MODEL)).lastrowid
    db.commit()

    print(f"discovering candidates for {len(entries)} companies...", flush=True)
    candidates = discover_all(entries)

    pages, company_for = [], {}
    for entry in entries:
        slug = entry["domain"]
        sitemap_urls, urls, read_homepage = candidates[entry["company"]]
        # Pages found in earlier weeks are checked again even when this week's sitemap leaves them out (some sitemaps
        # vary by visitor location). A page drops out once it's gone (a 404 or 410) or excluded since it was first seen.
        excluded = re.compile(discover.USER_CONTENT)
        known = {url for url, status in db.execute("select url, http_status from pages where company_slug = ?", (slug,))
                 if status not in (404, 410) and companies.owns(entry, url) and not excluded.search(url)
                 and not discover.ASSET.search(urlparse(url).path) and url == url.strip()}
        if known - set(urls):
            added = len(known - set(urls))
            print(f"{entry['company']:<14} +{added} known pages not in this week's sitemap", flush=True)
        urls = discover.dedupe_regional(set(urls) | known)
        sample = stable_sample(urls, args.max_pages_per_company)
        status = "no_sitemap" if sitemap_urls == 0 and not urls and not read_homepage else "ok"
        db.execute(
            """insert into companies (slug, company, hosts, aliases, category, product_names, candidates, sampled,
                 status, updated_at)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               on conflict(slug) do update set company = excluded.company, hosts = excluded.hosts,
                 aliases = excluded.aliases, category = excluded.category,
                 product_names = excluded.product_names, candidates = excluded.candidates,
                 sampled = excluded.sampled, status = excluded.status, updated_at = excluded.updated_at""",
            (slug, entry["company"], json.dumps(entry["hosts"]), json.dumps(entry.get("aliases", [])),
             entry["category"], json.dumps(entry["product_names"]),
             len(urls), len(sample), status, started),
        )
        for url in sample:
            page = {"page_id": page_id_for(url), "url": url, "company": entry["company"]}
            pages.append(page)
            company_for[page["page_id"]] = (slug, entry)
    db.commit()

    print(f"fetching {len(pages)} pages...", flush=True)
    fetch_started = time.monotonic()
    reuse_since = datetime.fromisoformat(args.reuse_fetched_since).timestamp() if args.reuse_fetched_since else None
    fetched = fetch_all(pages, raw_dir, reuse_since, args.host_budget_minutes * 60)
    print(f"fetched in {time.monotonic() - fetch_started:.0f}s", flush=True)

    # Hosts where every page was blocked: mark the company unreachable, unless pages read before keep its scores
    # (Pipedrive rate-limits some weeks). Opting out in robots.txt always counts.
    blocked_by_company = defaultdict(lambda: [0, 0, 0])
    for page in pages:
        counts = blocked_by_company[company_for[page["page_id"]][0]]
        counts[1] += 1
        counts[0] += fetched[page["page_id"]]["error"] in BLOCKED_ERRORS
        counts[2] += fetched[page["page_id"]]["error"] == OPTED_OUT
    for slug, (blocked, total, opted_out) in blocked_by_company.items():
        read_before = db.execute("select 1 from pages where company_slug = ? and page_type is not null limit 1",
                                 (slug,)).fetchone()
        if total and blocked == total and (opted_out or not read_before):
            db.execute("update companies set status = 'unreachable' where slug = ?", (slug,))

    shared = Counter()
    for page in pages:
        result = fetched[page["page_id"]]
        text_path = raw_dir / "text" / f"{page['page_id']}.md"
        if not result["error"] and result["status"] == 200 and text_path.exists():
            text = text_path.read_text(encoding="utf-8")
            if MIN_TEXT_CHARS <= len(text) < TEMPLATE_MAX_CHARS:
                shared[(company_for[page["page_id"]][0], text)] += 1

    products = classify.load_products()
    to_classify, reused = [], 0
    for page in pages:
        result = fetched[page["page_id"]]
        slug, entry = company_for[page["page_id"]]
        if result["error"] == fetch_pages.NOT_REACHED:
            # Out of time for this site: a known page stays current with its previous data and score.
            updated = db.execute("update pages set last_seen = ? where url = ?", (started, page["url"])).rowcount
            if not updated:
                db.execute("insert into pages (url, page_id, company_slug, first_seen, last_seen, skip_reason) "
                           "values (?, ?, ?, ?, ?, ?)",
                           (page["url"], page["page_id"], slug, started, started, "not checked yet"))
            continue
        status = result["status"] or 0
        failed = (result["error"] and result["error"] != OPTED_OUT) or status in fetch_pages.BLOCKED_STATUSES \
            or status >= 500
        read_before = db.execute("select 1 from pages where url = ? and page_type is not null", (page["url"],))
        if failed and read_before.fetchone():
            # Read before, failing this week: it stays current with its previous data and score.
            db.execute("update pages set last_seen = ? where url = ?", (started, page["url"]))
            continue
        text_path = raw_dir / "text" / f"{page['page_id']}.md"
        text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
        text_hash = hashlib.sha1(text.encode()).hexdigest() if text else None
        skip = None
        if result["error"] or result["status"] != 200:
            skip = result["error"] or f"http {result['status']}"
        elif result["final_url"] and not companies.owns(entry, result["final_url"]):
            skip = f"redirects off the company's domains ({urlparse(result['final_url']).hostname})"
        elif not is_english(result["lang"]):
            skip = f"not English ({result['lang']})"
        elif mostly_non_latin(text):
            skip = "not English (text)"
        elif len(text) < MIN_TEXT_CHARS:
            skip = "no readable text"
        elif (copies := shared[(slug, text)]) >= TEMPLATE_MIN_PAGES:
            skip = f"only the site's template (the same text on {copies} pages)"

        previous = db.execute("select text_hash, methodology, first_seen from pages where url = ?",
                              (page["url"],)).fetchone()
        db.execute(
            """insert into pages (url, page_id, company_slug, title, lang, http_status, final_url, text_hash,
                 text_chars, first_seen, last_seen, skip_reason, headings)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               on conflict(url) do update set title = excluded.title, lang = excluded.lang,
                 http_status = excluded.http_status, final_url = excluded.final_url,
                 text_hash = excluded.text_hash, text_chars = excluded.text_chars, last_seen = excluded.last_seen,
                 skip_reason = excluded.skip_reason, headings = excluded.headings""",
            (page["url"], page["page_id"], slug, result["title"], result["lang"], result["status"] or None,
             result["final_url"], text_hash, len(text), previous[2] if previous else started, started, skip,
             None if skip else json.dumps(mentions.list_headings(text))),
        )
        if skip:
            db.execute(f"update pages set {', '.join(f'{column} = null' for column in CLASSIFICATION)} where url = ?",
                       (page["url"],))
            continue
        if previous and previous[0] == text_hash and previous[1] == classify.METHODOLOGY_VERSION:
            reused += 1
            continue
        state = {
            "publisher": entry["company"],
            "publisher_products": products.get(entry["company"], [entry["company"]]),
            "note": "The page is published on the publisher's own website.",
            "url": page["url"],
            "title": result["title"],
            "page_text": text[:classify.MAX_TEXT_CHARS],
        }
        to_classify.append((page, state))
    db.commit()

    print(f"classifying {len(to_classify)} pages ({reused} unchanged, reused)...", flush=True)

    def run_one(item):
        page, state = item
        try:
            body, _ = classify.classify_page(api_client, api_key, state)
            return page, body, ""
        except Exception as error:  # keep the run going; the page is retried next week
            return page, {}, str(error)[:200]

    input_tokens = classified = 0
    with httpx.Client(timeout=90) as api_client, ThreadPoolExecutor(args.workers) as pool:
        for page, body, error in pool.map(run_one, to_classify):
            if error:
                print(f"  classify failed for {page['url']}: {error}")
                continue
            answers = {answer["name"]: answer for answer in body.get("answers", [])}
            missing = [name for name in classify.QUESTIONS if "probability" not in answers.get(name, {})]
            if "page_type" not in answers or missing:
                print(f"  classify failed for {page['url']}: incomplete answers {body.get('answers')}"[:400])
                continue
            page_type = answers.get("page_type", {})
            flags, unclear = classify.score(answers)
            probabilities = [classify.red_flag_probability(answers, name) for name in classify.QUESTIONS]
            db.execute(
                """update pages set page_type = ?, page_type_confidence = ?, p_best_at_everything = ?,
                     p_no_honest_exit = ?, p_no_admitted_weakness = ?, p_vague_attacks = ?, p_uneven_scrutiny = ?,
                     score = ?, unclear = ?, methodology = ?, model = ?, classified_at = ?
                   where url = ?""",
                (page_type.get("choice"), page_type.get("confidence"), *probabilities, flags, unclear,
                 classify.METHODOLOGY_VERSION, classify.MODEL, now(), page["url"]),
            )
            input_tokens += (body.get("usage") or {}).get("input_tokens", 0)
            classified += 1
            if classified % 200 == 0:
                db.commit()  # a crash late in a long run keeps what was already scored
    # Headings are only used to find the companies a compare page lists.
    db.execute("update pages set headings = null where page_type is not 'competitor_comparison'")
    db.commit()
    compare_pages, about, listed = mentions.rebuild(db, listed_entries if not only else None)
    print(f"mentions: {compare_pages:,} compare pages, {about:,} about a company, {listed:,} listing one", flush=True)
    db.execute(
        """update runs set finished_at = ?, companies = ?, pages_fetched = ?, pages_classified = ?,
             pages_reused = ?, input_tokens = ? where run_id = ?""",
        (now(), len(entries), len(pages), classified, reused, input_tokens, run_id),
    )
    db.commit()
    db.close()
    print(f"done: {classified} classified, {reused} reused, {input_tokens:,} input tokens "
          f"(~${input_tokens / 1e6 * 0.10:.2f}); database {os.path.relpath(args.db)}")


if __name__ == "__main__":
    main()
