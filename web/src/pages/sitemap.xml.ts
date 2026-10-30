// /sitemap.xml: every page, so crawlers (search engines and LLMs) find each company without following links.
import type { APIRoute } from "astro"
import { PAGE_SIZE } from "@/components/company-page.astro"
import { companies, companyPath, latestRun } from "@/lib/db"
import { absoluteUrl } from "@/lib/deploy"

const PAGES = ["/", "/companies", "/methodology", "/about", "/colophon", "/bot"]

export const GET: APIRoute = () => {
  // Every page is rebuilt from the latest weekly run.
  const lastmod = latestRun()?.startedAt.slice(0, 10)
  const paths = [
    ...PAGES,
    ...companies().flatMap(c => {
      const pages = Math.max(1, Math.ceil(c.scoredPages / PAGE_SIZE))
      return [
        ...Array.from({ length: pages }, (_, i) =>
          i === 0 ? companyPath(c) : `${companyPath(c)}/${i + 1}`
        ),
        ...(c.candidates > 0 ? [`${companyPath(c)}/candidates`] : []),
      ]
    }),
  ]
  const urls = paths
    .map(
      path =>
        `  <url><loc>${absoluteUrl(path)}</loc>${lastmod ? `<lastmod>${lastmod}</lastmod>` : ""}</url>`
    )
    .join("\n")
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>
`
  return new Response(xml, { headers: { "Content-Type": "application/xml; charset=utf-8" } })
}
