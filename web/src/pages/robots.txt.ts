// /robots.txt: everyone is welcome, AI crawlers included. The index is open data, meant to be read and quoted.
import type { APIRoute } from "astro"
import { absoluteUrl } from "@/lib/deploy"

export const GET: APIRoute = () =>
  new Response(
    `# The Bias Index is open data (MIT): search engines and AI crawlers are welcome.
# A summary for LLMs: ${absoluteUrl("/llms.txt")}
User-agent: *
Allow: /

Sitemap: ${absoluteUrl("/sitemap.xml")}
`,
    { headers: { "Content-Type": "text/plain; charset=utf-8" } }
  )
