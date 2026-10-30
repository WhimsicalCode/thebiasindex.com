"""Thin out old weekly data releases: keep the 8 most recent, plus the first release of every month.

Usage: uv run pipeline/prune_releases.py [--dry-run]

Data releases are tagged data-YYYY-MM-DD (see .github/workflows/weekly.yml). Other releases are never touched.
Needs the GitHub CLI (`gh`), authenticated; in the workflow it uses the workflow's own token.
"""

import argparse
import json
import re
import subprocess

KEEP_RECENT = 8
TAG = re.compile(r"^data-(\d{4})-(\d{2})-(\d{2})$")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    listed = subprocess.run(["gh", "release", "list", "--limit", "1000", "--json", "tagName"],
                            check=True, capture_output=True, text=True).stdout
    tags = sorted((t["tagName"] for t in json.loads(listed) if TAG.match(t["tagName"])), reverse=True)
    keep = set(tags[:KEEP_RECENT])
    first_of_month = {}
    for tag in sorted(tags):
        first_of_month.setdefault(tag[:12], tag)  # "data-YYYY-MM"
    keep |= set(first_of_month.values())

    for tag in tags:
        if tag in keep:
            continue
        print(f"{'would delete' if args.dry_run else 'deleting'} {tag}")
        if not args.dry_run:
            subprocess.run(["gh", "release", "delete", tag, "--cleanup-tag", "--yes"], check=True)
    print(f"{len(keep)} data releases kept")


if __name__ == "__main__":
    main()
