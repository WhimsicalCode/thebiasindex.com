"""Compare Luna's answers with the gold labels and check the targets (docs/METHODOLOGY.md, "How reliable is it").

Usage: uv run pipeline/evaluate.py GOLD.jsonl LUNA.csv [DISAGREEMENTS.csv]
           [--reviews REVIEWS.jsonl]

With --reviews, reviewed labels (by a person or the AI panel) replace the gold labels for those pages.
"""

import json
import sys

import pandas as pd

QUESTIONS = ["best_at_everything", "no_honest_exit", "no_admitted_weakness", "vague_attacks", "uneven_scrutiny"]
RED_FLAG, OK = 0.8, 0.2
TARGETS = {"question_agreement": 0.90, "page_type": 0.95, "score_within_1": 0.90, "unclear_rate": 0.15}


def luna_answer(probability):
    if probability >= RED_FLAG:
        return True
    if probability <= OK:
        return False
    return None  # unclear


def apply_reviews(gold, reviews_path):
    with open(reviews_path) as handle:
        reviews = {row["page_id"]: row for row in map(json.loads, filter(str.strip, handle))}
    for row in gold:
        review = reviews.get(row["page_id"])
        if review:
            row.update({key: review[key] for key in ["page_type", *QUESTIONS] if key in review})
    print(f"applied {len(reviews)} reviews ({sum(r['reviewer'] != 'ai-panel' for r in reviews.values())} by a person)")
    return gold


def main():
    args = sys.argv[1:]
    reviews_path = None
    if "--reviews" in args:
        reviews_path = args.pop(args.index("--reviews") + 1)
        args.remove("--reviews")
    gold_path, luna_path = args[0], args[1]
    out_path = args[2] if len(args) > 2 else None
    with open(gold_path) as handle:
        gold = [json.loads(line) for line in handle]
    if reviews_path:
        gold = apply_reviews(gold, reviews_path)
    gold = pd.DataFrame(gold)
    luna = pd.read_csv(luna_path)
    df = gold.merge(luna, on="page_id", suffixes=("_gold", "_luna"))
    rows, report = [], {}

    # Page type: exact match, and the gate that matters for scoring (competitor comparison or not).
    exact = (df.page_type_gold == df.page_type_luna).mean()
    gate = ((df.page_type_gold == "competitor_comparison") == (df.page_type_luna == "competitor_comparison")).mean()
    report["page_type"] = gate
    target = TARGETS["page_type"]
    print(f"page type: {exact:.0%} exact, {gate:.0%} on the competitor-comparison gate (target {target:.0%})")
    for _, row in df[df.page_type_gold != df.page_type_luna].iterrows():
        rows.append({"page_id": row.page_id, "company": row.company, "item": "page_type",
                     "gold": row.page_type_gold, "luna": row.page_type_luna,
                     "reason": (row.reasons or {}).get("page_type", "")})

    # Questions: pages both sides treat as competitor comparisons.
    both = df[(df.page_type_gold == "competitor_comparison") & (df.page_type_luna == "competitor_comparison")]
    print(f"\nquestions on {len(both)} pages both call competitor comparisons:")
    unclear_total = agreements = 0
    worst = 1.0
    for question in QUESTIONS:
        answers = both[f"{question}_luna"].map(luna_answer)
        unclear = answers.isna()
        decided = both[~unclear]
        agree = (decided[f"{question}_gold"].astype(bool) == answers[~unclear].astype(bool))
        rate = agree.mean() if len(decided) else float("nan")
        worst = min(worst, rate)
        unclear_total += unclear.sum()
        agreements += agree.sum()
        print(f"  {question:<18} agree {rate:5.0%} ({agree.sum()}/{len(decided)})   unclear {unclear.sum()}")
        for idx in decided.index[~agree.values]:
            row = both.loc[idx]
            rows.append({"page_id": row.page_id, "company": row.company, "item": question,
                         "gold": bool(row[f"{question}_gold"]), "luna": round(row[f"{question}_luna"], 2),
                         "reason": (row.reasons or {}).get(question, "")})
    report["question_agreement"] = worst
    unclear_rate = unclear_total / (len(both) * len(QUESTIONS))
    report["unclear_rate"] = unclear_rate
    print(f"  overall agreement {agreements / (len(both) * len(QUESTIONS) - unclear_total):.0%}, "
          f"unclear rate {unclear_rate:.0%} (target <= {TARGETS['unclear_rate']:.0%})")

    # Page score within one red flag.
    gold_score = both[[f"{q}_gold" for q in QUESTIONS]].astype(int).sum(axis=1)
    within = ((gold_score - both.score).abs() <= 1).mean()
    report["score_within_1"] = within
    print(f"\npage score within ±1: {within:.0%} (target {TARGETS['score_within_1']:.0%}); "
          f"mean gold {gold_score.mean():.2f}, mean Luna {both.score.mean():.2f}")

    print("\npass criteria:")
    for key, target in TARGETS.items():
        value = report[key]
        ok = value <= target if key == "unclear_rate" else value >= target
        print(f"  {key:<20} {value:5.0%}  {'PASS' if ok else 'FAIL'}")

    if out_path:
        pd.DataFrame(rows).to_csv(out_path, index=False)
        print(f"\n{len(rows)} disagreements written to {out_path}")


if __name__ == "__main__":
    main()
