// /<domain>.json (/clickup.com.json): the company page as data, for LLMs and anyone who wants the numbers.
import type { APIRoute } from "astro"
import { type Company, companies } from "@/lib/db"
import { reportOf } from "@/lib/report"

export function getStaticPaths() {
  return companies().map(company => ({ params: { domain: company.slug }, props: { company } }))
}

export const GET: APIRoute = ({ props }) =>
  new Response(JSON.stringify(reportOf((props as { company: Company }).company), null, 2), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  })
