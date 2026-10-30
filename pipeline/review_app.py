"""Review the thebiasindex.com benchmark page by page.

Run from the repo root:
    uv run streamlit run pipeline/review_app.py

Pick the set with BIAS_SET (tuning, heldout, fresh2, fresh3). The queue is review_queue.csv (or Claude's
close calls) plus every page where the AI panel (ai_review.py) overturned one of
Claude's labels. Each page's extracted text is shown next to Claude's label, the panel's votes and Luna's answer.
Decisions are saved to benchmark/reviews.jsonl and replace the panel's entry for that page. The text comes from
fetch_pages.py (data/raw/<set>/text/); re-fetch it with that script if the folder is missing.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
SET = os.environ.get("BIAS_SET", "tuning")
BENCHMARK = REPO / "benchmark" / SET
QUEUE = BENCHMARK / "review_queue.csv"
GOLD = BENCHMARK / "gold.jsonl"
PANEL = BENCHMARK / "panel.jsonl"
LUNA = BENCHMARK / "luna_v8.csv"
GUIDELINES = REPO / "docs" / "LABELING_GUIDELINES.md"
REVIEWS = Path(os.environ.get("BIAS_REVIEWS_PATH", BENCHMARK / "reviews.jsonl"))
TEXT_DIR = Path(os.environ.get("BIAS_TEXT_DIR", REPO / "data" / "raw" / SET / "text"))
PANEL_REVIEWER = "ai-panel"
JUDGE_LABELS = {"gpt-6.1-sol": "GPT-6.1 Sol", "gemini-3.1-pro-preview": "Gemini 3.1 Pro"}

PAGE_TYPES = ["competitor_comparison", "third_party_comparison", "own_products", "educational", "hub", "other"]
QUESTIONS = {
    "best_at_everything": (
        "Best at everything",
        "Does the page present the publisher's product as winning or tying on everything, conceding no area "
        "where a competitor is stronger?",
    ),
    "no_honest_exit": (
        "No honest exit",
        "Does the page leave out every situation where a competitor would be the better choice?",
    ),
    "no_admitted_weakness": (
        "No admitted weakness",
        "Does the page avoid saying anything the publisher's own product can't do or does poorly?",
    ),
    "vague_attacks": (
        "Vague attacks",
        "Are the page's criticisms of competitors vague, with no specifics, numbers or sources?",
    ),
    "uneven_scrutiny": (
        "Uneven scrutiny",
        "Does the page list clearly more drawbacks for competitors than for the publisher's product?",
    ),
}
ANSWERS = ["yes", "no"]
FILTERS = ["All queued pages", "Panel overturned Claude", "Not reviewed by a person"]


def read_jsonl(path):
    if not path.exists():
        return {}
    with open(path) as handle:
        return {row["page_id"]: row for row in map(json.loads, filter(str.strip, handle))}


def yes_no(value):
    return "" if value is None else ("yes" if value else "no")


@st.cache_data
def load_rows():
    gold = read_jsonl(GOLD)
    panel = read_jsonl(PANEL)
    pages = pd.read_csv(BENCHMARK / "pages.csv").set_index("page_id")
    luna = pd.read_csv(LUNA).set_index("page_id")
    if QUEUE.exists():
        queue = pd.read_csv(QUEUE, dtype=str, keep_default_na=False).set_index("page_id").why_in_queue.to_dict()
    else:  # sets without a prepared queue: Claude's close calls
        queue = {page_id: "close call" for page_id, label in gold.items() if label.get("needs_human")}
    overturned = {page_id for page_id, entry in panel.items() if entry["overturned_claude"]}
    rows = {}
    for page_id in sorted(set(queue) | overturned):
        label = gold[page_id]
        why = [queue[page_id]] if page_id in queue else []
        if page_id in overturned:
            why.append("panel overturned Claude")
        row = {"page_id": page_id, "company": pages.company[page_id], "url": pages.url[page_id],
               "why_in_queue": "; ".join(why), "gold_page_type": label["page_type"],
               "page_type_reason": label["reasons"].get("page_type", ""), "panel": panel.get(page_id),
               "luna_page_type": luna.page_type[page_id],
               "luna_page_type_confidence": float(luna.page_type_confidence[page_id])}
        for question in QUESTIONS:
            row[f"{question}_gold"] = yes_no(label[question])
            row[f"{question}_reason"] = label["reasons"].get(question, "")
            row[f"{question}_luna"] = float(luna[question][page_id])
        rows[page_id] = row
    return rows


@st.cache_data
def load_text(page_id):
    path = TEXT_DIR / f"{page_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def write_reviews(reviews):
    with open(REVIEWS, "w") as handle:
        for page_id in sorted(reviews):
            handle.write(json.dumps(reviews[page_id]) + "\n")


def default_reviewer():
    result = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, cwd=REPO)
    return result.stdout.strip()


def flag_label(probability):
    if probability >= 0.8:
        return "yes"
    if probability <= 0.2:
        return "no"
    return "unclear"


def visible(page_id, rows, reviews, mode):
    if mode == "Panel overturned Claude":
        return "panel overturned Claude" in rows[page_id]["why_in_queue"]
    if mode == "Not reviewed by a person":
        return reviews.get(page_id, {}).get("reviewer", PANEL_REVIEWER) == PANEL_REVIEWER
    return True


def save(row, ids, rows):
    """Button callback: store the current page's answers, then move to the next page."""
    page_id = row["page_id"]
    state = st.session_state
    page_type = state[f"{page_id}_page_type"]
    review = {"page_id": page_id, "reviewer": state.reviewer.strip(),
              "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "page_type": page_type}
    changed = [] if page_type == row["gold_page_type"] else ["page_type"]
    for question in QUESTIONS:
        answer = state.get(f"{page_id}_{question}") if page_type == "competitor_comparison" else None
        review[question] = None if answer is None else answer == "yes"
        if (answer or "") != row[f"{question}_gold"]:
            changed.append(question)
    review["changed_from_claude"] = changed
    review["notes"] = state.get(f"{page_id}_notes", "").strip()

    reviews = read_jsonl(REVIEWS)
    reviews[page_id] = review
    write_reviews(reviews)

    position = ids.index(page_id)
    later = [i for i in ids[position + 1:] + ids[:position] if visible(i, rows, reviews, state.filter)]
    state.page = later[0] if later else page_id


st.set_page_config(page_title="thebiasindex.com review", layout="wide")
rows = load_rows()
reviews = read_jsonl(REVIEWS)

with st.sidebar:
    st.title("thebiasindex.com review")
    if "reviewer" not in st.session_state:
        st.session_state.reviewer = default_reviewer()
    st.text_input("Your name", key="reviewer")
    st.radio("Show", FILTERS, key="filter")
    by_person = sum(reviews.get(i, {}).get("reviewer", PANEL_REVIEWER) != PANEL_REVIEWER for i in rows)
    st.progress(by_person / len(rows), text=f"{by_person} of {len(rows)} reviewed by a person")

    ids = [page_id for page_id in rows if visible(page_id, rows, reviews, st.session_state.filter)]
    if not ids:
        st.success("Nothing left in this view.")
        st.stop()
    if st.session_state.get("page") not in ids:
        st.session_state.page = ids[0]

    def page_label(page_id):
        reviewer = reviews.get(page_id, {}).get("reviewer")
        mark = "⬜" if reviewer is None else ("🤖" if reviewer == PANEL_REVIEWER else "✅")
        return f"{mark} {page_id} · {rows[page_id]['company']} · {rows[page_id]['url'].split('://', 1)[-1][:42]}"

    st.selectbox("Page", ids, key="page", format_func=page_label)
    st.caption("✅ reviewed by a person · 🤖 settled by the AI panel · ⬜ not reviewed")
    with st.expander("Labeling guidelines"):
        st.markdown(GUIDELINES.read_text())

row = rows[st.session_state.page]
page_id = row["page_id"]
existing = reviews.get(page_id, {})
panel = row["panel"] or {}
overturned = set(panel.get("overturned_claude", []))

left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader(f"{page_id} · {row['company']}")
    st.markdown(f"[{row['url']}]({row['url']}) · in queue because: *{row['why_in_queue']}*")
    text = load_text(page_id)
    if text is None:
        st.error(f"No extracted text in {TEXT_DIR}. Re-fetch with pipeline/fetch_pages.py.")
    else:
        query = st.text_input("Find in page", key=f"{page_id}_find", placeholder="e.g. cons, best, choose")
        if query:
            hits = [line for line in text.splitlines() if query.lower() in line.lower()]
            with st.expander(f"{len(hits)} matching lines", expanded=True):
                for line in hits[:50]:
                    st.markdown(f"- {line.strip()}")
        with st.container(height=760):
            st.markdown(text)


def judge_lines(item):
    for judge, label in JUDGE_LABELS.items():
        vote = panel.get("votes", {}).get(judge)
        if vote is None:
            continue
        answer = vote[item] if item == "page_type" else yes_no(vote[item]) or "n/a"
        reason = panel.get("judge_reasons", {}).get(judge, {}).get(item, "")
        st.caption(f"{label}: **{answer}** · {reason}")


with right:
    gold_type = row["gold_page_type"]
    st.markdown("#### Page type" + (" ⚠️ panel overturned Claude" if "page_type" in overturned else ""))
    st.caption(f"Claude: **{gold_type}** · {row['page_type_reason'] or 'no reason recorded'}")
    judge_lines("page_type")
    st.caption(f"Luna: **{row['luna_page_type']}** ({row['luna_page_type_confidence']:.2f})")
    default_type = existing.get("page_type", gold_type)
    page_type = st.radio("Page type", PAGE_TYPES, index=PAGE_TYPES.index(default_type), key=f"{page_id}_page_type",
                         label_visibility="collapsed")

    missing = False
    if page_type == "competitor_comparison":
        st.markdown("#### Red flags (yes = biased)")
        for question, (label, wording) in QUESTIONS.items():
            gold = row[f"{question}_gold"]
            marker = " ⚠️ panel overturned Claude" if question in overturned else ""
            st.markdown(f"**{label}**{marker}  \n{wording}")
            st.caption(f"Claude: **{gold or 'n/a'}** · {row[f'{question}_reason'] or 'no reason recorded'}")
            judge_lines(question)
            st.caption(f"Luna: **{flag_label(row[f'{question}_luna'])}** ({row[f'{question}_luna']:.2f})")
            if existing.get(question) is not None:
                default = "yes" if existing[question] else "no"
            else:
                default = gold or None
            answer = st.radio(label, ANSWERS, horizontal=True, key=f"{page_id}_{question}",
                              index=ANSWERS.index(default) if default else None, label_visibility="collapsed")
            missing = missing or answer is None
    else:
        st.info("Not a competitor comparison, so the five questions don't apply.")

    own_notes = existing.get("notes", "") if existing.get("reviewer") != PANEL_REVIEWER else ""
    st.text_area("Notes (optional)", value=own_notes, key=f"{page_id}_notes", height=80)
    if existing:
        who = "the AI panel" if existing["reviewer"] == PANEL_REVIEWER else existing["reviewer"]
        st.caption(f"Answers are pre-filled from {who} ({existing['reviewed_at']}). Saving records your review.")
    blocked = not st.session_state.reviewer.strip() or missing
    st.button("Save and next →", type="primary", use_container_width=True, key="save", disabled=blocked,
              on_click=save, args=(row, ids, rows))
    if blocked:
        st.caption("Enter your name and answer every question to save.")
