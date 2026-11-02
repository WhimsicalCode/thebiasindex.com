"""Which monitored companies each compare page is aimed at or lists, from its URL, title and headings. No AI.

Usage: uv run pipeline/mentions.py [--db data/bias_index.sqlite] [--headings-from data/raw/live]

- about: the page is aimed at the company. One of its product names sits next to "vs", "alternative(s)",
  "compare"... in the URL path or a part of the title ("Miro vs Whimsical", /whimsical-alternatives). The page's red
  flags count for it on the site.
- listed: the company is one entry in the page's list. A heading starts with its name ("3. Whimsical", "Whimsical:
  best for speed"). Counted, without the page's red flags, which may be about other entries. Headings that are
  other articles' titles ("Monday vs ClickUp: Which Should...") and the site's template (an unnumbered heading on a
  quarter or more of the company's compare pages, like Taskade's related-tool cards) aren't entries.
- The body of the page is never read: there, names are mostly navigation, integrations and customer stories.

Names are the `product_names` in pipeline/domains.yml. `not_mentions` lists other products that contain one
("Resource Guru" for Guru), and a name two companies share is skipped. A company's own pages never mention it.

The table is rebuilt from the database in seconds, so changing a rule costs nothing: run.py rebuilds it after every
run, and every rebuild first checks CASES. Headings are stored by run.py when a page is fetched; --headings-from
fills them in from saved page text (for a database written before headings were stored).
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import companies  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SCHEMA = """
create table if not exists mentions (
    url text not null references pages(url),
    company_slug text not null references companies(slug),
    mentioned_slug text not null references companies(slug),
    kind text not null,
    matched_in text not null,
    matched_text text not null,
    primary key (url, mentioned_slug)
);
create index if not exists mentions_mentioned on mentions(mentioned_slug);
"""

KEYWORDS = {"vs", "versus", "alternative", "alternatives", "compare", "compared", "comparison", "comparisons",
            "competitor", "competitors"}
# Only before the name: "switch from Asana" is about Asana, "make the switch" is not about Make.
LEFT_KEYWORDS = {"switch", "switching", "migrate", "migrating"}
WINDOW = 2  # words between the name and the keyword, at most WINDOW - 1
TITLE_PARTS = re.compile(r"\s+[|·–—-]\s+|\|")
WORD = re.compile(r"[A-Za-z0-9][\w'’.+&-]*")

HEADING = re.compile(r"^#{2,4}\s+(.+?)\s*#*\s*$", re.MULTILINE)
MAX_HEADING_CHARS = 100
# "2. Notion", "1.Typeform", "3) Notion", "#4 Notion", "Alternative #3: Notion", "No. 5: Notion"
NUMBERED = re.compile(r"^(?:\\?#?\d{1,3}\\?[.):](?:\s+|(?=[A-Z]))|#\d{1,3}\s*[.:]?\s+"
                      r"|(?:[A-Z][\w-]*\s){1,2}#?\d{1,3}\s*[:.]\s+|No\.\s*\d{1,3}\s*[:.]?\s+)")
SEPARATOR = re.compile(r"^\s*(?:[—–:|(,]|-+\s)")
ARTICLE_TITLE = re.compile(r"\b(?:vs\.?|versus)\s", re.IGNORECASE)
TEMPLATE_MIN_PAGES, TEMPLATE_SHARE = 5, 0.25


def list_headings(text):
    """The page's headings that could be list entries: numbered, with a separator, or a few words long."""
    headings = []
    for heading in HEADING.findall(text):
        heading = re.sub(r"\\(.)", r"\1", re.sub(r"[*_`\u200b-\u200d\ufeff]+", "", heading)).strip()  # "2\. Notion"
        if heading and len(heading) <= MAX_HEADING_CHARS and (
                NUMBERED.match(heading) or re.search(r"[—–:|(]| - ", heading) or len(heading.split()) <= 3):
            headings.append(heading)
    return list(dict.fromkeys(headings))


