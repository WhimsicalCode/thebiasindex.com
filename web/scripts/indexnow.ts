// node scripts/indexnow.ts, after `npm run build`: the IndexNow request (indexnow.org) for every page of the sitemap
// that differs from the live site, plus the pages the live sitemap has and the new one doesn't, written to stdout as
// one line of JSON. Nothing changed, nothing written. The deploy posts it once the new site is live, so Bing and the
// other IndexNow engines (and the AI search built on them) come back for the new data in days instead of weeks.
// Pages are compared without their asset hashes (/_astro/base-layout.CfEr1VdD.css): a style change alone isn't news.
import { existsSync, readFileSync } from "node:fs"
import path from "node:path"
import { BASE, SITE_ORIGIN } from "../src/lib/deploy.ts"

const out = path.resolve(import.meta.dirname, "..", "out")
const site = `${SITE_ORIGIN}${BASE}`

const locs = (sitemap: string) => [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1])
const withoutAssetHashes = (html: string) =>
  html.replace(/(\/_astro\/[^"'\s)]+?)\.[\w-]{8}(\.\w+)/g, "$1$2")

/** The built file for a page address: /clickup.com/ is out/clickup.com/index.html, /clickup.com out/clickup.com.html. */
function builtFile(url: string): string {
  const page = new URL(url).pathname.slice(BASE.length)
  const file = [`${page}index.html`, `${page}.html`, `${page}/index.html`]
    .map(name => path.join(out, name))
    .find(name => existsSync(name))
  if (!file) throw new Error(`${url} is in the sitemap but not in ${out}`)
  return file
}

/** Whether the live page differs from the one we built. A page we can't read counts as changed. */
async function changed(url: string): Promise<boolean> {
  const built = withoutAssetHashes(readFileSync(builtFile(url), "utf8"))
  try {
    const response = await fetch(url)
    return !response.ok || withoutAssetHashes(await response.text()) !== built
  } catch {
    return true
  }
}

const pages = locs(readFileSync(path.join(out, "sitemap.xml"), "utf8"))
const live = await fetch(`${site}/sitemap.xml`)
  .then(response => (response.ok ? response.text() : ""))
  .then(locs, () => [])
const gone = live.filter(url => !pages.includes(url))

// A few pages at a time: it's our own site, but no reason to hit it with all of them at once.
const updated: string[] = []
const queue = [...pages]
await Promise.all(
  Array.from({ length: 8 }, async () => {
    for (let url = queue.shift(); url; url = queue.shift()) {
      if (await changed(url)) updated.push(url)
    }
  })
)

const urlList = [...pages.filter(url => updated.includes(url)), ...gone]
console.error(
  `IndexNow: ${updated.length} of ${pages.length} pages new or changed, ${gone.length} gone (${site})`
)
if (urlList.length > 0) {
  const key = readFileSync(path.join(out, "indexnow.txt"), "utf8").trim()
  const host = new URL(SITE_ORIGIN).host
  console.log(JSON.stringify({ host, key, keyLocation: `${site}/indexnow.txt`, urlList }))
}
