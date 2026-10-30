# How thebiasindex.com scores a comparison page

> **Status:** methodology v8. Scored by OpenAI's `gpt-6-luna` classifier. Full benchmark history in
> [`docs/RESULTS.md`](RESULTS.md).

## The starting point

A comparison page on a vendor's own website is going to argue that the vendor is better at something. That's the
job of the page, and it isn't what we score. We score whether the page is **honest about the rest**: what the
competitor does better, who should pick the competitor, what the vendor's own product is bad at, and whether the
criticism of the competitor is specific and proportionate.

Whimsical's post [The anatomy of a SaaS comparison page](https://whimsical.com/blog/the-anatomy-of-a-saas-comparison-page)
put the failure in one line: *"every product is simultaneously easier to learn than everyone
else, more powerful than everyone else, better for enterprises, and somehow also better for small teams.
Statistically, this should not be possible."* The five questions turn that into checks a model can answer from the
page text alone.

## The five questions

Each question is a yes/no. On the site, **yes is always a red flag 🚩**, and a page's score is simply how many red
flags it has, from 0 to 5. Fewer is fairer.

| # | Question (as shown on the site) | Red flag when… |
|---|---|---|
| 1 | **Best at everything:** Does the page claim the vendor's product wins or ties on everything it compares? | No area is conceded where the competitor is stronger. |
| 2 | **No honest exit:** Does the page leave out every situation where a competitor would be the better choice? | Nobody is told to pick the competitor. |
| 3 | **No admitted weakness:** Does the page avoid saying anything the vendor's own product can't do or does poorly? | You can't quote a single limitation the vendor admits about itself. |
| 4 | **Vague attacks:** Are the criticisms of competitors vague, with no specifics, numbers or sources? | Rivals are "clunky", "limited", "outdated", with nothing checkable. |
| 5 | **Uneven scrutiny:** Does the competitor get clearly more criticism than the vendor's product? | One side gets the cons, the other gets the praise. |

## How they complement each other

The questions cover a 2×2 grid, strengths and weaknesses for each side, plus one check on balance:

| | **Vendor's product** | **Competitor** |
|---|---|---|
| **Strengths** | Does the vendor claim *all* the strengths, leaving none to the competitor? (**Best at everything**) | Does the page admit the competitor is the right pick for *someone*? (**No honest exit**) |
| **Weaknesses** | Does the vendor admit *any* weakness of its own? (**No admitted weakness**) | Are the competitor's weaknesses stated as facts or as insinuations? (**Vague attacks**) |
| **Across both** | Is criticism proportionate between the two? (**Uneven scrutiny**) | |

- **1 and 2 both ask whether the competitor gets anything,** from two angles. Question 1 is about **what**: a
  feature, price, platform, integration or ease of use where the competitor is stronger. Question 2 is about
  **who**: a team, use case or situation where the competitor is the better pick. A page can concede "Xmind offers
  more diagram types" without telling anyone to choose Xmind, and a page can say "small teams should stick with
  Trello" while claiming to win on every feature. They often go together, and that's fine: a page that fails both
  gives the competitor nothing at all.
