"""Fetch pages politely and extract their main text (methodology v1 extraction).

Usage: uv run pipeline/fetch_pages.py PAGES.csv OUT_DIR [--extract-only]

PAGES.csv needs `page_id` and `url` columns. Writes OUT_DIR/html/<page_id>.html, OUT_DIR/text/<page_id>.md
and OUT_DIR/fetch.csv (status, final URL, <html lang>, canonical URL, title, text length).
Hosts are fetched in parallel, one request at a time per host, honoring robots.txt.
"""

import csv
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import html2text
import httpx
from bs4 import BeautifulSoup

USER_AGENT = "BiasIndexBot/0.1 (+https://thebiasindex.com/bot)"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"}  # Zoho geo-targets its language
DELAY_S = 1.0
# Stop fetching a host after this many blocked responses in a row (Pipedrive answers 429 to every bot request).
BLOCKED_STATUSES = {403, 429, 503}
MAX_CONSECUTIVE_BLOCKS = 3
MAX_BYTES = 5_000_000

LANG = re.compile(r"<html[^>]*\blang=[\"']?([A-Za-z-]+)", re.IGNORECASE)
CANONICAL = re.compile(r"<link[^>]+rel=[\"']?canonical[\"']?[^>]*>", re.IGNORECASE)
HREF = re.compile(r"href=[\"']([^\"']+)", re.IGNORECASE)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# Page chrome removed before extraction. Kept deliberately simple so the rule fits in one sentence on the
# methodology page. (trafilatura was tried first and dropped whole comparison tables and testimonials.)
CHROME = ["script", "style", "noscript", "template", "svg", "iframe", "form", "nav", "footer",
          "[role=navigation]", "[role=contentinfo]", "[aria-hidden=true]"]
# Only stripped when falling back to <body>: inside <main>/<article>, <header> holds the page title.
BODY_CHROME = ["header", "[role=banner]"]
MIN_MAIN_CHARS = 1000


def content_root(soup):
    """<main>, else the largest <article>, else <body>. Chosen before stripping, because broken markup
    can nest the content inside the site header (ClickUp's blog)."""
    for candidates in (soup.find_all("main"), soup.find_all("article")):
        if candidates:
            best = max(candidates, key=lambda element: len(element.get_text(strip=True)))
            if len(best.get_text(strip=True)) >= MIN_MAIN_CHARS:
                return best, False
    return soup.body or soup, True


def extract_text(html):
    """The page's <main> (or largest <article>, or <body>) without navigation, footer, scripts and forms,
    as Markdown."""
    soup = BeautifulSoup(html, "lxml")
    root, is_body = content_root(soup)
    for element in root.select(", ".join(CHROME + (BODY_CHROME if is_body else []))):
        element.decompose()
    converter = html2text.HTML2Text()
    converter.ignore_links = True
    converter.ignore_images = True
    converter.body_width = 0
    text = converter.handle(str(root))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def page_metadata(html, url):
    lang = LANG.search(html[:5000])
    canonical = CANONICAL.search(html)
    href = HREF.search(canonical.group(0)) if canonical else None
    title = TITLE.search(html)
    return {
        "lang": lang.group(1) if lang else "",
        "canonical_url": urljoin(url, href.group(1)) if href else "",
        "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else "",
    }


def robots_for(client, host):
    parser = RobotFileParser()
    try:
        response = client.get(f"https://{host}/robots.txt")
        parser.parse(response.text.splitlines() if response.status_code == 200 else [])
    except httpx.HTTPError:
        parser.parse([])
    return parser


def fetch_host(client, host, rows, out_dir):
    robots = robots_for(client, host)
    delay = max(DELAY_S, robots.crawl_delay(USER_AGENT) or 0)
    results, blocked = [], 0
    for row in rows:
        result = {"page_id": row["page_id"], "url": row["url"], "status": "", "final_url": "", "lang": "",
                  "canonical_url": "", "title": "", "text_chars": 0, "error": ""}
        if blocked >= MAX_CONSECUTIVE_BLOCKS:
            result["error"] = "host blocked the crawler"
            results.append(result)
            continue
        if not robots.can_fetch(USER_AGENT, row["url"]):
            result["error"] = "disallowed by robots.txt"
            results.append(result)
            continue
        time.sleep(delay)
        try:
            response = client.get(row["url"])
            if response.status_code in BLOCKED_STATUSES:
                blocked += 1
                result.update(status=response.status_code, error="blocked")
                results.append(result)
                continue
            blocked = 0
            html = response.content[:MAX_BYTES].decode(response.encoding or "utf-8", errors="replace")
            text = extract_text(html)
            with open(os.path.join(out_dir, "html", f"{row['page_id']}.html"), "w", encoding="utf-8") as handle:
                handle.write(html)
            with open(os.path.join(out_dir, "text", f"{row['page_id']}.md"), "w", encoding="utf-8") as handle:
                handle.write(text)
            result.update(page_metadata(html, str(response.url)), status=response.status_code,
                          final_url=str(response.url), text_chars=len(text))
        except httpx.HTTPError as error:
            result["error"] = f"{type(error).__name__}: {error}"[:200]
        results.append(result)
    return results


def main():
    pages_path, out_dir = sys.argv[1], sys.argv[2]
    for sub in ("html", "text"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    if "--extract-only" in sys.argv:
        reextract(out_dir)
        return
    with open(pages_path) as handle:
        rows = list(csv.DictReader(handle))
    by_host = defaultdict(list)
    for row in rows:
        by_host[urlparse(row["url"]).netloc].append(row)

    started = time.monotonic()
    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client, \
            ThreadPoolExecutor(min(32, len(by_host))) as pool:
        chunks = list(pool.map(lambda item: fetch_host(client, item[0], item[1], out_dir), by_host.items()))
    results = sorted((r for chunk in chunks for r in chunk), key=lambda r: r["page_id"])

    with open(os.path.join(out_dir, "fetch.csv"), "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    failed = [r for r in results if r["error"] or r["status"] != 200]
    print(f"{len(results)} pages, {len(by_host)} hosts, {time.monotonic() - started:.0f}s, {len(failed)} problems")
    for r in failed:
        print(f"  {r['page_id']} {r['status']} {r['error']} {r['url']}")


def reextract(out_dir):
    """Re-run text extraction on already fetched HTML, e.g. after changing the extraction rules."""
    for name in sorted(os.listdir(os.path.join(out_dir, "html"))):
        with open(os.path.join(out_dir, "html", name), encoding="utf-8") as handle:
            text = extract_text(handle.read())
        with open(os.path.join(out_dir, "text", name.replace(".html", ".md")), "w", encoding="utf-8") as handle:
            handle.write(text)


if __name__ == "__main__":
    main()
