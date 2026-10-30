"""Classify fetched pages with OpenAI's Decisions API: page type plus the five questions (methodology v1).

Usage: uv run pipeline/classify.py PAGES.csv FETCH_DIR OUT.csv [WORKERS]

PAGES.csv needs `page_id`, `company` and `url`; FETCH_DIR is the output of fetch_pages.py. The API key comes from
OPENAI_API_KEY (see credentials.py) and is never printed. Question wording mirrors docs/LABELING_GUIDELINES.md.
"""

import csv
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import yaml
from credentials import openai_api_key

METHODOLOGY_VERSION = "v8"
MODEL = "gpt-6-luna"
MAX_TEXT_CHARS = 120_000  # ~30k tokens
RED_FLAG, OK = 0.8, 0.2

PAGE_TYPES = {
    "competitor_comparison": (
        "Compares the publisher's product with one or more named rival products, or lists alternatives to a "
        "product and the publisher's product is among them. Roundups that include the publisher's product count."
    ),
    "third_party_comparison": (
        "Compares or lists named products, none of them the publisher's. A closing call to action for the "
        "publisher's product does not change this, as long as it is not one of the options compared."
    ),
    "own_products": "Compares the publisher's own plans, editions or storage options.",
    "educational": "Compares concepts, methods, roles or software categories, not named products.",
    "hub": "An index linking to comparison pages, with no real comparison of its own.",
    "other": "Anything else: blog posts that only mention a 'vs', forms, survey announcements, opinion pieces.",
}

# Questions where a red flag is a confident "no". v1 asked these as negatives ("Are the drawbacks missing...?",
# "Does the page leave out every situation...?"), and Luna answered the double negative unreliably, so they are
# asked positively. The CSV still stores the probability of the red flag.
# The Decisions API answers each question independently: one request with all questions (v2) and one request per
# question (v4) gave identical answers, so a single request per page is used. See benchmark/RESULTS.md.
# v6 replaced crowns_itself ("best choice overall?") with best_at_everything; see METHODOLOGY.md.
INVERTED = {"best_at_everything", "no_honest_exit", "no_admitted_weakness"}

QUESTIONS_V1 = {
    "crowns_itself": (
        "Does the page present the publisher's product as the best choice overall?",
        "The page ranks the publisher's product #1 in a numbered or ranked list, or calls it the #1 alternative, "
        "the better or clear choice, more powerful, or otherwise declares it the overall winner.",
        "The page is framed as complementary or 'it depends' with no overall winner. Being better at specific "
        "things, or being listed first in an unranked list without a superlative, is not crowning.",
    ),
    "no_honest_exit": (
        "Does the page leave out every situation where a competitor would be the better choice?",
        "The page never names a concrete situation, team or use case where a named competitor is the better or "
        "right choice, or every such concession is undercut in the same breath. Generic hedges like 'every team "
        "is different' do not count as exits.",
        "The page names at least one concrete situation where a named competitor is the better or right choice "
        "and leaves it standing (for example 'ideal for teams that need X', 'choose X if...').",
    ),
    "no_admitted_weakness": (
        "Are the drawbacks of the publisher's own product missing, or rebutted as soon as they are mentioned?",
        "No drawback of the publisher's product is stated, or every stated drawback is softened in the same "
        "breath (for example 'can be overwhelming. That said, our intuitive interface...').",
        "At least one real drawback of the publisher's product is stated plainly and left standing. Comparison "
        "table cells count (for example 'Plugin ecosystem: Limited').",
    ),
    "vague_attacks": (
        "Are the page's criticisms of competitors vague, with no specifics, numbers or sources?",
        "Most criticisms of competitors are unfalsifiable, such as 'limited customization', 'lacks some "
        "collaboration features', 'outdated' or 'hard to use'.",
        "Most criticisms of competitors name something checkable (a missing feature, a price, a limit, a source), "
        "or the page does not criticize competitors at all.",
    ),
    "uneven_scrutiny": (
        "Does the page list clearly more drawbacks for competitors than for the publisher's product?",
        "Competitors get clearly more or harsher drawbacks, including when the publisher's product gets none and "
        "competitors get some.",
        "Drawbacks are roughly balanced between the publisher's product and competitors, or neither side gets any.",
    ),
}

