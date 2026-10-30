"""The monitored companies (pipeline/domains.yml), checked before anything is crawled.

A company's `domain` is its identity on the site: the slug of its page (thebiasindex.com/clickup.com) and the
key an LLM or a reader looks it up by. It is written by hand, never derived from the company name, and a run
stops if the file breaks one of these rules:

- every company has a unique domain, and no alias or host belongs to two companies;
- the first host is the domain itself or one of its subdomains (www.notion.com for notion.com);
- extra hosts on another domain (tldraw.dev for tldraw.com) must be listed explicitly under `hosts`.

`owns()` is the guard used on every URL: a page only counts for a company when its host is one of the company's
hosts, or a subdomain of its domain or of one of those hosts. Sitemaps sometimes list other sites (zoho.com's
points at zoho.com.cn) and pages can redirect elsewhere; those are never scored under the company's name.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

PATH = Path(__file__).resolve().parent / "domains.yml"
DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def _within(host, domain):
    return host == domain or host.endswith("." + domain)


def owns(entry, url):
    """Whether the URL's host belongs to this company."""
    host = (urlparse(url).hostname or "").lower()
    return any(_within(host, root) for root in [entry["domain"], *entry["hosts"]])


def validate(entries):
    problems, claimed = [], {}
    for entry in entries:
        name, domain = entry.get("company"), entry.get("domain", "")
        if not DOMAIN.match(domain) or domain.startswith("www."):
            problems.append(f"{name}: domain {domain!r} must be a bare lowercase domain like clickup.com")
            continue
        if not entry.get("hosts") or not _within(entry["hosts"][0], domain):
            problems.append(f"{name}: first host must be {domain} or a subdomain of it")
        for key in [domain, *entry.get("aliases", []), *entry.get("hosts", [])]:
            key = key.removeprefix("www.")
            if claimed.setdefault(key, name) != name:
                problems.append(f"{name}: {key} is already used by {claimed[key]}")
        for url in entry.get("extra_urls", []):
            if not owns(entry, url):
                problems.append(f"{name}: extra URL {url} is not on its hosts")
    if problems:
        raise SystemExit("pipeline/domains.yml is invalid:\n  " + "\n  ".join(problems))
    return entries


def load(path=PATH):
    with open(path) as handle:
        return validate(yaml.safe_load(handle))
