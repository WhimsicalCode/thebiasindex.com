// One company's results in the words and numbers the site uses everywhere: its page, /<domain>.json and
// /llms.txt all read from here, so an LLM quoting the JSON says exactly what a reader sees on the page.
import {
  byRedFlags,
  type Company,
  companies,
  companyPath,
  latestRun,
  MADE_BY,
  mentionsFor,
  notMeasured,
  type Page,
  type Pair,
  pagesFor,
  pairPath,
  QUESTIONS,
  RULES,
  silentCompanies,
  unrankedStatus,
} from "@/lib/db"
import { absoluteUrl } from "@/lib/deploy"
import { fmt, ordinal, perPage, redFlags } from "@/lib/format"
import { REPO_URL } from "@/lib/site"

const ANSWER = { flag: "yes", ok: "no", unclear: "unclear" } as const

// Two words, used the same way everywhere. A candidate page is one whose address looks like a comparison ("vs",
// "alternative", "compare", "switch"). A compare page is a candidate that turns out to compare the company with a
// named rival: only compare pages are scored.

/** What a candidate page that isn't a compare page turned out to be, by page type, in the order we list them. */
export const NOT_COMPARE: { kind: string; label: string }[] = [
  { kind: "third_party_comparison", label: "Compares other companies’ products" },
  { kind: "educational", label: "A guide or article" },
  { kind: "own_products", label: "About its own plans or products" },
  { kind: "hub", label: "A list of comparisons" },
  { kind: "other", label: "Something else" },
  { kind: "unreadable", label: "Couldn’t be read" },
]

/** A candidate page's kind: its page type, or "unreadable" when we couldn't read it. */
export function kindOf(page: Page): string {
  return page.pageType ?? "unreadable"
}

/** What a candidate page that isn't a compare page turned out to be, in a few words. */
export function whatItIs(page: Page): string {
  if (!page.pageType)
    return page.skipReason === "not checked yet"
      ? "Not read yet: we ran out of time on this site"
      : `Couldn’t be read: ${page.skipReason ?? "unknown"}`
  return NOT_COMPARE.find(k => k.kind === page.pageType)?.label ?? "Something else"
}

/** Rank among companies with at least 3 scored comparisons (1 = most red flags), or null. */
export function rankOf(company: Company): number | null {
  const index = byRedFlags(companies()).findIndex(c => c.slug === company.slug)
  return index < 0 ? null : index + 1
}

/** Where a company stands in a few words: "5th of 37 by total", or why it isn't ranked ("Fair player"…). */
export function standingOf(company: Company): string {
  const ranked = byRedFlags(companies())
  const rank = rankOf(company)
  return unrankedStatus(company) ?? `${ordinal(rank ?? 0)} of ${ranked.length} by total`
}

export type Verdict = { headline: string; found: string; total: string }

/** The verdict under a company's name: one big sentence, where its pages come from, and what they add up to. */
export function verdictOf(company: Company): Verdict {
  const name = company.company
  const ranked = byRedFlags(companies())
  const rank = rankOf(company)
  const comparePages = (n: number) => `${fmt(n)} compare page${n === 1 ? "" : "s"}`
  const candidatePages = (n: number) => `${fmt(n)} candidate page${n === 1 ? "" : "s"}`
  if (company.status === "unreachable")
    return {
      headline: `We can’t read ${name}’s pages yet.`,
      found: `${name}’s website blocks our crawler, so nothing was scored.`,
      total: "",
    }
  if (company.status !== "ok")
    return {
      headline: `We can’t read ${name}’s pages yet.`,
      found: `We can’t read ${name}’s sitemaps or homepage, so we haven’t found its candidate pages.`,
      total: "",
    }
  if (company.scoredPages === 0)
    return company.candidates === 0
      ? {
          headline: `${name} publishes no compare pages.`,
          found: `We found no candidate pages on ${name}’s website, so there is nothing to score.`,
          total: "It isn’t ranked, and it isn’t penalised.",
        }
      : {
          headline: `${name} publishes no compare pages.`,
          found: `We found ${candidatePages(company.candidates)} on ${name}’s website, of which 0 are compare pages, so there is nothing to score.`,
          total: "It isn’t ranked, and it isn’t penalised.",
        }
  const read = company.scoredPages
  const ofWhich = read === company.candidates && read > 1 ? `all ${fmt(read)}` : fmt(read)
  const found =
    company.candidates < read
      ? `${name}’s sitemaps don’t list its compare pages this week. We scored ${comparePages(read)} before.`
      : `We found ${candidatePages(company.candidates)} on ${name}’s website, of which ${ofWhich} ${read === 1 ? "is a compare page" : "are compare pages"}. Those are the ones we score.`
  const together =
    read === 1
      ? `That page carries ${redFlags(company.biasLoad)}`
      : `Together they add up to ${redFlags(company.biasLoad)}`
  const total = company.fairPlayer
    ? `${together}. At ${perPage(company)} per page, ${name} is a fair player: one red flag per page or fewer.`
    : rank
      ? `${together}, the ${rank === 1 ? "" : `${ordinal(rank)} `}most of the ${ranked.length} companies we rank.`
      : `${together}. With fewer than three compare pages, ${name} isn’t ranked.`
  return {
    headline: `A typical compare page from ${name} raises ${perPage(company)} of our five red flags.`,
    found,
    total,
  }
}

