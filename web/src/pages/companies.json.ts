// /companies.json: every monitored company, ranked as on /companies, without the page-by-page answers.
import type { APIRoute } from "astro"
import { companies } from "@/lib/db"
import { absoluteUrl } from "@/lib/deploy"
import { RULES_TEXT, reportOf } from "@/lib/report"
import { REPO_URL } from "@/lib/site"

export const GET: APIRoute = () => {
  const list = companies()
    .map(company => {
      const {
        pages: _pages,
        questions: _questions,
        methodology: _methodology,
        source: _source,
        ...summary
      } = reportOf(company)
      return summary
    })
    .sort((a, b) => (b.red_flags_total ?? -1) - (a.red_flags_total ?? -1))
  const body = {
    rules: RULES_TEXT,
    methodology: absoluteUrl("/methodology"),
    source: REPO_URL,
    companies: list,
  }
  return new Response(JSON.stringify(body, null, 2), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  })
}
