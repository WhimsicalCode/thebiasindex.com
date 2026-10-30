// Reads the pipeline's SQLite database at build time (node:sqlite, no native dependency).
// Path: BIAS_INDEX_DB, or ../data/bias_index.sqlite relative to this web/ folder.
import { existsSync, statSync } from "node:fs"
import path from "node:path"
import { DatabaseSync } from "node:sqlite"
import { href } from "./deploy"
import type { LookupCompany } from "./lookup"

const RED_FLAG = 0.8
const OK = 0.2
const MIN_PAGES_FOR_RANKING = 3
const FAIR_AVERAGE = 1

// The five questions, in the same order and colour everywhere: dots, bars, legends, the icon.
export const QUESTIONS = [
  {
    key: "p_best_at_everything",
    label: "Wins on everything",
    color: "#E9631C",
    question: "Does the page claim the vendor wins or ties on everything it compares?",
  },
  {
    key: "p_no_honest_exit",
    label: "Never says when to pick the rival",
    color: "#2D63E0",
    question:
      "Does the page leave out every situation where a competitor would be the better choice?",
  },
  {
    key: "p_no_admitted_weakness",
    label: "Admits no weakness",
    color: "#12A06A",
    question:
      "Does the page avoid saying anything the vendor's own product can't do or does poorly?",
  },
  {
    key: "p_vague_attacks",
    label: "Vague attacks",
    color: "#3B1E6E",
    question: "Are the criticisms of competitors vague, with no specifics, numbers or sources?",
  },
  {
    key: "p_uneven_scrutiny",
    label: "Rival gets more criticism",
    color: "#EC3E7B",
    question: "Does the competitor get clearly more criticism than the vendor's product?",
  },
] as const

type QuestionKey = (typeof QUESTIONS)[number]["key"]
export type Answer = "flag" | "ok" | "unclear"

export type Page = {
  url: string
  title: string | null
  pageType: string | null
  score: number | null
  unclear: number | null
  skipReason: string | null
  answers: Answer[]
}

export type Company = {
  /** The company's domain, e.g. "clickup.com": its page is /clickup.com. */
  slug: string
  company: string
  hosts: string[]
  /** Other domains people know it by (draw.io for drawio.com); /draw.io redirects to /drawio.com. */
  aliases: string[]
  /** e.g. "project_management"; null for databases from before categories existed. */
  category: string | null
  candidates: number
  sampled: number
  status: string
  scoredPages: number
  averageScore: number | null
  biasLoad: number
  /** Red flags for each of the five questions, in QUESTIONS order. They add up to biasLoad. */
  flags: number[]
  thirdParty: number
  otherPages: number
  skipped: number
  fairPlayer: boolean
}

export type Run = {
  startedAt: string
  finishedAt: string | null
  methodology: string
  model: string
  pagesFetched: number
  pagesClassified: number
}

const DB_FILE =
  process.env.BIAS_INDEX_DB ?? path.resolve(process.cwd(), "..", "data", "bias_index.sqlite")

let db: DatabaseSync | undefined

function requireDatabase() {
  if (existsSync(DB_FILE)) return
  throw new Error(
    `No database at ${DB_FILE}. Download the latest data release:\n` +
      "  curl -L --create-dirs -o data/bias_index.sqlite " +
      "https://github.com/WhimsicalCode/thebiasindex.com/releases/latest/download/bias_index.sqlite"
  )
}

function open(): DatabaseSync {
  requireDatabase()
  if (!db) db = new DatabaseSync(DB_FILE, { readOnly: true })
  return db
}

// Query results are reused until the database file changes. A build renders ~120 pages (and llms.txt asks for
// every company's rank), so without this the same queries run thousands of times; the dev server picks up a new
// pipeline run without a restart.
let cache = { mtime: -1, values: new Map<string, unknown>() }