/** Everyone against the company in one sentence, or "" when no other company's page is aimed at it. */
export function againstOf(company: Company): string {
  const name = company.company
  const { aimedAt, aimedAtPages } = mentionsFor(company.slug)
  if (aimedAtPages === 0) return ""
  const own =
    company.scoredPages > 0
      ? `${name} has ${fmt(company.scoredPages)} compare ${company.scoredPages === 1 ? "page" : "pages"} of its own.`
      : `${name} has no compare pages of its own.`
  return (
    `${fmt(aimedAtPages)} ${aimedAtPages === 1 ? "page" : "pages"} on ${fmt(aimedAt.length)} ` +
    `${aimedAt.length === 1 ? "company’s site is" : "companies’ sites are"} written for people looking at ` +
    `${name}: “${name} alternatives”, “X vs ${name}”. ${own}`
  )
}

/** "folk is listed as one option in 3 compare pages by Attio and Softr.", or "" when no other company lists it. */
export function listedOf(company: Company): string {
  const { listedIn, listedBy } = mentionsFor(company.slug)
  if (listedIn === 0) return ""
  const names = listedBy.map(c => c.company)
  const by =
    names.length <= 3
      ? names.join(names.length === 2 ? " and " : ", ").replace(/, ([^,]*)$/, " and $1")
      : `${names.slice(0, 3).join(", ")} and ${fmt(names.length - 3)} more`
  return `${company.company} is listed as one option in ${fmt(listedIn)} compare ${listedIn === 1 ? "page" : "pages"} by ${by}.`
}

/** The verdict as one paragraph: the meta description, /<domain>.json and llms.txt. */
export function summaryOf(company: Company): string {
  const { headline, found, total } = verdictOf(company)
  return [headline, found, total].filter(Boolean).join(" ")
}

/** The order of /companies and llms.txt: everyone with compare pages by total red flags (then compare pages), then
 * the companies with none, then the ones we can't measure yet. */
export function inListOrder(list: Company[]): Company[] {
  const read = list
    .filter(c => c.status === "ok" && c.scoredPages > 0)
    .sort((a, b) => b.biasLoad - a.biasLoad || b.scoredPages - a.scoredPages)
  return [...read, ...silentCompanies(list), ...notMeasured(list)]
}

