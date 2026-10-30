"""Second-opinion labels from an AI panel, so a person only reviews the pages where models disagree.

Usage: uv run pipeline/ai_review.py FETCH_DIR [--set tuning|heldout|fresh2|fresh3] [--limit N] [--pages p001,p002]

Two judges from other model families label every benchmark page with docs/LABELING_GUIDELINES.md: GPT-6.1 Sol
(OpenAI) and Gemini 3.1 Pro (Google, via Vertex AI). Together with Claude's gold labels they form a three-vote
panel. Luna never votes: it is the model being graded.

- Unanimous or 2-of-3 answers are accepted. A page needs a person only when a vote is split (1-1, or fewer than
  two judges answered). Pages where the majority overturned one of Claude's labels are accepted too, but the
  review app lists them separately so a person can spot-check them.
- Judge outputs are cached under FETCH_DIR/ai_review/<judge>/, so reruns are free.
- Writes benchmark/<set>/panel.jsonl (every judge's labels and the vote) and adds "ai-panel" entries to
  benchmark/<set>/reviews.jsonl for settled pages. Reviews by a person are never overwritten.

Credentials come from the environment (see credentials.py) and are never printed. Vertex AI uses application
default credentials.
"""

import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
from credentials import google_cloud_project, openai_api_key

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
BENCHMARK = REPO / "benchmark" / "tuning"
PAGE_TYPES = ["competitor_comparison", "third_party_comparison", "own_products", "educational", "hub", "other"]
QUESTIONS = ["best_at_everything", "no_honest_exit", "no_admitted_weakness", "vague_attacks", "uneven_scrutiny"]
MAX_TEXT_CHARS = 120_000
PANEL_REVIEWER = "ai-panel"

JUDGES = {
    "gpt-6.1-sol": {"label": "GPT-6.1 Sol", "provider": "openai"},
    "gemini-3.1-pro-preview": {"label": "Gemini 3.1 Pro", "provider": "vertex"},
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "quote": {"type": "string"},
        "reason": {"type": "string"},
        "answer": {"type": ["boolean", "null"]},
    },
    "required": ["quote", "reason", "answer"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "page_type_reason": {"type": "string"},
        "page_type": {"type": "string", "enum": PAGE_TYPES},
        **{question: ANSWER_SCHEMA for question in QUESTIONS},
    },
    "required": ["page_type_reason", "page_type", *QUESTIONS],
    "additionalProperties": False,
}


def system_prompt():
    guidelines = (REPO / "docs" / "LABELING_GUIDELINES.md").read_text().split("## Recording a label")[0]
    return (
        "You are an independent reviewer for The Bias Index, which scores how fair SaaS comparison pages are. "
        "Label one page by applying the guidelines below exactly. The publisher is the company whose website "
        "hosts the page. Judge only from the page text you are given: navigation and footers were removed, and "
        "images were dropped, so tables drawn with icons may appear as empty cells.\n\n"
        "Return JSON with: page_type and a one-sentence page_type_reason; then for each of the five questions an "
        "object with a short verbatim quote from the page that supports your answer (empty string if none), a "
        "one-sentence reason, and answer (true = red flag, false = no red flag, null only when page_type is not "
        "competitor_comparison).\n\n" + guidelines
    )


def user_message(page, products, title, text):
    return json.dumps({
        "publisher": page["company"],
        "publisher_products": products,
        "url": page["url"],
        "title": title,
        "page_text": text[:MAX_TEXT_CHARS],
    })


def valid(label):
    if not isinstance(label, dict) or label.get("page_type") not in PAGE_TYPES:
        return False
    for question in QUESTIONS:
        item = label.get(question)
        if not isinstance(item, dict) or item.get("answer") not in (True, False, None):
            return False
    return True


def ask_openai(client, model, system, message):
    response = client.responses.create(
        model=model,
        instructions=system,
        input=message,
        reasoning={"effort": "medium"},
        text={"format": {"type": "json_schema", "name": "page_label", "schema": SCHEMA, "strict": True}},
    )
    usage = response.usage
    return json.loads(response.output_text), {"input": usage.input_tokens, "output": usage.output_tokens}