function cached<T>(key: string, compute: () => T): T {
  requireDatabase()
  const mtime = statSync(DB_FILE).mtimeMs
  if (mtime !== cache.mtime) {
    db?.close()
    db = undefined
    cache = { mtime, values: new Map() }
  }
  if (!cache.values.has(key)) cache.values.set(key, compute())
  return cache.values.get(key) as T
}

export function answerFor(probability: number | null): Answer {
  if (probability === null) return "unclear"
  if (probability >= RED_FLAG) return "flag"
  if (probability <= OK) return "ok"
  return "unclear"
}

export function latestRun(): Run | undefined {
  return cached("run", queryLatestRun)
}

function queryLatestRun(): Run | undefined {
  const row = open()
    .prepare(
      `select started_at, finished_at, methodology, model, pages_fetched, pages_classified
       from runs where finished_at is not null order by run_id desc limit 1`
    )
    .get() as Record<string, string | number | null> | undefined
  if (!row) return undefined
  return {
    startedAt: String(row.started_at),
    finishedAt: row.finished_at ? String(row.finished_at) : null,
    methodology: String(row.methodology),
    model: String(row.model),
    pagesFetched: Number(row.pages_fetched),
    pagesClassified: Number(row.pages_classified),
  }
}

/** Pages seen in the latest run only, so pages that disappeared from a sitemap drop off the site. */
function currentPagesWhere(): string {
  return "last_seen = (select max(last_seen) from pages p2 where p2.company_slug = pages.company_slug)"
}

/** Every company. A fresh array each call, so callers can sort it. */
export function companies(): Company[] {
  return [...cached("companies", queryCompanies)]
}

function queryCompanies(): Company[] {
  // Databases from before categories (or the monitored flag) existed lack those columns.
  const columns = (open().prepare("pragma table_info(companies)").all() as { name: string }[]).map(
    column => column.name
  )
  const hasCategory = columns.includes("category")
  // Companies dropped from domains.yml stay in the database as history, but not on the site.
  const monitoredOnly = columns.includes("monitored") ? "where c.monitored = 1" : ""
  const rows = open()
    .prepare(
      `select c.slug, c.company, c.hosts, c.aliases, ${hasCategory ? "c.category" : "null as category"},
         c.candidates, c.sampled, c.status,
         sum(case when p.page_type = 'competitor_comparison' then 1 else 0 end) as scored,
         avg(case when p.page_type = 'competitor_comparison' then p.score end) as average_score,
         sum(case when p.page_type = 'competitor_comparison' then p.score else 0 end) as bias_load,
         ${QUESTIONS.map(
           (q, i) =>
             `sum(case when p.page_type = 'competitor_comparison' and p.${q.key} >= ${RED_FLAG} then 1 else 0 end) as flags_${i}`
         ).join(",\n         ")},
         sum(case when p.page_type = 'third_party_comparison' then 1 else 0 end) as third_party,
         sum(case when p.page_type in ('educational', 'own_products', 'hub', 'other') then 1 else 0 end)
           as other_pages,
         sum(case when p.skip_reason is not null then 1 else 0 end) as skipped
       from companies c
       left join pages p on p.company_slug = c.slug and ${currentPagesWhere().replaceAll("pages.", "p.")}
       ${monitoredOnly}
       group by c.slug
       order by c.company collate nocase`
    )
    .all() as Record<string, string | number | null>[]
  return rows.map(row => {
    const scoredPages = Number(row.scored ?? 0)
    const averageScore = row.average_score === null ? null : Number(row.average_score)
    return {
      slug: String(row.slug),
      company: String(row.company),
      hosts: JSON.parse(String(row.hosts)) as string[],
      aliases: JSON.parse(String(row.aliases ?? "[]")) as string[],
      category: row.category ? String(row.category) : null,
      candidates: Number(row.candidates),
      sampled: Number(row.sampled),
      status: String(row.status),
      scoredPages,
      averageScore,
      biasLoad: Number(row.bias_load ?? 0),
      flags: QUESTIONS.map((_, i) => Number(row[`flags_${i}`] ?? 0)),
      thirdParty: Number(row.third_party ?? 0),
      otherPages: Number(row.other_pages ?? 0),
      skipped: Number(row.skipped ?? 0),
      fairPlayer:
        averageScore !== null &&
        scoredPages >= MIN_PAGES_FOR_RANKING &&
        averageScore <= FAIR_AVERAGE,
    }
  })
}

