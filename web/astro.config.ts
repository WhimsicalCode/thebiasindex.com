import { writeFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig } from "astro/config"
import { aliasRedirects } from "./src/lib/db"
import { BASE, DIRECTORY_URLS, href, SITE_ORIGIN } from "./src/lib/deploy"
import { repoUrl } from "./src/lib/site"

type HastNode = {
  type: string
  tagName?: string
  properties?: Record<string, unknown>
  children?: HastNode[]
}

/** docs/*.md link to repo files with relative paths (right on GitHub); on the site they point at GitHub.
// Every link to another site opens in a new tab. */
function repoLinks() {
  const visit = (node: HastNode) => {
    const href = node.tagName === "a" ? node.properties?.href : undefined
    if (typeof href === "string" && !/^([a-z]+:|\/|#)/i.test(href)) {
      node.properties = {
        ...node.properties,
        href: repoUrl(path.posix.normalize(path.posix.join("docs", href))),
      }
    }
    // Links to other sites open in a new tab.
    if (typeof node.properties?.href === "string" && /^https?:/.test(node.properties.href)) {
      node.properties = { ...node.properties, target: "_blank", rel: "noopener" }
    }
    node.children?.forEach(visit)
  }
  return (tree: HastNode) => visit(tree)
}

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/** Cloudflare Pages serves `_redirects` as real 301s; Astro's own redirect pages stay as a fallback. */
function cloudflareRedirects() {
  return {
    name: "cloudflare-redirects",
    hooks: {
      "astro:build:done": ({ dir }: { dir: URL }) => {
        const lines = Object.entries(aliasRedirects()).map(
          ([from, to]) => `${BASE}${from} ${href(to)} 301`
        )
        writeFileSync(new URL("_redirects", dir), `${lines.join("\n")}\n`)
      },
    },
  }
}

// Address and URL shape come from src/lib/deploy.ts (SITE_URL, DIRECTORY_URLS); the default is thebiasindex.com.
export default defineConfig({
  build: { format: DIRECTORY_URLS ? "directory" : "file" },
  trailingSlash: DIRECTORY_URLS ? "ignore" : "never",
  site: SITE_ORIGIN,
  base: BASE || "/",
  output: "static",
  outDir: "out",
  // Other domains people know a company by: /draw.io goes to /drawio.com.
  redirects: Object.fromEntries(
    Object.entries(aliasRedirects()).map(([from, to]) => [from, href(to)])
  ),
  markdown: { rehypePlugins: [repoLinks] },
  integrations: [cloudflareRedirects()],
  vite: {
    resolve: { alias: { "@": path.resolve(__dirname, "src") } },
    // The dev server only watches web/ by default; the methodology page renders ../docs/METHODOLOGY.md.
    plugins: [
      {
        name: "watch-docs",
        configureServer: server => {
          server.watcher.add(path.resolve(__dirname, "..", "docs"))
        },
      },
    ],
    // The methodology page renders ../docs/METHODOLOGY.md, which lives outside this folder.
    server: {
      fs: { allow: [path.resolve(__dirname, "..")] },
      // Demo through an ngrok tunnel (any *.ngrok-free.app / *.ngrok.app subdomain).
      allowedHosts: [".ngrok-free.app", ".ngrok.app"],
    },
  },
})
