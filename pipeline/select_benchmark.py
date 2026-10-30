"""Draw the benchmark pages from discovered candidates: random within URL-pattern buckets, fixed seed.

Usage: uv run pipeline/select_benchmark.py CANDIDATES.csv OUT.csv
           [--heldout [PRODUCT_PAGES OTHER_PAGES PREFIX]]

Buckets are defined by URL only, before anyone has read the pages, so the selection can't be tilted
towards pages that are easy (or hard) to score. Bucket names are expectations, not labels.
"""

import sys

import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from discover import USER_CONTENT, is_english_path  # noqa: E402

SEED = 20261028

# (company, bucket, regex on the URL, number of pages)
BUCKETS = [
    ("Miro", "vs_page", r"miro\.com/compare/.+", 6),
    ("Miro", "alternatives", r"miro\.com/al/", 5),
    ("Miro", "alternatives", r"miro\.com/alternative/", 1),
    ("Miro", "hub", r"miro\.com/compare/$", 1),
    ("Miro", "educational", r"miro\.com/(agile|diagramming|product-development|research-and-design)/.*-vs-", 3),
    ("Ponder", "vs_page", r"/blog/ponder-vs-", 7),
    ("Ponder", "alternatives", r"/blog/.*alternative", 4),
    ("Ponder", "third_party_vs", r"/blog/(?!ponder-).+-vs-", 3),
    ("Ponder", "roundup", r"/blog/ai-research-tools-comparison$", 1),
    ("ClickUp", "vs_page", r"clickup\.com/compare/vs/", 6),
    ("ClickUp", "vs_page", r"clickup\.com/blog/[^/]*clickup[^/]*-vs-|clickup\.com/blog/[^/]*-vs-clickup", 3),
    ("ClickUp", "alternatives", r"clickup\.com/blog/[^/]*alternatives", 4),
    ("monday.com", "alternatives", r"monday\.com/alternative/", 2),
    ("monday.com", "alternatives", r"monday\.com/blog/.*alternatives", 3),
    ("monday.com", "third_party_vs", r"monday\.com/blog/.*/[a-z0-9]+-vs-[a-z0-9]+/?$", 3),
    ("monday.com", "educational", r"monday\.com/blog/.*-vs-(operational|cms|customer)", 1),
    ("Lucid", "vs_page", r"lucid\.co/alternative/lucid[a-z]*-vs-", 5),
    ("Lucid", "alternatives", r"lucid\.co/alternative/best-", 2),
    ("Lucid", "educational", r"lucid\.co/blog/.*-vs-", 2),
    ("Creately", "vs_page", r"creately\.com/(creately-vs-|[a-z0-9-]+-vs-creately)", 4),
    ("Creately", "alternatives", r"creately\.com/([a-z0-9-]+-alternative/|alternative-to-|alternatives/)", 3),
    ("Creately", "educational", r"creately\.com/guides/.*-vs-", 2),
    ("Smartsheet", "vs_page", r"smartsheet\.com/smartsheet-vs-|smartsheet\.com/.*-smartsheet-comparison", 3),
    ("Smartsheet", "roundup", r"smartsheet\.com/best-spreadsheet-apps-complete-comparison-guide", 1),
    ("Smartsheet", "educational", r"smartsheet\.com/content/[a-z-]+-vs-[a-z-]+$", 2),
    ("Asana", "vs_page", r"asana\.com/compare/", 2),
    ("Asana", "alternatives", r"asana\.com/resources/.*alternative", 2),
    ("Asana", "educational", r"asana\.com/resources/.*-vs-", 1),
    ("Notion", "vs_page", r"notion\.com/compare-against/.+", 3),
    ("Notion", "duplicate", r"notion\.com/en-gb/compare-against/.+", 1),
    ("Notion", "vs_page", r"notion\.com/lp/notion-vs-", 1),
    ("Notion", "educational", r"notion\.com/blog/.*-vs-", 1),
    ("Mural", "vs_page", r"mural\.co/compare/.+", 2),
    ("Mural", "hub", r"mural\.co/compare$", 1),
    ("Mural", "educational", r"mural\.co/blog/.*-vs-", 2),
    ("Excalidraw", "vs_page", r"excalidraw-vs-", 1),
    ("Excalidraw", "own_products", r"excalidraw-plus-vs-excalidraw$", 1),
    ("draw.io", "vs_page", r"drawio\.com/blog/gliffy-vs-drawio", 1),
    ("draw.io", "educational", r"drawio\.com/docs/diagram-types/sysml-vs-uml", 1),
    ("draw.io", "own_products", r"drawio\.com/docs/manual/file-storage-locations-compare", 1),
    ("Whimsical", "other", r"whimsical\.com/blog/", 2),
]