/** Machine-readable report, served as /<domain>.json. */
export function reportOf(company: Company) {
  const run = latestRun()
  const candidates = pagesFor(company.slug)
  const pages = candidates.filter(p => p.pageType === "competitor_comparison")
  const others = candidates.filter(p => p.pageType !== "competitor_comparison")
  const checked = company.status === "ok"
  const mentions = mentionsFor(company.slug)
  return {
    domain: company.slug,
    company: company.company,
    aliases: company.aliases,
    category: company.category,
    url: absoluteUrl(companyPath(company)),
    summary: summaryOf(company),
    status: company.status,
    rank: rankOf(company),
    fair_player: company.fairPlayer,
    red_flags_total: checked ? company.biasLoad : null,
    red_flags_per_page:
      company.averageScore === null ? null : Number(company.averageScore.toFixed(2)),
    compare_pages: company.scoredPages,
    candidate_pages: company.candidates,
    run_date: run?.startedAt.slice(0, 10) ?? null,
    methodology: { version: run?.methodology ?? null, url: absoluteUrl("/methodology") },
    source: REPO_URL,
    questions: QUESTIONS.map((q, i) => ({ id: `q${i + 1}`, label: q.label, question: q.question })),
    pages: pages.map(p => ({
      url: p.url,
      title: p.title,
      red_flags: p.score,
      answers: Object.fromEntries(p.answers.map((a, i) => [`q${i + 1}`, ANSWER[a]])),
    })),
    // The candidate pages that aren't compare pages, kept apart so totals computed from `pages` match the above.
    other_candidate_pages: others.map(p => ({
      url: p.url,
      title: p.title,
      type: kindOf(p),
      what_it_is: whatItIs(p),
    })),
    // Other companies' compare pages aimed at this one ("X alternatives", "Y vs X"), and this one's aimed back.
    everyone_against: {
      summary: againstOf(company) || null,
      pages: mentions.aimedAtPages,
      companies: mentions.aimedAt.length,
      red_flags_per_page: round(mentions.aimedAtAverage),
      // Pages where it is one entry in a list: counted, but their red flags may be about the other entries.
      listed_in_pages: mentions.listedIn,
      listed_by: mentions.listedBy.map(c => c.slug),
      by_company: mentions.aimedAt.map(row => ({
        domain: row.company.slug,
        company: row.company.company,
        url: absoluteUrl(companyPath(row.company)),
        pages: row.pages.length,
        red_flags_per_page: round(row.averageScore),
        pages_aimed_back: row.back,
        page_list: row.pages.map(p => ({ url: p.url, title: p.title, red_flags: p.score })),
      })),
    },
    // The companies this one's own compare pages are aimed at.
    aims_at: mentions.aimsAt.map(row => ({
      domain: row.company.slug,
      company: row.company.company,
      url: absoluteUrl(companyPath(row.company)),
      pages: row.pages,
    })),
  }
}

// Pair pages (/<a>/vs/<b>): what two companies wrote about each other.

/** One side of a pair: who wrote the pages, about whom, and their red flags per page (null without pages). */
export type PairSide = { who: Company; whom: Company; pages: Page[]; perPage: number | null }

/** A difference in red flags per page smaller than this isn't called: with 1 to 3 pages a side, it's noise. */
const PAIR_GAP = 1

const averageOf = (pages: Page[]) =>
  pages.length ? pages.reduce((sum, p) => sum + (p.score ?? 0), 0) / pages.length : null

/** Both sides of a pair, in the pair's order. */
export function sidesOf(pair: Pair): [PairSide, PairSide] {
  return [
    { who: pair.a, whom: pair.b, pages: pair.aOnB, perPage: averageOf(pair.aOnB) },
    { who: pair.b, whom: pair.a, pages: pair.bOnA, perPage: averageOf(pair.bOnA) },
  ]
}

/** The verdict in one sentence: who writes about the other more fairly, or that only one of them writes at all. */
export function pairVerdictOf(pair: Pair): string {
  const [x, y] = sidesOf(pair)
  const A = pair.a.company
  const B = pair.b.company
  if (x.perPage === null || y.perPage === null) {
    const side = x.perPage === null ? y : x
    const n = side.pages.length
    return `Only ${side.who.company} has written about ${side.whom.company}${n > 1 ? `: ${fmt(n)} pages` : ""}.`
  }
  if (Math.abs(x.perPage - y.perPage) >= PAIR_GAP) {
    const [fair, unfair] = x.perPage < y.perPage ? [A, B] : [B, A]
    return `${fair} writes about ${unfair} more fairly than ${unfair} writes about ${fair}.`
  }
  if (x.perPage <= RULES.FAIR_AVERAGE && y.perPage <= RULES.FAIR_AVERAGE)
    return `${A} and ${B} write about each other fairly.`
  if (x.perPage > RULES.FAIR_AVERAGE && y.perPage > RULES.FAIR_AVERAGE)
    return `Neither ${A} nor ${B} writes fairly about the other.`
  return `${A} and ${B} write about each other about as fairly.`
}

