# thebiasindex.com benchmark results

> Every benchmark run, in the order it happened, including the versions that failed. The current methodology is v8;
> its numbers on unseen pages are summarized in `docs/METHODOLOGY.md` ("How reliable is it") and in the last section
> below.
>
> Sets: `benchmark/tuning` (100 pages, used to tune the wording), then three sets never used for tuning:
> `benchmark/heldout` (41 pages), `benchmark/fresh2` ("fresh test set", 74 pages) and `benchmark/fresh3` ("third test
> set", 55 pages). Each set's labels were committed before Luna ran on it. That work started in a private
> repository, so those commits aren't in this repository's history; git timestamps are self-reported anyway, so the
> stronger check is that every label and its quoted reason is published here.

## The gold set

- **100 pages from 13 companies,** drawn at random (fixed seed) from URL-pattern buckets in each company's sitemap,
  before anyone read them (`select_benchmark.py`, `pages.csv`).
- **Labels:** `gold.jsonl`, written by Claude (`claude-opus-5-5`) from the extracted page text, following
  `docs/LABELING_GUIDELINES.md`. Every answer has a one-line reason that quotes the page. The labels were finished before any
  Luna output for these pages was looked at.
- **Page types:** 72 competitor comparisons, 17 educational, 4 other, 3 third-party comparisons, 2 hubs, 2 own-plan
  comparisons.
- **Gold scores** (red flags out of 5) on the 72 competitor comparisons: 0 → 14 pages, 1 → 3, 2 → 7, 3 → 18,
  4 → 13, 5 → 17.

## Results by methodology version

| Version | Change | Worst question | Page type | Score ±1 | Unclear | Pass |
|---|---|---|---|---|---|---|
| v1 | Five questions as written in the spec, one request | 83% (defused_drawbacks) | 96% | 89% | 13% | no |
| v2 | Ask `no_honest_exit` and `defused_drawbacks` positively; dropped the "not a comparison → false" guard | 81% (uneven_scrutiny) | 96% | 90% | 10% | no |
| v3 | Also ask `uneven_scrutiny` positively | 68% (uneven_scrutiny) | 96% | 93% | 8% | no |
| v4 | v2 wording, one request per question | 81% (identical answers to v2) | 96% | 90% | 10% | no |
| **v5** | v2 wording plus the guard restored on the three "yes = red flag" questions | **91%** | **96%** | **93%** | **12%** | **yes** |

v5 per question (agreement on answers Luna didn't mark unclear):

| Question | Agreement | Unclear |
|---|---|---|
| crowns_itself | 94% (66/70) | 2 |
| no_honest_exit | 97% (68/70) | 2 |
| defused_drawbacks | 91% (63/69) | 3 |
| vague_attacks | 96% (49/51) | 21 |
| uneven_scrutiny | 93% (51/55) | 17 |

Overall agreement 94%. Mean page score: gold 2.89, Luna 2.68. Cost: $0.02 and 5 seconds for 100 pages
(434k input tokens, 274k of them served from the prompt cache).

## What we learned

1. **Negative questions fail.** v1's "Are the drawbacks of the publisher's product *missing*, or rebutted...?"
   was answered "yes" on 11 pages with a plainly labeled drawback, including Lucid's "Cons: advanced data features
   require an Enterprise plan". Asking "Does the page state at least one drawback... and leave it standing?" and
   counting a confident "no" as the red flag fixed it (83% → 91%). The same applied to `no_honest_exit` (92% → 97%).
2. **Not every question can be flipped.** "Does the page give... roughly the same amount of criticism?" (v3) was
   answered "no" on almost every page. `uneven_scrutiny` stays in its original form.
3. **One sentence matters.** Removing "If the page is not a comparison involving the publisher's product, answer
   false" from the "yes = red flag" questions cut `uneven_scrutiny` from 93% to 81%. It's part of the method now.
4. **Questions don't interact.** One request per question (v4) returned exactly the same answers as one request
   with all questions (v2). A single request per page is used.
5. **Text extraction is part of the method.** trafilatura dropped most of Miro's and ClickUp's comparison tables
   and all but one testimonial on Excalidraw's page. The v1 extraction takes `<main>` (else the largest
   `<article>`, else `<body>`) and removes navigation, footers, scripts and forms (`fetch_pages.py`).

## Remaining disagreements (v5)

22 items across 19 pages, listed in `review_queue.csv` with Claude's reasons:

- **Page type (4):** Luna calls Ponder's three third-party comparisons (Grammarly vs Paperpal, Notion vs Obsidian,
  NotebookLM vs Obsidian) competitor comparisons because each ends with a Ponder pitch, and treats Smartsheet's
  gated comparison-video form as a comparison.
