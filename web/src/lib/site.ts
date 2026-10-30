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
