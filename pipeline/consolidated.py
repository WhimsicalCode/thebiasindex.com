"""Score Luna v8 on every labeled set, against Claude's labels and panel-adjusted labels."""

import json
import sys

import pandas as pd

sys.path.insert(0, "pipeline")
from evaluate import QUESTIONS, apply_reviews, luna_answer  # noqa: E402

SKIP = {"f075", "f076", "f078", "f079", "f080", "f081"}  # served in French; the crawler drops them
SETS = ["tuning", "heldout", "fresh2", "fresh3"]
NAMES = {"tuning": "Tuning set", "heldout": "Held-out", "fresh2": "Fresh 2", "fresh3": "Fresh 3"}

def score(gold, luna):
    df = gold.merge(luna, on="page_id", suffixes=("_gold", "_luna"))
    gate = ((df.page_type_gold == "competitor_comparison") == (df.page_type_luna == "competitor_comparison"))
    both = df[(df.page_type_gold == "competitor_comparison") & (df.page_type_luna == "competitor_comparison")]
    out = {"pages": len(both), "page_type": (gate.sum(), len(gate))}
    unclear = 0
    for q in QUESTIONS:
        a = both[f"{q}_luna"].map(luna_answer)
        dec = a.notna()
        unclear += (~dec).sum()
        agree = (both.loc[dec, f"{q}_gold"].astype(bool) == a[dec].astype(bool))
        out[q] = (agree.sum(), len(agree))
    g = both[[f"{q}_gold" for q in QUESTIONS]].astype(int).sum(axis=1)
    out["score_pm1"] = (((g - both.score).abs() <= 1).sum(), len(both))
    out["unclear"] = (unclear, len(both) * len(QUESTIONS))
    return out

rows = {}
for basis in ["claude", "panel"]:
    for s in SETS:
        labels = [json.loads(line) for line in open(f"benchmark/{s}/gold.jsonl")]
        gold = [row for row in labels if row["page_id"] not in SKIP]
        if basis == "panel":
            gold = apply_reviews(gold, f"benchmark/{s}/reviews.jsonl")
        luna = pd.read_csv(f"benchmark/{s}/luna_v8.csv")
        luna = luna[~luna.page_id.isin(SKIP)]
        rows[(basis, s)] = score(pd.DataFrame(gold), luna)

def pct(t):
    return f"{t[0] / t[1]:.0%} ({t[0]}/{t[1]})" if t[1] else "-"

items = ["page_type", *QUESTIONS, "score_pm1", "unclear"]
for basis in ["claude", "panel"]:
    print(f"\n### Luna v8 against {'Claude labels' if basis == 'claude' else 'panel-adjusted labels'}")
    header = ["", *[NAMES[s] for s in SETS], "Unseen pooled"]
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for it in items:
        cells = [pct(rows[(basis, s)][it]) for s in SETS]
        pooled = [sum(rows[(basis, s)][it][i] for s in SETS[1:]) for i in (0, 1)]
        print(f"| {it} | " + " | ".join(cells) + f" | **{pct(pooled)}** |")