- **crowns_itself (4):** monday's Trello page, Lucidscale vs Hava and Creately's draw.io list (gold: crowned, Luna:
  no); draw.io's single-feature Gliffy post (gold: scoped, Luna: crowned).
- **defused_drawbacks (6), no_honest_exit (2), vague_attacks (2), uneven_scrutiny (4):** mostly judgment calls on
  one caveat in a table cell, or a concession in a different domain ("Excel is great for pivot tables").

## AI panel review (2026-10-28)

`ai_review.py` had two judges from other model families label all 100 pages with the labeling guidelines: GPT-6.1 Sol
(OpenAI) and Gemini 3.1 Pro (Google). With Claude's labels they form a three-vote panel; Luna doesn't vote. 200
calls, 5 minutes, about $4.

- Agreement with Claude's labels: GPT-6.1 Sol 93%, Gemini 3.1 Pro 89%.
- No item was split. On 24 pages (33 answers) both judges agreed with each other against Claude, so the panel
  label replaces Claude's. Most are `uneven_scrutiny` on Ponder pages (Claude was too lenient) and
  `vague_attacks` (Claude called specific criticisms vague).
- **Luna v5 against the panel labels still passes:** worst question 90%, page type 97%, score within ±1 93%,
  unclear 13%, overall 93%.
- Panel labels live in `panel.jsonl` (every vote with reasons) and `reviews.jsonl` (reviewer `ai-panel`).
  `evaluate.py --reviews benchmark/reviews.jsonl` scores Luna against them.

The panel is three models agreeing, not a person. A human spot-check of the 24 overturned pages (review app,
"Panel overturned Claude" view) is the cheapest way to say "checked by a person".

**Human spot-check (David Baussart, 3 of the 24 overturned pages):** 16 of 18 answers agree with the panel. Both
disagreements are `crowns_itself` on Miro alternatives pages (p007, p009), where the person sided with Claude:
listing Miro as "Alternative #1" with praise counts as crowning. So the panel's overrides are not reliable
enough to accept unchecked. With the person's labels applied, Luna v5 still passes: worst question 91%, page
type 97%, score within ±1 93%, unclear 13%, overall 94%.

## Files

Each `benchmark/<set>/` folder holds:

| File | What |
|---|---|
| `pages.csv` | The pages: id, company, sampling bucket, URL |
| `gold.jsonl` | Claude's labels, with a quoted reason per answer |
| `luna_v*.csv` | Luna's answers (red-flag probabilities) for each methodology version run on the set |
| `panel.jsonl` | The GPT-6.1 Sol and Gemini 3.1 Pro votes |
| `reviews.jsonl` | Label changes from the panel and from human review, with who made them |
| `review_queue.csv` | (tuning set) Close calls queued for human review |

Raw HTML and extracted text are not committed: they're the vendors' content. Re-fetch with
`uv run pipeline/fetch_pages.py benchmark/<set>/pages.csv OUT_DIR`. Pages change, so a re-fetch can differ from
what was labeled.

## Held-out test (2026-10-28): methodology v5 fails

41 pages from 10 companies not in the benchmark (Airtable, Canva, Coda, Figma, Linear, MindMeister, Taskade,
Wrike, Xmind, tldraw; Basecamp and Gamma had no candidates), sampled at random per company
(`select_benchmark.py --heldout`). Claude's labels were committed before Luna ran. Files:
`benchmark/heldout/`.

| | Against Claude's labels | Against panel-adjusted labels | Target |
|---|---|---|---|
| crowns_itself | **59%** | **64%** | ≥ 90% |
| no_honest_exit | 96% | 96% | ≥ 90% |
| defused_drawbacks | 100% | 100% | ≥ 90% |
| vague_attacks | 85% | 85% | ≥ 90% |
| uneven_scrutiny | 90% | 95% | ≥ 90% |
| Page type | 95% | 95% | ≥ 95% |
| Score within ±1 | 74% | 74% | ≥ 90% |

