// /llms.txt (llmstxt.org): what the site is, the five questions, how to look a company up by domain, and every
// company in one line, in the order of /companies and in the same words as its page.
import type { APIRoute } from "astro"
import {
  companies,
  latestRun,
  longDate,
  mentionsFor,
  QUESTIONS,
  RULES,
  unrankedStatus,
} from "@/lib/db"
import { absoluteUrl } from "@/lib/deploy"
import { againstOf, inListOrder, RULES_TEXT, standingOf, summaryOf } from "@/lib/report"
import { REPO_URL } from "@/lib/site"

const SITE = absoluteUrl("/").replace(/\/$/, "")
const page = (slug: string) => absoluteUrl(`/${slug}`)

export const GET: APIRoute = () => {
  const run = latestRun()
  const lines = inListOrder(companies()).map(c => {
    const standing = unrankedStatus(c) ? standingOf(c) : `Ranked ${standingOf(c)} red flags`
    const { aimedAtAverage } = mentionsFor(c.slug)
    const against =
      aimedAtAverage === null
        ? ""
        : ` ${againstOf(c)} The pages aimed at ${c.company} average ${aimedAtAverage.toFixed(1)} red flags per page.`
    return `- [${c.company} (${c.slug})](${page(c.slug)}): ${standing}. ${summaryOf(c)}${against}`
  })
  const text = `# The Bias Index (thebiasindex.com)

> On their own comparison pages ("X vs Y", "X alternatives"), SaaS companies win every single time. Every week,
> The Bias Index finds those pages and scores each one for bias with five yes/no questions. Made by Whimsical,
> which is scored by the same rules as everyone else. The data and the code are open (MIT).

Latest run: ${run ? `${longDate(run.startedAt)} (${run.startedAt.slice(0, 10)})` : "none yet"}, methodology ${run?.methodology ?? "–"}.

## The five questions

A candidate page is a page on a company's website whose address looks like a comparison ("vs", "alternative",
"compare", "switch"). A compare page is a candidate page that compares the company with a named rival; the AI reads
every candidate to tell. Only compare pages are scored, with five yes/no questions. Every "yes" is a red flag.

${QUESTIONS.map((q, i) => `${i + 1}. ${q.label}: ${q.question}`).join("\n")}

${RULES_TEXT}

## Statuses

- Ranked: at least ${RULES.MIN_PAGES_FOR_RANKING} compare pages and more than ${RULES.FAIR_AVERAGE} red flag per page. Ranked by total red flags, then compare pages.
- Fair player: at least ${RULES.MIN_PAGES_FOR_RANKING} compare pages, ${RULES.FAIR_AVERAGE} red flag per page or fewer. Not ranked.
- Too few pages: fewer than ${RULES.MIN_PAGES_FOR_RANKING} compare pages, so one page would decide everything. Not ranked.
- No compare pages: none of the company's candidate pages (if it has any) compares it with a named rival. Not ranked, and not penalised.
- Not measured yet: our crawler is blocked, or we can read neither the company's sitemaps nor its homepage.

## Who writes about whom

A compare page is aimed at a company when one of its product names sits next to "vs", "alternative" or "compare" in
the page's address or title ("Notion alternatives", "Miro vs Notion"). Its red flags then count on the company's page
under "Everyone against", with how many of the company's own pages are aimed back. A company is listed in a page when
a heading of the page's list starts with its name ("3. Notion"): counted, but without the red flags, which may be
about the other entries. Only monitored companies are matched, and the page body isn't read.

## Look a company up by its domain

- Page: ${SITE}/<domain>, e.g. ${SITE}/clickup.com
- Data: ${SITE}/<domain>.json, e.g. ${SITE}/clickup.com.json (every compare page and its five answers; other_candidate_pages lists the candidate pages that aren't compare pages, and what each one is; everyone_against lists the other companies' pages aimed at it, by company; aims_at lists the companies its own pages are aimed at)
- All companies: ${SITE}/companies.json
- How it works: ${absoluteUrl("/methodology")}
- Weekly dataset (SQLite and CSV, MIT): ${REPO_URL}/releases/latest
- Code and benchmark labels (MIT): ${REPO_URL}

## Companies

${lines.join("\n")}
`
  return new Response(text, { headers: { "Content-Type": "text/plain; charset=utf-8" } })
}