export function rankable(list: Company[]): Company[] {
  return list.filter(c => c.status === "ok" && c.scoredPages >= MIN_PAGES_FOR_RANKING)
}

export function pagesFor(slug: string): Page[] {
  return [...cached(`pages:${slug}`, () => queryPages(slug))]
}

function queryPages(slug: string): Page[] {
  const rows = open()
    .prepare(
      `select url, title, page_type, score, unclear, skip_reason,
         ${QUESTIONS.map(q => q.key).join(", ")}
       from pages where company_slug = ? and ${currentPagesWhere()}
       order by case when page_type = 'competitor_comparison' then 0 else 1 end, score desc, url`
    )
    .all(slug) as Record<string, string | number | null>[]
  return rows.map(row => ({
    url: String(row.url),
    title: row.title ? String(row.title) : null,
    pageType: row.page_type ? String(row.page_type) : null,
    score: row.score === null ? null : Number(row.score),
    unclear: row.unclear === null ? null : Number(row.unclear),
    skipReason: row.skip_reason ? String(row.skip_reason) : null,
    answers: QUESTIONS.map(q =>
      answerFor(row[q.key as QuestionKey] === null ? null : Number(row[q.key as QuestionKey]))
    ),
  }))
}

export const RULES = { RED_FLAG, OK, MIN_PAGES_FOR_RANKING, FAIR_AVERAGE }

export const PAGE_TYPE_LABELS: Record<string, string> = {
  competitor_comparison: "Competitor comparison",
  third_party_comparison: "Third-party comparison",
  own_products: "Own plans or editions",
  educational: "Educational",
  hub: "Index page",
  other: "Other",
}

/** The ranking: companies with at least 3 scored pages, by total red flags, then by compare pages. Fair players (1 red
 * flag per page or fewer) are left out: a high total from many fair pages isn't a red flag. */
export function byRedFlags(list: Company[]): Company[] {
  return rankable(list)
    .filter(c => !c.fairPlayer)
    .sort((a, b) => b.biasLoad - a.biasLoad || b.scoredPages - a.scoredPages)
}

/** Fair players, fewest red flags per page first. */
export function fairPlayers(list: Company[]): Company[] {
  return list
    .filter(c => c.fairPlayer)
    .sort((a, b) => (a.averageScore ?? 0) - (b.averageScore ?? 0))
}

/** Every company with at least one scored page: the points of the scope plot. */
export function scoredCompanies(list: Company[]): Company[] {
  return list.filter(c => c.scoredPages > 0)
}

// The home page's example of a biased page: ClickUp's Notion comparison while it carries all five red flags,
// otherwise the top company's first page with the most red flags.
const EXAMPLE_URL = "https://clickup.com/compare/notion-vs-clickup"

export function examplePage(list: Company[]): Page | undefined {
  const top = byRedFlags(list)[0]
  if (!top) return undefined
  const pages = pagesFor(top.slug).filter(p => p.pageType === "competitor_comparison")
  return pages.find(p => p.url === EXAMPLE_URL && p.score === QUESTIONS.length) ?? pages[0]
}

/** The company that made the index, said so in the fair table. */
export const MADE_BY = "whimsical.com"

export type FairRow = { company: Company; why: string }

/** Fair players, then companies we could read that publish no comparison with a named rival: not penalised.
 * Companies we couldn't read (blocked crawler, unreadable sitemap) aren't here. */
export function fairTable(list: Company[]): FairRow[] {
  return [
    ...fairPlayers(list).map(company => ({ company, why: "Fair" })),
    ...silentCompanies(list).map(company => ({ company, why: "No compare pages" })),
  ].map(row =>
    row.company.slug === MADE_BY ? { ...row, why: `${row.why}. We made this index.` } : row
  )
}