# Held-out sampling: URLs that look like product comparisons vs everything else. Defined on URLs only.
LIKELY_PRODUCT = r"compare/|/al/|alternative|-vs-|/switch"
NOT_PRODUCT = (r"templates|prompts|generate/|automate/|convert/|help\.|/hc/|faq|resource-library|best-practices"
               r"|user-guide")


def select_heldout(candidates, out_path, product_pages=4, other_pages=1, prefix="h"):
    """Random pages per company, no hand-picked buckets: a held-out test of a frozen methodology."""
    candidates = candidates[~candidates.url.str.contains(USER_CONTENT, regex=True)]
    likely = candidates.url.str.contains(LIKELY_PRODUCT, regex=True) & ~candidates.url.str.contains(
        NOT_PRODUCT, regex=True)
    picks = []
    for company, group in candidates.groupby("company", sort=True):
        mask = likely[group.index]
        for pool, count, bucket in ((group[mask], product_pages, "likely_product"),
                                    (group[~mask], other_pages, "other")):
            picks.append(pool.sample(min(count, len(pool)), random_state=SEED).assign(bucket=bucket))
    selected = pd.concat(picks)[["company", "bucket", "url"]].reset_index(drop=True)
    selected.insert(0, "page_id", [f"{prefix}{i:03d}" for i in range(1, len(selected) + 1)])
    selected.to_csv(out_path, index=False)
    print(f"{len(selected)} held-out pages from {selected.company.nunique()} companies")
    print(selected.groupby(["company", "bucket"]).size().to_string())


def main():
    candidates_path, out_path = sys.argv[1], sys.argv[2]
    candidates = pd.read_csv(candidates_path)
    candidates = candidates[candidates.url.map(is_english_path)]
    if "--heldout" in sys.argv:
        # --heldout [PRODUCT_PAGES OTHER_PAGES PREFIX], e.g. --heldout 5 1 f
        extra = sys.argv[sys.argv.index("--heldout") + 1:]
        if extra:
            select_heldout(candidates, out_path, int(extra[0]), int(extra[1]), extra[2])
        else:
            select_heldout(candidates, out_path)
        return
    taken, picks = set(), []
    for company, bucket, pattern, count in BUCKETS:
        pool = candidates[(candidates.company == company) & candidates.url.str.contains(pattern, regex=True)
                          & ~candidates.url.isin(taken)]
        if len(pool) < count:
            print(f"warning: {company}/{bucket} wanted {count}, found {len(pool)}")
        chosen = pool.sample(min(count, len(pool)), random_state=SEED)
        taken.update(chosen.url)
        picks.append(chosen.assign(bucket=bucket))
    selected = pd.concat(picks)[["company", "bucket", "url"]].reset_index(drop=True)
    selected.insert(0, "page_id", [f"p{i:03d}" for i in range(1, len(selected) + 1)])
    selected.to_csv(out_path, index=False)
    print(f"{len(selected)} pages from {selected.company.nunique()} companies")
    print(selected.groupby("bucket").size().to_string())


if __name__ == "__main__":
    main()