QUESTIONS = {"best_at_everything": (
    "Does the page credit a named competitor with at least one strength, advantage or use case that it does not "
    "also claim for the publisher's product, and leave it standing?",
    "The page credits a competitor with something it is good at or better at, without claiming the same for the "
    "publisher in the same breath. Implicit credit counts: 'X is great for design-first visuals', 'X is free and "
    "open source', 'X integrates natively with Figma', 'X is ideal for technical diagrams', 'X helps you manage "
    "tasks, we help you visualize them', 'Excel is great for pivot tables', a comparison table row the competitor "
    "wins. Also true when the page compares only one specific feature and makes no claim beyond it.",
    "Every strength credited to a competitor is matched or beaten by the publisher in the same breath ('X may work "
    "for brainstorming, but it's no match for us', 'X excels at tasks, but we do everything X does'), or the page "
    "claims the publisher wins every category. Strengths a competitor has only relative to another competitor, "
    "never relative to the publisher, do not count. Ties and generic praise ('X is popular') do not count.",
)}
QUESTIONS.update({name: wording for name, wording in QUESTIONS_V1.items() if name != "crowns_itself"})
QUESTIONS["no_honest_exit"] = (
    "Does the page name at least one concrete situation where a named competitor is the better or right choice?",
    "The page names a concrete situation, team or use case where a named competitor is the better or right choice "
    "and leaves it standing (for example 'ideal for teams that need X', 'choose X if...', 'X is great for Y').",
    "No such situation is named, or every concession is undercut in the same breath ('X may work for "
    "brainstorming, but it's no match for us'). Generic hedges like 'every team is different' do not count.",
)
QUESTIONS["no_admitted_weakness"] = (
    "Does the page say, about the publisher's own product, something it cannot do, does not include, or does "
    "poorly, and leave it standing?",
    "The page states a weakness of the publisher's product in its own words: 'X does not offer automated alerts', "
    "'X is not a screening tool', 'no self-hostable export', 'coming soon', a 'Cons' or 'Limitations' list for X, or "
    "a comparison table cell where X has 'No' or 'Limited'.",
    "No such statement. Weaknesses that are only implied by praising a competitor ('choose Y if you want more "
    "structures') do not count: that is credit to the competitor, not an admission. Plan or pricing descriptions "
    "('the free plan includes 3 boards') do not count unless the page calls them a limitation. A weakness rebutted "
    "in the same breath ('can be overwhelming. That said, our intuitive interface...') does not count.",
)


# Appended to the questions where "yes" is the red flag. Dropping it (v2) cut uneven_scrutiny agreement from
# 93% to 81%, so it is part of the methodology.
NOT_A_COMPARISON = "If the page is not a comparison involving the publisher's product, answer false."


def wire_questions():
    questions = [{
        "type": "choice",
        "name": "page_type",
        "instructions": "What kind of page is this, from the publisher's point of view?",
        "choices": [{"value": value, "description": description} for value, description in PAGE_TYPES.items()],
    }]
    for name, (instructions, true_means, false_means) in QUESTIONS.items():
        guard = "" if name in INVERTED else f" {NOT_A_COMPARISON}"
        questions.append({
            "type": "predicate",
            "name": name,
            "instructions": f"{instructions}{guard}\n\nTrue means: {true_means}\nFalse means: {false_means}",
        })
    return questions


def load_products():
    with open(os.path.join(os.path.dirname(__file__), "domains.yml")) as handle:
        return {entry["company"]: entry["product_names"] for entry in yaml.safe_load(handle)}


