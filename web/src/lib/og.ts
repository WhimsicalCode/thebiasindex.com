// Share images (Open Graph, 1200 × 630) in the site's style (design/v2/mockups/Share.dc.html, without the weave), rendered at build
// time: satori lays out the card as SVG, resvg turns it into PNG. Fonts come from src/assets/fonts (SIL Open Font
// License): satori reads TTF, not WOFF2, and the static Dinsical weights instead of the variable one.
import { readFileSync } from "node:fs"
import path from "node:path"
import { Resvg } from "@resvg/resvg-js"
import satori from "satori"
import { type Company, companies, QUESTIONS, unrankedStatus } from "@/lib/db"
import { fmt, perPage } from "@/lib/format"

const W = 1200
const H = 630
const INK = "#1A1630"
const MUTED = "#5F5A72"

const font = (file: string) => readFileSync(path.resolve(process.cwd(), "src/assets/fonts", file))
const FONTS = [
  {
    name: "Dinsical",
    data: font("Dinsical-Bold.ttf"),
    weight: 700 as const,
    style: "normal" as const,
  },
  {
    name: "Dinsical",
    data: font("Dinsical-SemiBold.ttf"),
    weight: 600 as const,
    style: "normal" as const,
  },
  {
    name: "Monsical",
    data: font("Monsical-Regular.ttf"),
    weight: 400 as const,
    style: "normal" as const,
  },
]

type Node = { type: string; props: Record<string, unknown> }
/** A satori element without JSX. */
const h = (style: Record<string, unknown>, ...children: unknown[]): Node => ({
  type: "div",
  props: {
    style: { display: "flex", ...style },
    children: children.length === 1 ? children[0] : children,
  },
})
const img = (src: string, width: number, height: number): Node => ({
  type: "img",
  props: { src, width, height, style: { display: "block" } },
})

async function png(node: Node): Promise<Uint8Array<ArrayBuffer>> {
  // satori's own element type wants React; the plain object tree is what it reads at runtime.
  const markup = await satori(node as unknown as Parameters<typeof satori>[0], {
    width: W,
    height: H,
    fonts: FONTS,
  })
  return new Uint8Array(new Resvg(markup, { fitTo: { mode: "width", value: W } }).render().asPng())
}

// The icon: five dots on a circle, 72° apart, orange at the top, then clockwise in question order.
const ICON =
  '<circle cx="12.00" cy="4.60" r="3.4" fill="#E9631C"/><circle cx="19.04" cy="9.71" r="3.4" fill="#2D63E0"/>' +
  '<circle cx="16.35" cy="17.99" r="3.4" fill="#12A06A"/><circle cx="7.65" cy="17.99" r="3.4" fill="#3B1E6E"/>' +
  '<circle cx="4.96" cy="9.71" r="3.4" fill="#EC3E7B"/>'
const icon = (size: number) =>
  img(
    `data:image/svg+xml;base64,${Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">${ICON}</svg>`).toString("base64")}`,
    size,
    size
  )

const brand = () =>
  h(
    { alignItems: "center", gap: 10, fontFamily: "Dinsical", fontWeight: 700, fontSize: 20 },
    icon(28),
    "The Bias Index"
  )

// satori sizes boxes without their padding, so the card subtracts it to fill exactly 1200 × 630.
const PAD_X = 72
const PAD_Y = 64
const card = (style: Record<string, unknown>, ...children: Node[]) =>
  h(
    {
      width: W - 2 * PAD_X,
      height: H - 2 * PAD_Y,
      padding: `${PAD_Y}px ${PAD_X}px`,
      background: "#ffffff",
      color: INK,
      fontFamily: "Monsical",
      ...style,
    },
    ...children
  )

/** The company's red flags as one bar, a segment per question. */
const bar = (company: Company, width: number) => {
  const total = Math.max(
    1,
    company.flags.reduce((sum, n) => sum + n, 0)
  )
  return h(
    { width, height: 22, borderRadius: 3, overflow: "hidden" },
    ...company.flags.map((n, i) =>
      h({ width: (n / total) * width, height: 22, background: QUESTIONS[i].color })
    )
  )
}

/** A company's card: its name, red flags per page, and its red flags by question. */
export function companyImage(company: Company): Promise<Uint8Array<ArrayBuffer>> {
  const width = W - 2 * PAD_X
  // Long names shrink to fit: Dinsical Bold averages about 0.56em a character.
  const nameSize = Math.min(160, Math.floor(width / (company.company.length * 0.56)))
  const scored = company.status === "ok" && company.scoredPages > 0
  const address = `thebiasindex.com/${company.slug}`
  return png(
    card(
      { flexDirection: "column", justifyContent: "space-between" },
      brand(),
      h(
        { flexDirection: "column", gap: 24 },
        h(
          {
            fontFamily: "Dinsical",
            fontWeight: 700,
            fontSize: nameSize,
            lineHeight: 0.9,
            letterSpacing: "-0.045em",
          },
          company.company
        ),
        h(
          { fontSize: 28, lineHeight: 1.4 },
          scored
            ? `${perPage(company)} red flags per comparison page, out of 5.`
            : `${unrankedStatus(company)}.`
        )
      ),
      h(
        { flexDirection: "column", gap: 18 },
        ...(company.biasLoad > 0 ? [bar(company, width)] : []),
        h(
          { justifyContent: "space-between", fontSize: 18, color: MUTED },
          h(
            {},
            scored
              ? `${fmt(company.biasLoad)} red flags across ${fmt(company.scoredPages)} page${company.scoredPages === 1 ? "" : "s"}`
              : ""
          ),
          h({}, address)
        )
      )
    )
  )
}

/** The site's card: the question, and the three numbers. */
export function siteImage(): Promise<Uint8Array<ArrayBuffer>> {
  const all = companies()
  const facts = [
    [fmt(all.length), "Companies"],
    [fmt(all.reduce((sum, c) => sum + c.scoredPages, 0)), "Compare pages"],
    [fmt(all.reduce((sum, c) => sum + c.biasLoad, 0)), "Red flags"],
  ]
  return png(
    card(
      { flexDirection: "column", justifyContent: "space-between" },
      brand(),
      h(
        {
          maxWidth: 900,
          fontFamily: "Dinsical",
          fontWeight: 700,
          fontSize: 92,
          lineHeight: 0.96,
          letterSpacing: "-0.025em",
        },
        "How fair are SaaS comparison pages?"
      ),
      h(
        { borderTop: `1px solid ${INK}` },
        ...facts.map(([value, label]) =>
          h(
            { flexDirection: "column", width: (W - 2 * PAD_X) / 3, paddingTop: 20 },
            h(
              {
                fontFamily: "Dinsical",
                fontWeight: 700,
                fontSize: 48,
                letterSpacing: "-0.02em",
                lineHeight: 1.15,
              },
              value
            ),
            h({ fontSize: 16, color: MUTED }, label)
          )
        )
      )
    )
  )
}