def ask_vertex(client, model, system, message):
    from google.genai import types

    response = client.models.generate_content(
        model=model,
        contents=message,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=SCHEMA,
            temperature=0,
        ),
    )
    usage = response.usage_metadata
    output_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    return json.loads(response.text), {"input": usage.prompt_token_count, "output": output_tokens}


def judge_page(clients, judge, page, products, title, text, cache_dir):
    path = cache_dir / judge / f"{page['page_id']}.json"
    if path.exists():
        return json.loads(path.read_text())
    provider = JUDGES[judge]["provider"]
    ask = ask_openai if provider == "openai" else ask_vertex
    error = ""
    for attempt in range(3):
        try:
            label, usage = ask(clients[provider], judge, system_prompt(), user_message(page, products, title, text))
            if valid(label):
                result = {"page_id": page["page_id"], "judge": judge, "label": label, "usage": usage}
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(result, indent=1))
                return result
            error = "invalid label"
        except Exception as exc:  # retried, then reported
            error = f"{type(exc).__name__}: {exc}"[:300]
        time.sleep(2 ** attempt * 3)
    return {"page_id": page["page_id"], "judge": judge, "label": None, "error": error}


def vote(values):
    """Majority over non-null votes. Returns (result, status) with status unanimous, majority or split."""
    cast = [value for value in values if value is not None]
    counts = Counter(cast).most_common()
    if len(cast) >= 2 and counts[0][1] >= 2 and (len(counts) == 1 or counts[1][1] < counts[0][1]):
        return counts[0][0], "unanimous" if counts[0][1] == len(values) == len(cast) else "majority"
    return None, "split"


def panel_page(gold, labels):
    """Combine Claude's gold label and the judges' labels into one decision per item."""
    voters = {"claude-opus-5-5": {"page_type": gold["page_type"], **{q: gold[q] for q in QUESTIONS}}}
    for judge, label in labels.items():
        voters[judge] = {"page_type": label["page_type"], **{q: label[q]["answer"] for q in QUESTIONS}}
    page_type, page_type_status = vote([v["page_type"] for v in voters.values()])
    decision = {"page_type": page_type}
    status = {"page_type": page_type_status}
    for question in QUESTIONS:
        if page_type != "competitor_comparison":
            decision[question], status[question] = None, "n/a" if page_type else "split"
            continue
        votes = [v[question] if v["page_type"] == "competitor_comparison" else None for v in voters.values()]
        decision[question], status[question] = vote(votes)
    needs_human = any(value == "split" for value in status.values())
    overturned = [key for key in ["page_type", *QUESTIONS]
                  if status[key] != "split" and decision[key] != gold.get(key)]
    return {"votes": voters, "decision": decision, "status": status,
            "needs_human": needs_human, "overturned_claude": overturned}