def ask(client, api_key, payload, questions):
    for attempt in range(3):
        response = client.post(
            "https://api.openai.com/v1/decisions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": MODEL, "input": payload, "questions": questions},
        )
        if response.status_code not in (429, 500, 502, 503):
            break
        time.sleep(2 ** attempt * 2)
    response.raise_for_status()
    return response.json()


def classify_page(client, api_key, state):
    started = time.monotonic()
    body = ask(client, api_key, json.dumps(state), wire_questions())
    usage = body.get("usage") or {}
    usage["cached_tokens"] = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    body["usage"] = usage
    return body, time.monotonic() - started


def red_flag_probability(answers, name):
    probability = answers[name]["probability"]
    return 1 - probability if name in INVERTED else probability


def score(answers):
    """Red flags (p >= 0.8) and unclear answers (0.2 < p < 0.8), only for competitor comparisons."""
    if answers.get("page_type", {}).get("choice") != "competitor_comparison":
        return None, None
    probabilities = [red_flag_probability(answers, name) for name in QUESTIONS]
    return sum(p >= RED_FLAG for p in probabilities), sum(OK < p < RED_FLAG for p in probabilities)


def main():
    pages_path, fetch_dir, out_path = sys.argv[1:4]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    api_key = openai_api_key()
    products = load_products()
    with open(pages_path) as handle:
        pages = list(csv.DictReader(handle))
    with open(os.path.join(fetch_dir, "fetch.csv")) as handle:
        titles = {row["page_id"]: row["title"] for row in csv.DictReader(handle)}

    def run(page):
        with open(os.path.join(fetch_dir, "text", f"{page['page_id']}.md"), encoding="utf-8") as handle:
            text = handle.read()[:MAX_TEXT_CHARS]
        state = {
            "publisher": page["company"],
            "publisher_products": products.get(page["company"], [page["company"]]),
            "note": "The page is published on the publisher's own website.",
            "url": page["url"],
            "title": titles.get(page["page_id"], ""),
            "page_text": text,
        }
        try:
            body, elapsed = classify_page(api_client, api_key, state)
            return page, body, elapsed, ""
        except Exception as error:  # keep the batch going
            return page, {}, 0.0, str(error)[:200]

    started = time.monotonic()
    with httpx.Client(timeout=90) as api_client, ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(run, pages))
    total_s = time.monotonic() - started

    tokens, latencies, cached = [], [], 0
    with open(out_path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["page_id", "company", "url", "methodology", "page_type", "page_type_confidence",
                         *QUESTIONS, "score", "unclear", "input_tokens", "seconds", "error"])
        for page, body, elapsed, error in results:
            answers = {answer["name"]: answer for answer in body.get("answers", [])}
            page_type = answers.get("page_type", {})
            flags, unclear = score(answers) if answers else (None, None)
            input_tokens = (body.get("usage") or {}).get("input_tokens")
            cached += (body.get("usage") or {}).get("cached_tokens", 0)
            if input_tokens:
                tokens.append(input_tokens)
                latencies.append(elapsed)
            writer.writerow([
                page["page_id"], page["company"], page["url"], METHODOLOGY_VERSION,
                page_type.get("choice", ""), page_type.get("confidence", ""),
                *(f"{red_flag_probability(answers, name):.3f}" if name in answers else "" for name in QUESTIONS),
                "" if flags is None else flags, "" if unclear is None else unclear,
                input_tokens or "", f"{elapsed:.2f}", error,
            ])

    errors = sum(1 for result in results if result[3])
    print(f"{len(results)} pages in {total_s:.1f}s with {workers} workers, {errors} errors")
    if tokens:
        uncached = sum(tokens) - cached
        print(f"median {statistics.median(latencies):.2f}s/page, {sum(tokens):,} input tokens, {cached:,} cached "
              f"(~${uncached / 1e6 * 0.10 + cached / 1e6 * 0.01:.3f} at $0.10/M uncached, $0.01/M cached)")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