def slug_words(text):
    return [word for word in re.split(r"[^a-z0-9]+", text.lower()) if word]


def forms(name):
    """How a name may be written in a title or heading: as in domains.yml, capitalized ("monday", "Monday"), or
    without its inner capitals ("HubSpot", "Hubspot")."""
    return {name, name[:1].upper() + name[1:], name[:1].upper() + name[1:].lower()}


def load_names(entries):
    """[(company domain, name, title/heading regex, URL words, the company's not_mentions)], longest names first."""
    owners = defaultdict(set)
    for entry in entries:
        for name in entry["product_names"]:
            owners[name.lower()].add(entry["domain"])
    names = []
    for entry in entries:
        for name in entry["product_names"]:
            if len(owners[name.lower()]) > 1:
                continue
            pattern = re.compile(r"(?<![\w.@/-])(?:" + "|".join(map(re.escape, forms(name))) + r")(?![\w-]|\.\w)")
            names.append((entry["domain"], name, pattern, slug_words(name), tuple(entry.get("not_mentions", []))))
    names.sort(key=lambda item: -len(item[1]))
    return names


def keyword_near(before, after):
    near_before = {word.lower().strip(".:,") for word in before[-WINDOW:]}
    near_after = {word.lower().strip(".:,") for word in after[:WINDOW]}
    return bool((near_before | near_after) & KEYWORDS or near_before & LEFT_KEYWORDS)


def url_words(url, excluded):
    """The words of the URL path, without excluded phrases and without "vs" in "vs code" (the editor)."""
    tokens = slug_words(url.split("://", 1)[-1].partition("/")[2].split("?")[0])
    tokens = [token for i, token in enumerate(tokens)
              if not (token == "vs" and i + 1 < len(tokens) and tokens[i + 1] == "code")]
    for phrase in excluded:
        size = len(phrase)
        tokens = [token for i, token in enumerate(tokens)
                  if not any(tokens[j:j + size] == phrase for j in range(max(0, i - size + 1), i + 1))]
    return tokens


def in_url(tokens, words):
    size = len(words)
    return any(tokens[i:i + size] == words and keyword_near(tokens[:i], tokens[i + size:])
               for i in range(len(tokens) - size + 1))


def title_parts(title, excluded):
    parts = []
    for part in TITLE_PARTS.split(title or ""):
        for phrase in excluded:
            part = re.sub(re.escape(phrase), " ", part, flags=re.IGNORECASE)
        parts.append(part)
    return parts


def in_title(parts, pattern):
    for part in parts:
        for match in pattern.finditer(part):
            if keyword_near(WORD.findall(part[:match.start()]), WORD.findall(part[match.end():])):
                return part.strip()
    return None


def in_heading(heading, name):
    """The heading starts with the name (any capitalization), and is a list entry: numbered ("3. Railway with a
    CLI"), or the name stands alone or is followed by a separator, after up to two words ("Notion AI (best for...)")."""
    numbered = NUMBERED.match(heading)
    rest = heading[numbered.end():] if numbered else heading
    if not rest.lower().startswith(name.lower()) or re.match(r"[\w.-]", rest[len(name):len(name) + 1]):
        return False
    after = rest[len(name):]
    if numbered or not after.strip() or SEPARATOR.match(after):
        return True
    extra = re.match(r"(?:\s+[A-Z0-9][\w.+-]*){1,2}", after)
    return bool(extra and SEPARATOR.match(after[extra.end():]))