- **1 and 3 are kept apart on purpose.** Question 1 is about the competitor: is it credited with anything ("Xmind
  offers more diagram types")? Question 3 is about the vendor, in its own words: does it say what its product
  can't do ("SmartDraw: 3D floor plans — No")? Credit to a competitor only answers question 1, even though it
  implies a weakness, so one sentence is never counted twice. A quick test for question 3: *can you quote a
  sentence where the vendor describes its own limitation?*
- **4 is about the quality of criticism, 5 about its quantity.** A page can attack with precise, checkable facts and
  still pile them all on one side (4 passes, 5 fails), or criticize both sides evenly but in mush (5 passes, 4
  fails).

What a **fair page** looks like: it wins where the vendor is strong, concedes where the competitor is strong, tells
some readers to pick the competitor, admits at least one real weakness, criticizes with facts, and keeps the
criticism roughly even. That page scores 0. It is still a sales page; it just isn't a misleading one.

What a **typical biased page** looks like: "Alternative #1: us", a feature table where the vendor ticks every row,
two "cons" for the vendor each followed by "That said…", and three vague cons per competitor. That page scores 5.

## Which pages are checked

- **Companies** come from a hand-maintained list ([`pipeline/domains.yml`](../pipeline/domains.yml)), each keyed by its domain. A page only
  counts for a company if it is on that company's own hosts; URLs a sitemap lists on other sites, and pages that
  redirect off the company's domains, are never scored under its name.
- **Discovery:** the sitemaps named in each host's `robots.txt` (else `/sitemap.xml`), followed recursively. A URL is
  a *candidate page* if its path contains `-vs-`, `/vs/`, `versus`, `alternative`, `compare`, `comparison`, `switch-to` or
  `/switch`. Known gap: comparison pages without one of these words in the URL are missed. Pages a sitemap leaves
  out are still found when the company's homepage links to them (its navigation and footer), or can be
  added by hand (`linear.app/switch`).
- **Excluded before fetching:** localized paths and sitemaps (`/de/`, `/pt-br/`, `sitemap_fr.xml`), and
  user-generated content or template galleries on vendor domains (Figma Community, Coda's `/@` docs, Prezi
  presentations).
- **Regional copies count once:** URLs that differ only by a market as the first path segment (`zoho.com/ae/...`,
  `workday.com/en-gb/...`) are one page, and the shortest URL is kept.
- **Every candidate is read,** every week, to tell whether it is a *compare page*: one that compares the company
  with a named rival. Only compare pages are scored. No sampling, no cap per company. A page found in an earlier
  week is checked again even if this week's sitemap leaves it out (some sitemaps vary by visitor location); it
  drops out once the page is gone.
- **Fetching:** as `BiasIndexBot`, honoring `robots.txt`, one request at a time per host and at least a second apart
  (or the site's `Crawl-delay`), asking for English. A host that blocks three requests in a row is marked
  unreachable rather than retried harder. A company whose every page is blocked, or that opts out in `robots.txt`,
  shows as "crawler blocked", with no score. Details for site owners: [`/bot`](https://thebiasindex.com/bot).
- **Scored only if** the page answers HTTP 200, its `<html lang>` is English (or missing), at most 30% of the
  letters in its text are non-Latin (pages tagged English but written in Japanese, say), and it has at least 200
  characters of text. Everything else is stored with the reason and shown as not scored.
- **Text:** the page's `<main>`, else its largest `<article>`, else `<body>`, without navigation, footer, scripts and
  forms, as Markdown, up to 120,000 characters (about 30k tokens). A generic extractor (trafilatura) was tried
  first and dropped whole comparison tables.
- **Duplicates:** every URL counts. The same text published at two URLs is two pages; publishing a one-sided page
  twice is counted twice.
- **Re-scoring:** a page is sent to the model again only when its text or the methodology version changes.

## Scoring rules

- **Which pages are scored:** only pages that compare the vendor's product with named competitors, or list
  alternatives that include the vendor's product. Educational pages ("Scrum vs Kanban"), the vendor's own plan
  comparisons, hub pages and third-party comparisons are counted separately and never scored.
- **Thresholds:** a red flag needs at least 80% model confidence. At 20% or less the answer is "no". Anything in
  between is shown as **unclear** and does not count, so pages get the benefit of the doubt.
- **Company scores:** the **total number of red flags** across all of a company's competitor comparisons, which
  ranks the leaderboard: forty pages with four red flags each weigh more than three pages with five. Red flags
  **per page** (0–5) and the page count are shown next to it. Colors follow red flags per page: 1 or fewer is green,
  3 or more is red, in between is amber.
- **Fair players:** 1 red flag per page or fewer, across at least 3 scored pages. They are not ranked: a large
  total built from many fair pages isn't a red flag.
- **Not scored:** whether claims are true (we don't fact-check, so "Trello has no integrations" doesn't change a
  score), and whether the page grades a competitor on things outside its category. Comparison tables drawn with icons
  only come through as empty cells. These are known gaps.

## How reliable is it

Every methodology version is tested against labeled pages before it scores anything. The full log, failures
included, is in [`docs/RESULTS.md`](RESULTS.md); every label and every model output is in [`benchmark/`](../benchmark/).

- **Who labeled the pages.** Labels were written by Claude (`claude-opus-5-5`) from the page text, following
  [`docs/LABELING_GUIDELINES.md`](LABELING_GUIDELINES.md), with a one-line reason quoting the page for every answer. They are model-made, not
  hand-made.
- **Cross-check.** Two models from other companies, GPT-6.1 Sol (OpenAI) and Gemini 3.1 Pro (Google), labeled the
  same pages independently. Where both disagreed with Claude, their answer replaced Claude's ("panel-adjusted
  labels").
- **Unseen pages.** The question wording was tuned on a first set of 100 pages from 13 companies. The numbers below
  come from three later sets the wording was never tuned on: 170 pages sampled from 34 other companies (164 could be
  fetched), each set labeled and committed before the model ran on it.
- **Targets set in advance:** at least 90% agreement per question, 95% on page type, 90% of page scores within one
  red flag, and at most 15% unclear answers.

Agreement on the unseen pages. Question checks only apply to competitor comparisons, and leave out answers the model
marked unclear, so each rests on 79 to 97 answers:

| Check | vs panel-adjusted labels | vs Claude's labels | Target |
|---|---|---|---|
| Is this a competitor comparison at all? | 96% (158 of 164) | 95% (156 of 164) | 95% |
| 1. Best at everything | **80%** (74 of 93) | 86% (78 of 91) | 90% |
| 2. No honest exit | 94% (91 of 97) | 91% (86 of 95) | 90% |
| 3. No admitted weakness | 93% (79 of 85) | 90% (75 of 83) | 90% |
| 4. Vague attacks | **89%** (70 of 79) | 90% (70 of 78) | 90% |
| 5. Uneven scrutiny | 95% (75 of 79) | 88% (69 of 78) | 90% |
| Page score within one red flag | **88%** (88 of 100) | 83% (81 of 98) | 90% |
| Unclear answers | 13% (67 of 500) | 13% (65 of 490) | at most 15% |

Reproduce these with `uv run pipeline/consolidated.py` ([source](../pipeline/consolidated.py)).

Against the panel-adjusted labels, three checks miss their target by a few points, and we'd rather say so than hide it. Question 1 is the
weakest: the model sometimes counts a concession that the page takes back in the next sentence ("X is great for Y.
But…") as a real one, so it misses some red flags rather than adding them. Unclear answers never count.

## How the model is asked

Luna (OpenAI's `gpt-6-luna` via the Decisions API) answers all five in one request per page. Two questions are
asked the positive way round, because Luna answered negative wording unreliably, and the answer is inverted:

| Question | Luna is asked | Red flag |
|---|---|---|
| 1. Best at everything | Does the page credit a named competitor with a strength it doesn't also claim for the vendor? | confident **no** |
| 2. No honest exit | Does the page name a situation where a named competitor is the better choice? | confident **no** |
| 3. No admitted weakness | Does the page say, about the vendor's own product, something it can't do or does poorly, and leave it standing? | confident **no** |
| 4. Vague attacks | Are the criticisms of competitors vague? | confident **yes** |
| 5. Uneven scrutiny | Does the competitor get clearly more drawbacks? | confident **yes** |

The exact wording is in [`pipeline/classify.py`](../pipeline/classify.py); the labeling rules a person (or the review panel) applies are
in [`docs/LABELING_GUIDELINES.md`](LABELING_GUIDELINES.md).

## History

| Version | Change |
|---|---|
| v1 | Five questions as first written; question 1 was "Crowns itself: does the page present the vendor as the best choice overall?" |
| v5 | Questions 2 and 3 asked positively; passed the 100-page benchmark |
| v5 held-out | Failed on "crowns itself" (64%): it flagged every page with a confident headline, while vendor pages are *supposed* to claim they're better at something |
| v6 | Question 1 becomes **Best at everything**: the red flag is conceding nothing, not claiming something. Benchmark: 84% on question 1 (Luna only counted explicit "X beats us" concessions) |
| v7 | Luna's wording counts implicit credit ("X is great for design-first visuals", "X is free"). Benchmark: 89% on question 1 (target 90%), score within ±1 92%, other questions unchanged |
| **v8** | Question 3 renamed **No admitted weakness** and limited to what the vendor says about itself. Fresh-set v7 run: Luna counted weaknesses implied by credit to rivals, and plan facts, as admissions (70%) |
