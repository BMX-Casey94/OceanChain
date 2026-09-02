import { NextRequest, NextResponse } from "next/server"

type NominatimItem = {
  display_name?: string
  lat?: string
  lon?: string
  type?: string
  class?: string
}

const cache = new Map<string, { at: number; results: unknown }>()
const CACHE_TTL_MS = 1000 * 60 * 30
const RATE = new Map<string, number[]>()

function rateLimited(ip: string): boolean {
  const now = Date.now()
  const windowMs = 60_000
  const hits = (RATE.get(ip) || []).filter((t) => now - t < windowMs)
  if (hits.length >= 30) {
    RATE.set(ip, hits)
    return true
  }
  hits.push(now)
  RATE.set(ip, hits)
  return false
}

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q")?.trim() || ""
  if (q.length < 2 || q.length > 120) {
    return NextResponse.json({ results: [] })
  }

  const ip =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    request.headers.get("x-real-ip") ||
    "anon"
  if (rateLimited(ip)) {
    return NextResponse.json(
      { error: "Rate limit exceeded" },
      { status: 429 }
    )
  }

  const key = q.toLowerCase()
  const cached = cache.get(key)
  if (cached && Date.now() - cached.at < CACHE_TTL_MS) {
    return NextResponse.json({ results: cached.results })
  }

  const url = new URL("https://nominatim.openstreetmap.org/search")
  url.searchParams.set("q", q)
  url.searchParams.set("format", "json")
  url.searchParams.set("limit", "6")
  url.searchParams.set("addressdetails", "0")

  try {
    const res = await fetch(url.toString(), {
      headers: {
        "User-Agent": "Ocechain/1.0 (maritime intelligence; https://watching.boats)",
        Accept: "application/json",
      },
      next: { revalidate: 0 },
    })
    if (!res.ok) {
      return NextResponse.json({ results: [] }, { status: 502 })
    }
    const data = (await res.json()) as NominatimItem[]
    const results = data
      .map((item) => {
        const lat = Number(item.lat)
        const lon = Number(item.lon)
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
        return {
          label: item.display_name || `${lat}, ${lon}`,
          lat,
          lon,
          type: item.type || item.class || "place",
        }
      })
      .filter(Boolean)

    cache.set(key, { at: Date.now(), results })
    return NextResponse.json({ results })
  } catch {
    return NextResponse.json({ results: [] }, { status: 502 })
  }
}