def main():
    fetch_dir = Path(sys.argv[1])
    args = sys.argv[2:]
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    global BENCHMARK
    if "--set" in args:
        BENCHMARK = REPO / "benchmark" / args[args.index("--set") + 1]
    only = set(args[args.index("--pages") + 1].split(",")) if "--pages" in args else None

    from google import genai
    from openai import OpenAI

    clients = {
        "openai": OpenAI(api_key=openai_api_key(), timeout=300),
        "vertex": genai.Client(vertexai=True, project=google_cloud_project(), location="global"),
    }
    with open(TOOLS / "domains.yml") as handle:
        products = {entry["company"]: entry["product_names"] for entry in yaml.safe_load(handle)}
    pages = pd.read_csv(BENCHMARK / "pages.csv").to_dict("records")
    titles = pd.read_csv(fetch_dir / "fetch.csv").set_index("page_id").title.fillna("").to_dict()
    with open(BENCHMARK / "gold.jsonl") as handle:
        gold = {row["page_id"]: row for row in map(json.loads, handle)}
    if only:
        pages = [page for page in pages if page["page_id"] in only]
    if limit:
        pages = pages[:limit]

    def run(job):
        judge, page = job
        text = (fetch_dir / "text" / f"{page['page_id']}.md").read_text(encoding="utf-8")
        return judge_page(clients, judge, page, products.get(page["company"], [page["company"]]),
                          titles.get(page["page_id"], ""), text, fetch_dir / "ai_review")

    started = time.monotonic()
    jobs = [(judge, page) for page in pages for judge in JUDGES]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(run, jobs))
    errors = [r for r in results if r["label"] is None]
    print(f"{len(jobs)} judge calls in {time.monotonic() - started:.0f}s, {len(errors)} failed")
    for result in errors:
        print(f"  {result['judge']} {result['page_id']}: {result['error']}")

    by_page = {}
    for result in results:
        if result["label"] is not None:
            by_page.setdefault(result["page_id"], {})[result["judge"]] = result["label"]

    panel = {}
    for page in pages:
        page_id = page["page_id"]
        entry = panel_page(gold[page_id], by_page.get(page_id, {}))
        entry["judge_reasons"] = {
            judge: {"page_type": label["page_type_reason"],
                    **{q: f"{label[q]['reason']} \"{label[q]['quote']}\"".replace(' ""', "") for q in QUESTIONS}}
            for judge, label in by_page.get(page_id, {}).items()
        }
        panel[page_id] = {"page_id": page_id, **entry}

    # Merge with earlier panel results for pages not in this run.
    panel_path = BENCHMARK / "panel.jsonl"
    if panel_path.exists():
        with open(panel_path) as handle:
            panel = {**{row["page_id"]: row for row in map(json.loads, handle)}, **panel}
    with open(panel_path, "w") as handle:
        for page_id in sorted(panel):
            handle.write(json.dumps(panel[page_id]) + "\n")

    write_panel_reviews(panel, gold)
    report(panel, by_page, gold)


def write_panel_reviews(panel, gold):
    """Record settled pages as ai-panel reviews; never touch a person's review."""
    reviews_path = BENCHMARK / "reviews.jsonl"
    reviews = {}
    if reviews_path.exists():
        with open(reviews_path) as handle:
            reviews = {row["page_id"]: row for row in map(json.loads, filter(str.strip, handle))}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for page_id, entry in panel.items():
        if page_id in reviews and reviews[page_id]["reviewer"] != PANEL_REVIEWER:
            continue
        if entry["needs_human"]:
            reviews.pop(page_id, None)
            continue
        statuses = Counter(entry["status"].values())
        reviews[page_id] = {
            "page_id": page_id, "reviewer": PANEL_REVIEWER, "reviewed_at": now,
            **entry["decision"],
            "changed_from_claude": entry["overturned_claude"],
            "notes": f"panel: {statuses['unanimous']} unanimous, {statuses['majority']} majority",
        }
    with open(reviews_path, "w") as handle:
        for page_id in sorted(reviews):
            handle.write(json.dumps(reviews[page_id]) + "\n")


def report(panel, by_page, gold):
    print("\nagreement with Claude's labels (items both answered):")
    for judge, meta in JUDGES.items():
        same = total = 0
        for page_id, labels in by_page.items():
            if judge not in labels:
                continue
            label, reference = labels[judge], gold[page_id]
            total += 1
            same += label["page_type"] == reference["page_type"]
            for question in QUESTIONS:
                if label[question]["answer"] is not None and reference[question] is not None:
                    total += 1
                    same += label[question]["answer"] == reference[question]
        print(f"  {meta['label']:<16} {same / total:.0%} ({same}/{total})" if total else f"  {meta['label']}: none")
    needs_human = sorted(page_id for page_id, entry in panel.items() if entry["needs_human"])
    overturned = sorted(page_id for page_id, entry in panel.items() if entry["overturned_claude"])
    print(f"\npages needing a person: {len(needs_human)} {needs_human}")
    print(f"pages where the panel overturned a Claude label: {len(overturned)}")
    for page_id in overturned:
        print(f"  {page_id}: {', '.join(panel[page_id]['overturned_claude'])}")


if __name__ == "__main__":
    main()
