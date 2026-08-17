export type VesselSummary = {
  mmsi: string
  name: string
  call_sign: string
  destination: string
  imo: string
  ship_type: number | null
  lat: number
  lon: number
  speed: number
  heading: number | null
  timestamp: number
  last_txid?: string | null
  fee_sat?: number | null
}

export type StatsSummary = {
  txs_today: number
  active_vessels: number
  bsv_spent_today: number
  avg_fee_sat: number
  uptime_seconds: number
  uptime_pct: number
}

export type TxEvent = {
  txid: string
  mmsi: string
  vessel_name?: string
  call_sign?: string
  destination?: string
  imo?: string
  ship_type?: number | null
  lat: number
  lon: number
  speed: number
  heading?: number | null
  timestamp: number
  fee_sat?: number
  broadcaster?: string
}

export function getApiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/$/, "")
}

/**
 * WebSocket URL for live tx events.
 * Same-origin HTTP rewrites (/ocechain-api) cannot upgrade WebSockets — set
 * NEXT_PUBLIC_WS_URL to ws(s)://host:port/ws when using the proxy for REST.
 */
export function getWsUrl(): string {
  const explicit = (process.env.NEXT_PUBLIC_WS_URL || "").trim().replace(/\/$/, "")
  if (explicit) return explicit

  const base = getApiBase()
  if (!base) return ""
  if (base.startsWith("/")) return ""
  if (base.startsWith("https://")) return `${base.replace(/^https/, "wss")}/ws`
  if (base.startsWith("http://")) return `${base.replace(/^http/, "ws")}/ws`
  return ""
}

export type ApiHealth = {
  status: string
  ais_vessels?: number
  ais_connected?: boolean | null
  ais_messages?: number | null
  ais_rate_limited?: boolean | null
  ais_rate_limited_for_seconds?: number | null
  ais_last_error?: string | null
  uptime_seconds?: number
}

export async function fetchStatsSummary(): Promise<StatsSummary | null> {
  const base = getApiBase()
  if (!base) return null
  try {
    const res = await fetch(`${base}/stats/summary`, { cache: "no-store" })
    if (!res.ok) return null
    return (await res.json()) as StatsSummary
  } catch {
    return null
  }
}

export async function fetchApiHealth(): Promise<ApiHealth | null> {
  const base = getApiBase()
  if (!base) return null
  try {
    const res = await fetch(`${base}/health`, { cache: "no-store" })
    if (!res.ok) return null
    return (await res.json()) as ApiHealth
  } catch {
    return null
  }
}

export async function fetchVessels(params?: {
  bbox?: string
  near?: string
  radius_nm?: number
  limit?: number
}): Promise<VesselSummary[]> {
  const base = getApiBase()
  if (!base) return []
  const sp = new URLSearchParams()
  if (params?.bbox) sp.set("bbox", params.bbox)
  if (params?.near) sp.set("near", params.near)
  if (params?.radius_nm != null) sp.set("radius_nm", String(params.radius_nm))
  if (params?.limit != null) sp.set("limit", String(params.limit))
  const qs = sp.toString()
  const res = await fetch(`${base}/vessels${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
  })
  if (!res.ok) throw new Error("Failed to load vessels")
  const data = await res.json()
  return (data.vessels ?? data) as VesselSummary[]
}

export async function fetchVessel(mmsi: string): Promise<VesselSummary | null> {
  const base = getApiBase()
  if (!base) return null
  const res = await fetch(`${base}/vessels/${encodeURIComponent(mmsi)}`, {
    cache: "no-store",
  })
  if (res.status === 404) return null
  if (!res.ok) throw new Error("Failed to load vessel")
  return (await res.json()) as VesselSummary
}

export type TrailPoint = {
  lat: number
  lon: number
  timestamp: number
  txid?: string | null
}

export async function fetchVesselTrail(mmsi: string): Promise<TrailPoint[]> {
  const base = getApiBase()
  if (!base) return []
  const res = await fetch(`${base}/vessels/${encodeURIComponent(mmsi)}/trail`, {
    cache: "no-store",
  })
  if (!res.ok) return []
  const data = await res.json()
  return (data.points ?? []) as TrailPoint[]
}

export async function searchVessels(q: string, limit = 12): Promise<VesselSummary[]> {
  const base = getApiBase()
  if (!base) return []
  const sp = new URLSearchParams({ q, limit: String(limit) })
  const res = await fetch(`${base}/vessels/search?${sp}`, { cache: "no-store" })
  if (!res.ok) throw new Error("Search failed")
  const data = await res.json()
  return (data.results ?? data) as VesselSummary[]
}

export type GeocodeResult = {
  label: string
  lat: number
  lon: number
  type?: string
}

export async function geocodePlaces(q: string): Promise<GeocodeResult[]> {
  const sp = new URLSearchParams({ q })
  const res = await fetch(`/api/geocode?${sp}`, { cache: "no-store" })
  if (!res.ok) return []
  const data = await res.json()
  return (data.results ?? []) as GeocodeResult[]
}