def match_page(publisher, url, title, headings, names, template=frozenset()):
    """{mentioned domain: (kind, matched_in, matched_text)} for one page. `template` holds the publisher's template
    headings."""
    headings = [h for h in headings if h not in template and not ARTICLE_TITLE.search(h)]
    views = {}

    def view(excluded):
        """The page's URL words, title parts and headings without a company's not_mentions ("Figma Make" for Make)."""
        if excluded not in views:
            tokens = url_words(url, [slug_words(phrase) for phrase in excluded])
            views[excluded] = (tokens, " ".join(tokens), title_parts(title, excluded),
                               [h for h in headings if not any(p.lower() in h.lower() for p in excluded)])
        return views[excluded]

    found = {}
    for domain, name, pattern, words, excluded in names:
        if domain == publisher or domain in found:
            continue
        tokens, text, parts, _ = view(excluded)
        if " ".join(words) in text and in_url(tokens, words):
            found[domain] = ("about", "url", url.split("://", 1)[-1].partition("/")[2])
        elif (part := in_title(parts, pattern)) is not None:
            found[domain] = ("about", "title", part)
    for domain, name, _, _, excluded in names:
        if domain == publisher or domain in found:
            continue
        heading = next((h for h in view(excluded)[3] if name[1:].lower() in h.lower() and in_heading(h, name)), None)
        if heading:
            found[domain] = ("listed", "heading", heading)
    return found


# Checked on every rebuild, so a rule change can't quietly break them: (publisher, url, title, headings, expected).
CASES = [
    ("miro.com", "https://miro.com/al/whimsical-alternatives/", "Top 5 Whimsical Alternatives To Switch To in 2026",
     [], {"whimsical.com": "about"}),
    ("miro.com", "https://miro.com/al/lucidchart-alternatives/", "Top 5 Lucidchart Alternatives",
     ["Alternative #3: Whimsical", "Why teams switch"], {"lucid.co": "about", "whimsical.com": "listed"}),
    ("miro.com", "https://miro.com/compare/miro-vs-notion/", "Miro vs Notion Comparison | 2026 | Miro", [],
     {"notion.com": "about"}),
    ("clickup.com", "https://clickup.com/blog/monday-vs-asana-vs-clickup-small-business-pricing/",
     "Monday vs. Asana vs. ClickUp Pricing: Which Is Best Value?", [], {"monday.com": "about", "asana.com": "about"}),
    ("clickup.com", "https://clickup.com/blog/linear-alternatives/", "6 Best Linear Alternatives for Product Teams",
     ["2. Notion AI (Best for turning research into specs)", "3. Asana", "Make: best for automation",
      "#5 Craft -- Best for Apple Users", "3. FullStory", "4. Railway with a CLI-first deployment experience"],
     {"linear.app": "about", "notion.com": "listed", "asana.com": "listed", "make.com": "listed", "craft.do": "listed",
      "fullstory.com": "listed", "railway.com": "listed"}),
    ("miro.com", "https://miro.com/compare/miro-vs-visio/", "Miro vs Visio | Make a powerful choice | 2025 | Miro",
     ["How to Make an Interactive Flipbook", "Ready to Make The Switch From Outlook?"], {}),
    ("aha.io", "https://www.aha.io/blog/aha-builder-vs-figma-make-best-ai-app-builder-prototyping",
     "Aha! Builder vs. Figma Make: How To Choose the Best AI App Builder", [], {"figma.com": "about"}),
    ("zoho.com", "https://www.zoho.com/survey/survey-sparrow-alternatives.html", "10 alternatives to Survey Sparrow",
     ["1.Typeform", "2. Hubspot Forms", "Pricing"], {"typeform.com": "listed", "hubspot.com": "listed"}),
    ("monday.com", "https://monday.com/blog/project-management/asana-alternatives/",
     "Alternatives to Asana for Small Teams", [], {"asana.com": "about"}),
    ("clickup.com", "https://clickup.com/blog/resource-guru-alternatives/",
     "We Tested 11 Resource Guru Alternatives for 2026", [], {}),
    ("clickup.com", "https://clickup.com/compare/vs/pitch-avatar",
     "Pitch Avatar vs. ClickUp™ — The #1 Pitch Avatar Alternative is ClickUp", [], {}),
    ("visme.co", "https://visme.co/blog/interactive-flipbook-alternatives/", "Flipbook Alternatives",
     ["Advantage #1: Non-Linear Navigation", "Pricing", "Features"], {}),
    ("hiverhq.com", "https://hiverhq.com/blog/helpscout-vs-intercom", "Help Scout vs Intercom: Feature Comparison",
     ["Jira Service Management vs. Freshdesk: Which Is Right for Your Team?"],
     {"helpscout.com": "about", "intercom.com": "about"}),
    ("loom.com", "https://www.loom.com/comparison/loom-vs-vidyard",
     "Loom vs. Vidyard: Which Is the Best Teamwork Tool? | Loom", [], {}),
    ("clickup.com", "https://clickup.com/blog/linting-and-formatting-with-eslint-in-vs-code/",
     "Linting in VS Code", [], {}),
]


