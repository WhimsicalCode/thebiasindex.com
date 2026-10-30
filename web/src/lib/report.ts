// One company's results in the words and numbers the site uses everywhere: its page, /<domain>.json and
// /llms.txt all read from here, so an LLM quoting the JSON says exactly what a reader sees on the page.
import {
  byRedFlags,
  type Company,
  companies,
  companyPath,
  latestRun,
  notMeasured,
  type Page,
  pagesFor,
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
      found: `We can’t read ${name}’s sitemaps, so we haven’t found its candidate pages.`,
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
  }
}

/** The rules, stated once for JSON and llms.txt. */
export const RULES_TEXT =
  `Five yes/no questions per page that compares a company with a named rival; each "yes" is a red flag (the ` +
  `model is at least ${RULES.RED_FLAG * 100}% sure). A page carries 0 to 5 red flags. Companies are ranked by ` +
  `total red flags once at least ${RULES.MIN_PAGES_FOR_RANKING} pages are read; a fair player averages ` +
  `${RULES.FAIR_AVERAGE} red flag per page or fewer.`
