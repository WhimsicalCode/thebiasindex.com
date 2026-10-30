// schema.org structured data (Dataset) for the home page and company pages, so search engines and dataset search
// know what the numbers are, where to download them, and under which license.
import { type Company, companyPath, latestRun, QUESTIONS, RULES } from "@/lib/db"
import { absoluteUrl } from "@/lib/deploy"
import { summaryOf } from "@/lib/report"
import { REPO_URL } from "@/lib/site"

const DOWNLOAD = `${REPO_URL}/releases/latest/download`
const WHIMSICAL = { "@type": "Organization", name: "Whimsical", url: "https://whimsical.com" }
const MIT = "https://opensource.org/licenses/MIT"

const common = () => {
  const run = latestRun()
  return {
    creator: WHIMSICAL,
    license: MIT,
    isAccessibleForFree: true,
    ...(run ? { dateModified: run.startedAt.slice(0, 10) } : {}),
    measurementTechnique: `Five yes/no questions per comparison page, answered by ${run?.model ?? "a language model"}; a yes at least ${RULES.RED_FLAG * 100}% sure is a red flag.`,
  }
}

/** The whole index. */
export function siteDataset() {
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: "The Bias Index",
    alternateName: "thebiasindex.com",
    description:
      "How fair SaaS companies' own comparison pages are: every page that compares a company with a named rival, scored each week with five yes/no questions.",
    url: absoluteUrl("/"),
    keywords: ["SaaS", "comparison pages", "alternatives pages", "bias", "marketing"],
    ...common(),
    variableMeasured: QUESTIONS.map(q => ({
      "@type": "PropertyValue",
      name: q.label,
      description: q.question,
    })),
    distribution: [
      {
        "@type": "DataDownload",
        encodingFormat: "application/json",
        contentUrl: absoluteUrl("/companies.json"),
      },
      {
        "@type": "DataDownload",
        encodingFormat: "text/csv",
        contentUrl: `${DOWNLOAD}/companies.csv`,
      },
      { "@type": "DataDownload", encodingFormat: "text/csv", contentUrl: `${DOWNLOAD}/pages.csv` },
      {
        "@type": "DataDownload",
        encodingFormat: "application/vnd.sqlite3",
        contentUrl: `${DOWNLOAD}/bias_index.sqlite`,
      },
    ],
  }
}

/** One company's results. */
export function companyDataset(company: Company) {
  const value = (name: string, v: number | null) => ({ "@type": "PropertyValue", name, value: v })
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: `The Bias Index: ${company.company}`,
    description: summaryOf(company),
    url: absoluteUrl(companyPath(company)),
    about: { "@type": "Organization", name: company.company, url: `https://${company.slug}` },
    isPartOf: { "@type": "Dataset", name: "The Bias Index", url: absoluteUrl("/") },
    ...common(),
    variableMeasured: [
      value("Red flags in total", company.status === "ok" ? company.biasLoad : null),
      value(
        "Red flags per page",
        company.averageScore === null ? null : Number(company.averageScore.toFixed(2))
      ),
      value("Compare pages", company.scoredPages),
      value("Candidate pages", company.candidates),
      ...QUESTIONS.map((q, i) => ({
        ...value(q.label, company.flags[i] ?? 0),
        description: q.question,
      })),
    ],
    distribution: [
      {
        "@type": "DataDownload",
        encodingFormat: "application/json",
        contentUrl: absoluteUrl(`/${company.slug}.json`),
      },
    ],
  }
}
