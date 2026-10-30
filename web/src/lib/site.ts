// The public repository: code, methodology, benchmark and data. Change it here if the repo moves.
export const REPO_URL = "https://github.com/WhimsicalCode/thebiasindex.com"

/** A file or folder in the repository, e.g. repoUrl("docs/RESULTS.md"). */
export function repoUrl(path: string): string {
  return `${REPO_URL}/${path.endsWith("/") ? "tree" : "blob"}/main/${path.replace(/\/$/, "")}`
}

/** Whimsical's view of vendor comparison pages, and why the index exists. */
export const WHY_URL = "https://whimsical.com/blog/the-anatomy-of-a-saas-comparison-page"

/** Contact for site owners and corrections, written so scrapers don't pick it up as an email address. */
export const CONTACT = "david.baussart at whimsical.com"

/** "acme.io", not "Acme" or "acme.io/pricing". */
export const isDomain = (text: string) => /^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(text)

/** A new GitHub issue asking for a company, by website or name: GitHub fills the form from ?title= and ?body=.
 * "Add <company name>" and "Website: <url>", nothing else: the pipeline finds the comparison pages. What we don't
 * know stays a placeholder to fill in. */
export function addCompanyUrl(what = ""): string {
  const title = `Add ${what && !isDomain(what) ? what : "<company name>"}`
  const body = `Website: ${isDomain(what) ? `https://${what}` : "<url>"}`
  return `${REPO_URL}/issues/new?${new URLSearchParams({ title, body })}`
}
