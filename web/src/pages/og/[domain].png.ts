// /og/<domain>.png: the company's share image, shown when its page is linked on Slack, X, LinkedIn…
import type { APIRoute } from "astro"
import { type Company, companies } from "@/lib/db"
import { companyImage } from "@/lib/og"

export function getStaticPaths() {
  return companies().map(company => ({ params: { domain: company.slug }, props: { company } }))
}

export const GET: APIRoute = async ({ props }) =>
  new Response(await companyImage((props as { company: Company }).company), {
    headers: { "Content-Type": "image/png" },
  })