/** Companies we could read that publish no comparison with a named rival, A to Z. */
export function silentCompanies(list: Company[]): Company[] {
  return list
    .filter(c => c.status === "ok" && c.scoredPages === 0)
    .sort((a, b) => a.company.localeCompare(b.company))
}

/** Companies we can't measure yet (blocked crawler, unreadable sitemaps), A to Z. */
export function notMeasured(list: Company[]): Company[] {
  return list.filter(c => c.status !== "ok").sort((a, b) => a.company.localeCompare(b.company))
}

/** Why a company isn't ranked, in the same four words everywhere, or null when it is ranked. */
export function unrankedStatus(company: Company): string | null {
  if (company.status !== "ok") return "Not measured yet"
  if (company.scoredPages === 0) return "No compare pages"
  if (company.fairPlayer) return "Fair player"
  if (company.scoredPages < MIN_PAGES_FOR_RANKING) return "Too few pages"
  return null
}

/** This week's pages by what they turned out to be: page type, or "unreadable" when we couldn't read them. */
export function pageTypeCounts(): Record<string, number> {
  return cached("pageTypes", () => {
    // Only companies on the site, as in companies(), so the totals match the home page.
    const columns = (
      open().prepare("pragma table_info(companies)").all() as { name: string }[]
    ).map(column => column.name)
    const monitoredOnly = columns.includes("monitored")
      ? "and company_slug in (select slug from companies where monitored = 1)"
      : ""
    const rows = open()
      .prepare(
        `select coalesce(page_type, 'unreadable') as type, count(*) as n from pages
         where ${currentPagesWhere()} ${monitoredOnly} group by 1`
      )
      .all() as { type: string; n: number }[]
    return Object.fromEntries(rows.map(row => [row.type, Number(row.n)]))
  })
}

/** Number of scored pages with 0, 1, ... 5 red flags. */
export function scoreDistribution(pages: Page[]): number[] {
  const counts = [0, 0, 0, 0, 0, 0]
  for (const page of pages) {
    if (page.pageType === "competitor_comparison" && page.score !== null) counts[page.score] += 1
  }
  return counts
}

/** "29 October 2026" from an ISO timestamp. */
export function longDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  })
}

/** Main host without www, e.g. "clickup.com". */
export function mainHost(company: Company): string {
  return (company.hosts[0] ?? "").replace(/^www\./, "")
}

/** The company page's path, e.g. "/clickup.com". */
export function companyPath(company: Pick<Company, "slug">): string {
  return `/${company.slug}`
}

/** A link to the company page, with the deployment's base path. */
export function companyHref(company: Pick<Company, "slug">): string {
  return href(companyPath(company))
}

/** For the lookups (lib/lookup.ts): each company's name and every domain it is known by, pointing at its page. */
export function lookupCompanies(): LookupCompany[] {
  return companies()
    .map(c => ({
      name: c.company,
      slug: c.slug,
      domains: [
        ...new Set([c.slug, ...c.aliases, ...c.hosts].map(domain => domain.replace(/^www\./, ""))),
      ],
      href: companyHref(c),
    }))
    .sort((a, b) => a.name.localeCompare(b.name))
}

/** Company pages used to live at /companies/<name>; links shared before the move still work. */
const formerPath = (name: string) =>
  `/companies/${name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")}`
const FORMER_NAMES: Record<string, string> = { "zoho.com": "Zoho Projects" }

/** Alias domains and former paths to the company page, e.g. { "/draw.io": "/drawio.com" }, for astro.config.ts. */
export function aliasRedirects(): Record<string, string> {
  return Object.fromEntries(
    companies().flatMap(c => [
      ...c.aliases.map(alias => [`/${alias}`, companyPath(c)]),
      [formerPath(FORMER_NAMES[c.slug] ?? c.company), companyPath(c)],
      ...(c.scoredPages > 100 ? [[`${companyPath(c)}/1`, companyPath(c)]] : []),
    ])
  )
}