- **`crowns_itself` is the failure,** in both directions: Luna misses headline superlatives on otherwise fair
  pages ("the best Miro alternative", "FigJam is the new Jamboard", Linear's "replacing Jira") and flags
  conditional or split verdicts ("Xmind is a better alternative when...", Taskade's "Choose Bolt.new if...").
  The AI panel sided with Claude on 8 of these 9 pages, so this is a Luna weakness, not label noise.
- `vague_attacks` misses are all Xmind's template pages (3 of 20).
- Only 23 pages were competitor comparisons, so one page moves a question by 4-5 points. The next held-out set
  should be larger.
- Not tuned on: per the method, changing v5 to fix these pages would make this set useless as a test. A new
  version must be tuned on the benchmark and confirmed on a fresh held-out set.

## Methodology v6/v7: "best at everything" (2026-10-29)

Question 1 changed from "crowns itself" to "best at everything" (see `../METHODOLOGY.md`). Both gold sets were
relabeled for question 1 and committed before Luna ran: 20 of 72 benchmark answers and 4 of 24
held-out answers flipped. The old labels are kept under `superseded_v5` in `gold.jsonl`.

| Version | Question 1 agreement | Score within ±1 | Unclear | Notes |
|---|---|---|---|---|
| v6 | 84% (59/70) | 89% | 12% | Luna only counted explicit "X is better than us"; missed "FigJam integrates seamlessly with Figma" |
| v7 | 89% (59/66) | 92% | 14% | Implicit credit counts; misses now lean lenient (generic rival pros counted as concessions) |

Other questions are unchanged (97%, 91%, 96%, 93%). v7 is one page short of the 90% target on question 1. Not tuned
further to avoid fitting individual pages; the held-out set (relabeled, not yet run) and a fresh set decide.

## Fresh test set (2026-10-29): v7 passes question 1, fails on "defused drawbacks"

74 pages from 12 companies never used before (Consensus, Framer, Loom, Mindomo, Nuclino, Penpot, Plane, Shortcut,
SmartDraw, Teamwork.com, Visme, Zoho Projects). Pipedrive answered 429 to every request, even with a browser user
agent, and was dropped. Zoho served French pages at English URLs (geo-targeting), which are labeled `other`.
Labels committed before Luna ran. 46 competitor comparisons. Files: `benchmark/fresh2/`.

Excluding the 6 French Zoho pages (the crawler filters non-English before Luna):

| | Result | Target |
|---|---|---|
| best_at_everything | **90%** (37/41) | ≥ 90% |
| no_honest_exit | 93% | ≥ 90% |
| defused_drawbacks | **70%** (26/37) | ≥ 90% |
| vague_attacks | 97% | ≥ 90% |
| uneven_scrutiny | 91% | ≥ 90% |
| Page type gate | 96% | ≥ 95% |
| Score within ±1 | 78% | ≥ 90% |
| Unclear | 15% | ≤ 15% |

- **Question 1 (v7) holds up on fresh data.**
- **`defused_drawbacks` fails, in one direction:** on 10 of 11 misses Luna says the vendor admits a drawback where
  the labels say it doesn't. On these pages the vendor's limits are only implied by credit given to a rival ("Choose
  XMind if you want more structures") or by plan facts ("Free supports up to 12 users"). Luna counts those; the
  guidelines don't. This also pulls Luna's mean score down (1.67 vs 2.35) and causes most score-within-±1 misses.
  The question needs to say explicitly that credit to a competitor belongs to question 1, not question 3.
- Page type: the three Nuclino "X vs Y" pages that end with "consider Nuclino" are called competitor comparisons,
  the same closing-pitch pattern as Ponder's third-party posts in the benchmark.
- Crawler notes: honor 429 and mark the company "unreachable"; send `Accept-Language: en` and drop pages whose
  `<html lang>` isn't English before classification.

## Methodology v8 and the third test set (2026-10-29)

v8 renames question 3 **No admitted weakness** and limits it to what the vendor says about itself (credit to a rival
and plan facts don't count). Benchmark: question 3 91%, nothing else changed. Fresh-set diagnostic (already seen):
question 3 went from 70% to 78%; two of the remaining misses were labeling errors (Mindomo's own tables mark Mindomo
"No" on several rows) and were corrected.

Third test set: 55 pages from 12 new companies (Beautiful.ai, Conceptboard, Craft, Guru, Hive, Nifty, Pitch, Prezi,
ProofHub, Stormboard, Todoist, Venngage), 29 competitor comparisons. Labels committed before Luna ran.
Guru publishes 1,312 programmatic third-party "X vs Y" pages under `/reference/`.

| | v8 vs Claude | v8 vs panel-adjusted labels | Target |
|---|---|---|---|
| best_at_everything | 78% | **68%** | ≥ 90% |
| no_honest_exit | 81% | 93% | ≥ 90% |
| no_admitted_weakness | **92%** | **93%** | ≥ 90% |
| vague_attacks | 80% | 85% | ≥ 90% |
| uneven_scrutiny | 83% | 96% | ≥ 90% |
| Page type gate | 95% | 96% | ≥ 95% |
| Score within ±1 | 83% | **90%** | ≥ 90% |
| Unclear | 14% | 15% | ≤ 15% |

- 18 of 21 question-level disagreements with Claude were on pages Claude had flagged as close calls. The AI panel
  (GPT-6.1 Sol + Gemini 3.1 Pro) overturned Claude on 16 pages; agreement with Claude 86% for both judges.
- **Question 3 is fixed.**
- **Question 1 is Luna's weak point:** it counts a concession that is taken back in the next breath ("Figma Slides is
  intuitive for people who already use Figma. But...", "Asana is great at everyday task management, [but] it
  lacks..."). The panel judges catch this; Luna doesn't. Same pattern as Airtable in the held-out set.
- **v9 (tried, parked):** a second Luna check, "does the page claim the vendor also does whatever the competitor is
  good at?", combined with question 1. Benchmark question 1 93% but unclear rose to 17%; third set question 1 78%,
  unclear 18%. Not adopted.

## Consolidated (2026-10-29): Luna v8 on every set, panel rerun with current guidelines

All four sets scored with the same wording (v8) and reviewed by the same panel (GPT-6.1 Sol + Gemini 3.1 Pro,
current guidelines). French Zoho pages excluded. "Unseen pooled" = held-out + fresh 2 + fresh 3.
Regenerate with `uv run --no-project --with pandas python -I pipeline/consolidated.py`.

### Luna v8 against Claude labels
|  | Benchmark (tuned) | Held-out | Fresh 2 | Fresh 3 | Unseen pooled |
|---|---|---|---|---|---|
| page_type | 96% (96/100) | 95% (39/41) | 96% (65/68) | 95% (52/55) | **95% (156/164)** |
| best_at_everything | 89% (59/66) | 87% (20/23) | 90% (37/41) | 78% (21/27) | **86% (78/91)** |
| no_honest_exit | 97% (68/70) | 96% (22/23) | 93% (42/45) | 81% (22/27) | **91% (86/95)** |
| no_admitted_weakness | 91% (62/68) | 100% (20/20) | 84% (31/37) | 92% (24/26) | **90% (75/83)** |
| vague_attacks | 96% (49/51) | 85% (17/20) | 97% (37/38) | 80% (16/20) | **90% (70/78)** |
| uneven_scrutiny | 93% (51/55) | 90% (18/20) | 91% (31/34) | 83% (20/24) | **88% (69/78)** |
| score_pm1 | 92% (66/72) | 87% (20/23) | 80% (37/46) | 83% (24/29) | **83% (81/98)** |
| unclear | 14% (50/360) | 8% (9/115) | 15% (35/230) | 14% (21/145) | **13% (65/490)** |

### Luna v8 against panel-adjusted labels
|  | Benchmark (tuned) | Held-out | Fresh 2 | Fresh 3 | Unseen pooled |
|---|---|---|---|---|---|
| page_type | 96% (96/100) | 95% (39/41) | 97% (66/68) | 96% (53/55) | **96% (158/164)** |
| best_at_everything | 89% (59/66) | 87% (20/23) | 83% (35/42) | 68% (19/28) | **80% (74/93)** |
| no_honest_exit | 97% (68/70) | 96% (22/23) | 93% (43/46) | 93% (26/28) | **94% (91/97)** |
| no_admitted_weakness | 91% (62/68) | 95% (19/20) | 92% (35/38) | 93% (25/27) | **93% (79/85)** |
| vague_attacks | 88% (45/51) | 85% (17/20) | 92% (36/39) | 85% (17/20) | **89% (70/79)** |
| uneven_scrutiny | 93% (51/55) | 95% (19/20) | 94% (32/34) | 96% (24/25) | **95% (75/79)** |
| score_pm1 | 90% (65/72) | 87% (20/23) | 87% (41/47) | 90% (27/30) | **88% (88/100)** |
| unclear | 14% (50/360) | 8% (9/115) | 15% (36/235) | 15% (22/150) | **13% (67/500)** |

On unseen pages against panel-adjusted labels, everything passes or is within a point except **best_at_everything
(80%)**, which also pulls score-within-±1 to 88%. Its misses are concessions taken back in the next sentence.
