// /<a>/vs/<b>.json (/lucid.co/vs/miro.com.json): the pair page as data, for LLMs and anyone who wants the numbers.
import type { APIRoute } from "astro"
import { type Pair, pairs } from "@/lib/db"
import { pairReportOf } from "@/lib/report"

export function getStaticPaths() {
  return pairs().map(pair => ({
    params: { domain: pair.a.slug, other: pair.b.slug },
    props: { pair },
  }))
}

export const GET: APIRoute = ({ props }) =>
  new Response(JSON.stringify(pairReportOf((props as { pair: Pair }).pair), null, 2), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  })
