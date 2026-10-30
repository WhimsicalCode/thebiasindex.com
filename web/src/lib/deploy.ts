// Where the site is served, from the environment, so astro.config.ts and the pages share one answer.
// - SITE_URL: the site's address, base path included. Default https://thebiasindex.com. The GitHub Pages workflow
//   passes the URL GitHub reports (https://whimsicalcode.github.io/thebiasindex.com, or the custom domain once set).
// - DIRECTORY_URLS=true builds every page as a folder (clickup.com/index.html): GitHub Pages can't serve
//   /clickup.com from a file when a clickup.com/ folder (pages 2, 3…) exists. Cloudflare Pages can.
const siteUrl = new URL(process.env.SITE_URL || "https://thebiasindex.com")
// GitHub reports http:// until HTTPS is enforced; the published URLs (JSON, llms.txt) should always be https.
if (siteUrl.hostname !== "localhost") siteUrl.protocol = "https:"

export const SITE_ORIGIN = siteUrl.origin
export const BASE = siteUrl.pathname.replace(/\/$/, "")
export const DIRECTORY_URLS = process.env.DIRECTORY_URLS === "true"

/** An internal link: the base path, plus a trailing slash for pages when they're built as folders. */
export function href(path: string): string {
  if (/^[a-z]+:/i.test(path)) return path
  // Files keep their address as is: no trailing slash on /favicon.ico or /clickup.com.json.
  const file = /\.(json|txt|xml|png|jpe?g|svg|ico|webp|csv)$/.test(path)
  const slash = DIRECTORY_URLS && !file && !path.endsWith("/") ? "/" : ""
  return `${BASE}${path}${slash}`
}

/** An absolute URL, e.g. for JSON and llms.txt. */
export function absoluteUrl(path: string): string {
  return `${SITE_ORIGIN}${href(path)}`
}
