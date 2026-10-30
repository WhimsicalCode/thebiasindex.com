// One company's results in the words and numbers the site uses everywhere: its page, /<domain>.json and
// /llms.txt all read from here, so an LLM quoting the JSON says exactly what a reader sees on the page.
import {
  byRedFlags,
  type Company,
  companies,
  companyPath,
  latestRun,
  notMeasured,
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
  const pages = (n: number) => `${fmt(n)} page${n === 1 ? "" : "s"}`
  if (company.status === "unreachable")
    return {
      headline: `We can’t read ${name}’s pages yet.`,
      found: `${name}’s website blocks our crawler, so nothing was scored.`,
      total: "",
    }
  if (company.status !== "ok")
    return {
      headline: `We can’t read ${name}’s pages yet.`,
      found: `We can’t read ${name}’s sitemaps, so we haven’t found its comparison pages.`,
      total: "",
    }
  if (company.scoredPages === 0)
    return company.candidates === 0
      ? {
          headline: `${name} publishes no comparison pages.`,
          found:
            "Its sitemaps list no page comparing it with another product, so there is nothing to score.",
          total: "It isn’t ranked, and it isn’t penalised.",
        }
      : {
          headline: `${name} publishes no comparison against a named rival.`,
          found: `${name} publishes ${pages(company.candidates)} that compare it with other products. None of them compares it with a named rival, so there is nothing to score.`,
          total: "It isn’t ranked, and it isn’t penalised.",
        }
  const read = company.scoredPages
  const ofThem =
    read === company.candidates && read > 1
      ? `All ${fmt(read)} of them compare`
      : `${fmt(read)} of them compare${read === 1 ? "s" : ""}`
  const found =
    company.candidates < read
      ? `${name}’s sitemaps don’t list its comparison pages this week. We read ${pages(read)} that compare it with a named rival before.`
      : `${name} publishes ${pages(company.candidates)} that compare it with other products. ${ofThem} it with a named rival, and those are the ones we read.`
  const together =
    read === 1
      ? `That page carries ${redFlags(company.biasLoad)}`
      : `Together they add up to ${redFlags(company.biasLoad)}`
  const total = company.fairPlayer
    ? `${together}. At ${perPage(company)} per page, ${name} is a fair player: one red flag per page or fewer.`
    : rank
      ? `${together}, the ${rank === 1 ? "" : `${ordinal(rank)} `}most of the ${ranked.length} companies we rank.`
      : `${together}. With fewer than three pages read, ${name} isn’t ranked.`
  return {
    headline: `A typical comparison page from ${name} raises ${perPage(company)} of our five red flags.`,
    found,
    total,
  }
}

/** The verdict as one paragraph: the meta description, /<domain>.json and llms.txt. */
export function summaryOf(company: Company): string {
  const { headline, found, total } = verdictOf(company)
  return [headline, found, total].filter(Boolean).join(" ")
}

/** The order of /companies and llms.txt: everyone with pages read by total red flags (then pages read), then the
 * companies with no comparison pages, then the ones we can't measure yet. */
export function inListOrder(list: Company[]): Company[] {
  const read = list
    .filter(c => c.status === "ok" && c.scoredPages > 0)
    .sort((a, b) => b.biasLoad - a.biasLoad || b.scoredPages - a.scoredPages)
  return [...read, ...silentCompanies(list), ...notMeasured(list)]
}

/** Machine-readable report, served as /<domain>.json. */
export function reportOf(company: Company) {
  const run = latestRun()
  const pages = pagesFor(company.slug).filter(p => p.pageType === "competitor_comparison")
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
    competitor_comparisons_scored: company.scoredPages,
    pages_checked: company.sampled,
    comparison_style_pages_found: company.candidates,
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
  }
}

/** The rules, stated once for JSON and llms.txt. */
export const RULES_TEXT =
  `Five yes/no questions per page that compares a company with a named rival; each "yes" is a red flag (the ` +
  `model is at least ${RULES.RED_FLAG * 100}% sure). A page carries 0 to 5 red flags. Companies are ranked by ` +
  `total red flags once at least ${RULES.MIN_PAGES_FOR_RANKING} pages are read; a fair player averages ` +
  `${RULES.FAIR_AVERAGE} red flag per page or fewer.`
