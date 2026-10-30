// /llms.txt (llmstxt.org): what the site is, the five questions, how to look a company up by domain, and every
// company in one line, in the order of /companies and in the same words as its page.
import type { APIRoute } from "astro"
import { companies, latestRun, longDate, QUESTIONS, RULES, unrankedStatus } from "@/lib/db"
import { absoluteUrl } from "@/lib/deploy"
import { inListOrder, RULES_TEXT, standingOf, summaryOf } from "@/lib/report"
import { REPO_URL } from "@/lib/site"

const SITE = absoluteUrl("/").replace(/\/$/, "")
const page = (slug: string) => absoluteUrl(`/${slug}`)

export const GET: APIRoute = () => {
  const run = latestRun()
  const lines = inListOrder(companies()).map(c => {
    const standing = unrankedStatus(c) ? standingOf(c) : `Ranked ${standingOf(c)} red flags`
    return `- [${c.company} (${c.slug})](${page(c.slug)}): ${standing}. ${summaryOf(c)}`
  })
  const text = `# The Bias Index (thebiasindex.com)

> On their own comparison pages ("X vs Y", "X alternatives"), SaaS companies win every single time. Every week,
> The Bias Index finds those pages and scores each one for bias with five yes/no questions. Made by Whimsical,
> which is scored by the same rules as everyone else. The data and the code are open (MIT).

Latest run: ${run ? `${longDate(run.startedAt)} (${run.startedAt.slice(0, 10)})` : "none yet"}, methodology ${run?.methodology ?? "–"}.

## The five questions

Asked of every page that compares a company's product with a named rival. Every "yes" is a red flag.

${QUESTIONS.map((q, i) => `${i + 1}. ${q.label}: ${q.question}`).join("\n")}

${RULES_TEXT}

## Statuses

- Ranked: at least ${RULES.MIN_PAGES_FOR_RANKING} pages read and more than ${RULES.FAIR_AVERAGE} red flag per page. Ranked by total red flags, then pages read.
- Fair player: at least ${RULES.MIN_PAGES_FOR_RANKING} pages read, ${RULES.FAIR_AVERAGE} red flag per page or fewer. Not ranked.
- Too few pages: fewer than ${RULES.MIN_PAGES_FOR_RANKING} pages read, so one page would decide everything. Not ranked.
- No comparison pages: no page compares the company with a named rival. Not ranked, and not penalised.
- Not measured yet: our crawler is blocked, or we can't read the company's sitemaps.

## Look a company up by its domain

- Page: ${SITE}/<domain>, e.g. ${SITE}/clickup.com
- Data: ${SITE}/<domain>.json, e.g. ${SITE}/clickup.com.json (every page we read and its five answers)
- All companies: ${SITE}/companies.json
- How it works: ${absoluteUrl("/methodology")}
- Weekly dataset (SQLite and CSV, MIT): ${REPO_URL}/releases/latest
- Code and benchmark labels (MIT): ${REPO_URL}

## Companies

${lines.join("\n")}
`
  return new Response(text, { headers: { "Content-Type": "text/plain; charset=utf-8" } })
}
