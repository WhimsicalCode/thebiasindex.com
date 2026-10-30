// /og/site.png: the share image for every page that isn't a company page.
import type { APIRoute } from "astro"
import { siteImage } from "@/lib/og"

export const GET: APIRoute = async () =>
  new Response(await siteImage(), { headers: { "Content-Type": "image/png" } })
