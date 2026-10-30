// Finding a company by name or website as you type, in the browser: the home page's lookup and the ⌘K palette.
// "mir", "Miro" and "https://www.Miro.com/app" all find Miro, aliases included. The list comes from
// lookupCompanies() in db.ts, built with the site.

/** A company's name and every domain it is known by, pointing at its page. */
export type LookupCompany = { name: string; slug: string; domains: string[]; href: string }

/** "acme.io" for "https://www.Acme.io/pricing". */
export const domainOf = (text: string) =>
  text
    .trim()
    .toLowerCase()
    .replace(/^[a-z]+:\/\//, "")
    .replace(/[/?#:].*$/, "")
    .replace(/^www\./, "")
    .replace(/\.$/, "")

// 0: the name or a domain starts with the query, or the query is on one of its domains (app.miro.com is Miro).
// 1: a word of the name starts with it. 2: the name or a domain contains it. null: no match.
function rank(company: LookupCompany, text: string, domain: string): number | null {
  const name = company.name.toLowerCase()
  const on = (d: string) => domain === d || domain.endsWith(`.${d}`)
  if (name.startsWith(text) || company.domains.some(d => d.startsWith(domain) || on(d))) return 0
  if (name.split(/[\s.-]+/).some(word => word.startsWith(text))) return 1
  if (name.includes(text) || company.domains.some(d => d.includes(domain))) return 2
  return null
}

/** The companies matching what was typed, best first. */
export function findCompanies(
  companies: LookupCompany[],
  query: string,
  max: number
): LookupCompany[] {
  const text = query.trim().toLowerCase()
  const domain = domainOf(query)
  if (!text) return []
  return companies
    .map(company => ({ company, rank: rank(company, text, domain || text) }))
    .filter((match): match is { company: LookupCompany; rank: number } => match.rank !== null)
    .sort((a, b) => a.rank - b.rank)
    .slice(0, max)
    .map(({ company }) => company)
}