/** Each side's numbers in a sentence: "Lucid’s 5 pages about Miro raise 3.6 of our five red flags per page." */
export function pairNumbersOf(pair: Pair): string {
  return sidesOf(pair)
    .filter(side => side.perPage !== null)
    .map(({ who, whom, pages, perPage }) =>
      pages.length === 1
        ? `${who.company}’s page about ${whom.company} raises ${redFlags(Number(perPage?.toFixed(0)))} of our five.`
        : `${who.company}’s ${fmt(pages.length)} pages about ${whom.company} raise ${perPage?.toFixed(1)} of our five red flags per page.`
    )
    .join(" ")
}

/** The verdict and the numbers: the meta description, the pair's JSON and llms.txt. */
export function pairSummaryOf(pair: Pair): string {
  return `${pairVerdictOf(pair)} ${pairNumbersOf(pair)}`
}

/** "We score the pages, not the products.", and that Whimsical made the index when it is one side. */
export function pairNoteOf(pair: Pair): string {
  const maker = [pair.a, pair.b].find(c => c.slug === MADE_BY)
  return `We score the pages, not the products.${maker ? ` ${maker.company} made The Bias Index and is scored by the same rules.` : ""}`
}

/** How many pages give the most common five answers, when that's most of them (at least 3, half or more): pages
 * stamped from one template. Null otherwise. */
export function sameAnswersOf(pages: Page[]): number | null {
  const counts = new Map<string, number>()
  for (const p of pages) {
    const key = p.answers.join(" ")
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  const top = Math.max(0, ...counts.values())
  return top >= 3 && top * 2 >= pages.length ? top : null
}

/** The one thing a buyer can check on a vendor's page: does it admit anything its own product can't do? From
 * question 3 ("Admits no weakness"), which is about the publisher, so it holds whichever rival the page is about.
 * Only clear passes count; an unclear answer isn't an admission. */
export function admitsWeaknessOf({ who, pages }: PairSide): string {
  const admits = pages.filter(p => p.answers[2] === "ok").length
  const A = who.company
  if (pages.length === 1)
    return `${A}’s page ${admits ? "admits something" : "admits nothing"} ${A} can’t do.`
  if (admits === 0) return `None of ${A}’s ${fmt(pages.length)} pages admit anything ${A} can’t do.`
  if (admits === pages.length)
    return `All ${fmt(pages.length)} of ${A}’s pages admit something ${A} can’t do.`
  return `${admits * 2 < pages.length ? "Only " : ""}${fmt(admits)} of ${A}’s ${fmt(pages.length)} pages ${admits === 1 ? "admits" : "admit"} something ${A} can’t do.`
}

/** Machine-readable pair, served as /<a>/vs/<b>.json. */
export function pairReportOf(pair: Pair) {
  const run = latestRun()
  return {
    url: absoluteUrl(pairPath(pair)),
    companies: [pair.a, pair.b].map(c => ({
      domain: c.slug,
      company: c.company,
      url: absoluteUrl(companyPath(c)),
    })),
    verdict: pairVerdictOf(pair),
    summary: pairSummaryOf(pair),
    run_date: run?.startedAt.slice(0, 10) ?? null,
    methodology: { version: run?.methodology ?? null, url: absoluteUrl("/methodology") },
    source: REPO_URL,
    questions: QUESTIONS.map((q, i) => ({ id: `q${i + 1}`, label: q.label, question: q.question })),
    sides: sidesOf(pair).map(side => ({
      publisher: side.who.slug,
      about: side.whom.slug,
      pages_count: side.pages.length,
      red_flags_per_page: round(side.perPage),
      admits_a_weakness: admitsWeaknessOf(side),
      pages: side.pages.map(p => ({
        url: p.url,
        title: p.title,
        red_flags: p.score,
        answers: Object.fromEntries(p.answers.map((a, i) => [`q${i + 1}`, ANSWER[a]])),
      })),
    })),
  }
}

const round = (n: number | null) => (n === null ? null : Number(n.toFixed(2)))

/** The rules, stated once for JSON and llms.txt. */
export const RULES_TEXT =
  `Five yes/no questions per page that compares a company with a named rival; each "yes" is a red flag (the ` +
  `model is at least ${RULES.RED_FLAG * 100}% sure). A page carries 0 to 5 red flags. Companies are ranked by ` +
  `total red flags once at least ${RULES.MIN_PAGES_FOR_RANKING} pages are read; a fair player averages ` +
  `${RULES.FAIR_AVERAGE} red flag per page or fewer.`
