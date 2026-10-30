// Numbers as the site writes them.
import type { Company } from "@/lib/db"

/** 6,193 */
export const fmt = (n: number) => n.toLocaleString("en-US")

/** Red flags per page with one decimal, or "–" when no page was scored. */
export const perPage = (company: Company) =>
  company.averageScore === null ? "–" : company.averageScore.toFixed(1)

/** 1st, 2nd, 3rd, 4th… 11th, 12th, 13th… 21st */
export function ordinal(n: number): string {
  const tens = n % 100
  const suffix = tens >= 11 && tens <= 13 ? "th" : (["th", "st", "nd", "rd"][n % 10] ?? "th")
  return `${n}${suffix}`
}

/** "1 red flag", "5 red flags" */
export const redFlags = (n: number) => `${fmt(n)} red flag${n === 1 ? "" : "s"}`
