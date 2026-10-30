"""Find candidate comparison pages in each monitored company's sitemaps.

Usage: uv run pipeline/discover.py OUT.csv [COMPANY ...]

Hosts are crawled in parallel, one request at a time per host. Only URLs are read here, no pages:
the URL-pattern prefilter described in docs/METHODOLOGY.md ("Which pages are checked").
"""

import csv
import gzip
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import companies as company_list
import httpx

USER_AGENT = "BiasIndexBot/0.1 (+https://thebiasindex.com/bot)"
DELAY_S = 1.0
MAX_SITEMAPS = 200

# User-generated content and template galleries on vendor domains: not the vendor's own comparisons, never scored.
USER_CONTENT = (r"figma\.com/community/|coda\.io/@|airtable\.com/universe/|consensus\.app/questions/"
                r"|framer\.com/marketplace/|/templates/|smartdraw\.com/comparisons/examples/|prezi\.com/p/|scite\.ai/reports/|padlet\.com/[^/]+/(?=[a-z0-9]*[0-9])[a-z0-9]{10,}/?$")

CANDIDATE = re.compile(r"-vs-|/vs/|-vs$|versus|alternative|compare|comparison|switch-to|/switch(?:/|$)",
                       re.IGNORECASE)
# Non-English language codes seen in localized paths and sitemap names. A whitelist, because short
# path segments are often not locales at all (Miro's alternatives pages live under /al/).
LANGUAGES = set(
    "ar bg cs da de el es et fa fi fr he hi hr hu id it ja ko lt lv ms nb nl no pl pt ro ru sk sl sr sv "
    "th tr uk vi zh".split()
)
# A whole path segment such as de, pt-br or zh_hant, anywhere in the path (/blog/de/..., /hc/es/...).
LOCALE_SEGMENT = re.compile(r"^([a-z]{2})(?:[-_][a-z]{2,4})?$", re.IGNORECASE)
# sitemap_de.xml, sitemap-zh_hant.xml, .../de-de.xml (but .../en-us.xml is English).
LOCALE_SITEMAP = re.compile(r"(?:^|[_/.-])([a-z]{2})(?:[-_][a-z]{2,4})?\.xml(?:\.gz)?$", re.IGNORECASE)
LOC = re.compile(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\]\s]+)", re.IGNORECASE)


def is_english_path(url):
    for segment in urlparse(url).path.split("/"):
        match = LOCALE_SEGMENT.match(segment)
        if match and match.group(1).lower() in LANGUAGES:
            return False
    return True


def is_foreign_sitemap(url):
    match = LOCALE_SITEMAP.search(urlparse(url).path)
    return bool(match) and match.group(1).lower() in LANGUAGES


class Host:
    """A per-host client that waits DELAY_S between requests."""

    def __init__(self, client):
        self.client = client
        self.last = 0.0

    def get(self, url):
        wait = self.last + DELAY_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            return self.client.get(url)
        except httpx.HTTPError:
            return None
        finally:
            self.last = time.monotonic()


def body_text(response):
    content = response.content
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    return content.decode("utf-8", errors="replace")


def sitemap_roots(host, name):
    response = host.get(f"https://{name}/robots.txt")
    roots = []
    if response is not None and response.status_code == 200:
        roots = [line.split(":", 1)[1].strip() for line in response.text.splitlines()
                 if line.lower().startswith("sitemap:")]
    return roots or [f"https://{name}/sitemap.xml"]


def discover_host(client, name, sitemaps=None):
    host = Host(client)
    queue = list(sitemaps or sitemap_roots(host, name))
    seen, urls = set(), set()
    while queue and len(seen) < MAX_SITEMAPS:
        sitemap = queue.pop(0)
        if sitemap in seen:
            continue
        seen.add(sitemap)
        response = host.get(sitemap)
        if response is None or response.status_code != 200:
            continue
        text = body_text(response)
        for loc in LOC.findall(text):
            if "<sitemapindex" in text[:2000].lower() or loc.endswith((".xml", ".xml.gz")):
                if not is_foreign_sitemap(loc):
                    queue.append(loc)
            else:
                urls.add(loc)
    return seen, urls


def discover_company(client, entry):
    rows, sitemaps_read, total = [], 0, 0
    for name in entry["hosts"]:
        seen, urls = discover_host(client, name, entry.get("sitemaps"))
        sitemaps_read += len(seen)
        total += len(urls)
        for url in sorted(urls):
            if CANDIDATE.search(urlparse(url).path) and is_english_path(url) and company_list.owns(entry, url):
                rows.append({"company": entry["company"], "host": name, "url": url})
    # Pages a sitemap leaves out (linear.app/switch), added by hand in domains.yml.
    listed = {row["url"] for row in rows}
    for url in entry.get("extra_urls", []):
        if url not in listed:
            rows.append({"company": entry["company"], "host": urlparse(url).netloc, "url": url})
    print(f"{entry['company']:<12} sitemaps={sitemaps_read:<4} urls={total:<7} candidates={len(rows)}", flush=True)
    return rows


def main():
    out_path, only = sys.argv[1], set(sys.argv[2:])
    companies = [c for c in company_list.load() if not only or c["company"] in only]

    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client, \
            ThreadPoolExecutor(min(32, len(companies))) as pool:
        results = list(pool.map(lambda entry: discover_company(client, entry), companies))

    with open(out_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["company", "host", "url"])
        writer.writeheader()
        for rows in results:
            writer.writerows(rows)
    print(f"wrote {sum(map(len, results))} candidates to {out_path}")


if __name__ == "__main__":
    main()
