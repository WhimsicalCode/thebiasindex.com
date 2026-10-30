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

// Empty space after the last stroke of a character, in em, measured in the browser: Dinsical bold at -0.02em
// letter-spacing (the big numbers) and Monsical regular (their labels). A "1" ends far earlier than other digits.
const DINSICAL_END: Record<string, number> = {
  "0": 0.043,
  "1": 0.156,
  "2": 0.052,
  "3": 0.049,
  "4": 0.026,
  "5": 0.049,
  "6": 0.04,
  "7": 0.051,
  "8": 0.04,
  "9": 0.04,
}
const MONSICAL_END: Record<string, number> = { "→": 0.032 }

/** A right margin that pulls the last stroke onto the right edge, so a right-aligned number and its label end on
 * exactly the same line. */
export function inkEnd(text: string, font: "Dinsical" | "Monsical"): string {
  const last = text.at(-1) ?? ""
  const em = font === "Dinsical" ? (DINSICAL_END[last] ?? 0) : (MONSICAL_END[last] ?? 0.085)
  return `margin-right: -${em}em`
}

/** "1 red flag", "5 red flags" */
export const redFlags = (n: number) => `${fmt(n)} red flag${n === 1 ? "" : "s"}`