def check_cases(names):
    problems = []
    for publisher, url, title, headings, expected in CASES:
        found = {domain: kind for domain, (kind, _, _) in
                 match_page(publisher, url, title, headings, names).items()}
        if found != expected:
            problems.append(f"{url}: expected {expected}, got {found}")
    if problems:
        raise SystemExit("mentions.py rules broke a known case:\n  " + "\n  ".join(problems))


def ensure_schema(db):
    db.executescript(SCHEMA)
    if "headings" not in {row[1] for row in db.execute("pragma table_info(pages)")}:
        db.execute("alter table pages add column headings text")


def fill_headings(db, raw_dir):
    """Headings for compare pages stored before run.py saved them, from the page text saved under raw_dir."""
    filled = 0
    for url, page_id in db.execute("select url, page_id from pages where page_type = 'competitor_comparison' "
                                   "and headings is null").fetchall():
        path = Path(raw_dir) / "text" / f"{page_id}.md"
        if path.exists():
            db.execute("update pages set headings = ? where url = ?",
                       (json.dumps(list_headings(path.read_text(encoding="utf-8"))), url))
            filled += 1
    return filled


def template_headings(rows):
    """{publisher: unnumbered headings on a quarter or more of its compare pages}: related-article cards, FAQs."""
    pages, seen = Counter(), defaultdict(Counter)
    for publisher, _, _, headings in rows:
        pages[publisher] += 1
        seen[publisher].update(h for h in set(headings) if not NUMBERED.match(h))
    return {publisher: frozenset(h for h, n in counts.items()
                                 if n >= TEMPLATE_MIN_PAGES and n >= TEMPLATE_SHARE * pages[publisher])
            for publisher, counts in seen.items()}


def rebuild(db, entries=None):
    """Recompute every compare page's mentions. Returns (pages, about, listed)."""
    ensure_schema(db)
    names = load_names(entries or companies.load())
    check_cases(names)
    rows = [(publisher, url, title, json.loads(headings or "[]")) for publisher, url, title, headings in db.execute(
        "select company_slug, url, title, headings from pages where page_type = 'competitor_comparison'")]
    template = template_headings(rows)
    db.execute("delete from mentions")
    counts = {"about": 0, "listed": 0}
    for publisher, url, title, headings in rows:
        found = match_page(publisher, url, title, headings, names, template.get(publisher, frozenset()))
        for domain, (kind, matched_in, text) in found.items():
            db.execute("insert into mentions values (?, ?, ?, ?, ?, ?)",
                       (url, publisher, domain, kind, matched_in, text))
            counts[kind] += 1
    db.commit()
    return len(rows), counts["about"], counts["listed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", default=str(REPO / "data" / "bias_index.sqlite"))
    parser.add_argument("--headings-from", default="", help="Saved page text (run.py --raw) to fill in headings")
    args = parser.parse_args()
    db = sqlite3.connect(args.db)
    ensure_schema(db)
    if args.headings_from:
        print(f"filled headings for {fill_headings(db, args.headings_from)} compare pages")
    pages, about, listed = rebuild(db)
    print(f"{pages:,} compare pages: {about:,} about a company, {listed:,} listing one")


if __name__ == "__main__":
    main()
