"""Export the database as CSV for the weekly data release, plus the release notes.

Usage: uv run pipeline/export.py [--db data/bias_index.sqlite] [--out data/export]

Writes OUT/companies.csv (one row per monitored company), OUT/pages.csv (every page ever checked, with a `current`
column for pages seen in the company's latest run) and OUT/release-notes.md. Answers are red-flag probabilities:
0.8 or more is a red flag, 0.2 or less is a no, anything between is unclear (docs/METHODOLOGY.md).
"""

import argparse
import csv
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QUESTIONS = ["best_at_everything", "no_honest_exit", "no_admitted_weakness", "vague_attacks", "uneven_scrutiny"]
CURRENT = "p.last_seen = (select max(last_seen) from pages p2 where p2.company_slug = p.company_slug)"


def write_csv(path, cursor):
    columns = [d[0] for d in cursor.description]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(cursor)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", default=str(REPO / "data" / "bias_index.sqlite"))
    parser.add_argument("--out", default=str(REPO / "data" / "export"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.db)

    write_csv(out / "companies.csv", db.execute(f"""
        select c.slug as domain, c.company, c.status, c.candidates,
               count(p.url) filter (where p.page_type = 'competitor_comparison') as competitor_comparisons,
               coalesce(sum(p.score) filter (where p.page_type = 'competitor_comparison'), 0) as red_flags_total,
               round(avg(p.score) filter (where p.page_type = 'competitor_comparison'), 2) as red_flags_per_page
        from companies c left join pages p on p.company_slug = c.slug and {CURRENT}
        group by c.slug order by red_flags_total desc, c.company"""))

    write_csv(out / "pages.csv", db.execute(f"""
        select p.company_slug as domain, p.url, p.title, {CURRENT} as current, p.first_seen, p.last_seen,
               p.http_status, p.skip_reason, p.page_type, p.score as red_flags, p.unclear,
               {", ".join(f"round(p.p_{q}, 3) as {q}" for q in QUESTIONS)},
               p.methodology, p.model, p.classified_at
        from pages p order by p.company_slug, p.url"""))

    run = db.execute("select started_at, methodology, model from runs where finished_at is not null "
                     "order by run_id desc limit 1").fetchone()
    companies, scored, flags = db.execute(f"""
        select count(distinct c.slug),
               count(p.url) filter (where p.page_type = 'competitor_comparison'),
               coalesce(sum(p.score) filter (where p.page_type = 'competitor_comparison'), 0)
        from companies c left join pages p on p.company_slug = c.slug and {CURRENT}""").fetchone()
    (out / "release-notes.md").write_text(
        f"Weekly run of {run[0][:10]}, methodology {run[1]} ({run[2]}).\n\n"
        f"- {companies} companies monitored\n- {scored:,} competitor comparisons scored\n"
        f"- {flags:,} red flags in total\n\n"
        "Files: `bias_index.sqlite` (the full database the site is built from), `companies.csv` and `pages.csv`. "
        "Answers are red-flag probabilities: 0.8 or more is a red flag, 0.2 or less is a no, anything between is "
        "unclear. How pages are found and scored: "
        "[docs/METHODOLOGY.md](https://github.com/WhimsicalCode/thebiasindex.com/blob/main/docs/METHODOLOGY.md). "
        "MIT licensed.\n",
        encoding="utf-8",
    )
    print(f"exported {companies} companies, {scored:,} scored pages to {out}")


if __name__ == "__main__":
    main()
