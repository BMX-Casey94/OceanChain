"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import dynamic from "next/dynamic"
import { useSearchParams } from "next/navigation"
import Link from "next/link"
import { BrandMark } from "@/components/brand-mark"
import { LiveSearch, type SearchSelection } from "@/components/live/live-search"
import { VesselPanel } from "@/components/live/vessel-panel"

const VesselMap = dynamic(
  () => import("@/components/live/vessel-map").then((m) => m.VesselMap),
  {
    ssr: false,
    loading: () => (
      <div className="live-map-root flex items-center justify-center text-white/50 text-sm">
        Loading chart…
      </div>
    ),
  }
)
import {
  fetchApiHealth,
  fetchVessel,
  fetchVessels,
  getApiBase,
  getWsUrl,
  type ApiHealth,
  type TxEvent,
  type VesselSummary,
} from "@/lib/api"
import { trackEvent } from "@/lib/analytics"

type ConnState = "connecting" | "connected" | "reconnecting" | "limited" | "offline"

function upsertVessel(list: VesselSummary[], next: VesselSummary): VesselSummary[] {
  const idx = list.findIndex((v) => v.mmsi === next.mmsi)
  if (idx === -1) return [next, ...list].slice(0, 20000)
  const copy = list.slice()
  copy[idx] = { ...copy[idx], ...next }
  return copy
}

export function LiveApp() {
  const searchParams = useSearchParams()
  const [vessels, setVessels] = useState<VesselSummary[]>([])
  const [selectedMmsi, setSelectedMmsi] = useState<string | null>(null)
  const [conn, setConn] = useState<ConnState>("connecting")
  const [pulseMmsi, setPulseMmsi] = useState<string | null>(null)
  const [flyTo, setFlyTo] = useState<{
    lon: number
    lat: number
    zoom?: number
    key: number
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<ApiHealth | null>(null)
  const [chartUnavailable, setChartUnavailable] = useState(false)

  const selected = useMemo(
    () => vessels.find((v) => v.mmsi === selectedMmsi) ?? null,
    [vessels, selectedMmsi]
  )

  const selectVessel = useCallback((mmsi: string, fly = true) => {
    setSelectedMmsi(mmsi)
    trackEvent("vessel_opened", { mmsi })
    const match = vessels.find((v) => v.mmsi === mmsi)
    if (fly && match) {
      setFlyTo({ lon: match.lon, lat: match.lat, zoom: 8, key: Date.now() })
    }
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href)
      url.searchParams.set("mmsi", mmsi)
      window.history.replaceState({}, "", url.toString())
    }
  }, [vessels])

  const loadVessels = useCallback(async (opts?: {
    near?: { lat: number; lon: number }
    bbox?: string
  }) => {
    if (!getApiBase()) {
      setConn("limited")
      setError("Live API is not configured. Set NEXT_PUBLIC_API_BASE to connect the fleet.")
      return
    }
    try {
      setError(null)
      const data = await fetchVessels(
        opts?.near
          ? { near: `${opts.near.lat},${opts.near.lon}`, radius_nm: 120, limit: 5000 }
          : opts?.bbox
            ? { bbox: opts.bbox, limit: 12000 }
            : { limit: 12000 }
      )
      setVessels(data)
      setConn((c) => (c === "offline" ? c : "connected"))
    } catch {
      setError(
        `No response from the Ocechain API at ${getApiBase()}. Start the backend, or point NEXT_PUBLIC_API_BASE at your VPS.`
      )
      setConn("limited")
    }
  }, [])

  useEffect(() => {
    void loadVessels()
  }, [loadVessels])

  // Poll backend health so AIS rate-limit state is visible without overlapping the chart panel.
  useEffect(() => {
    if (!getApiBase()) return
    let cancelled = false

    const poll = async () => {
      const next = await fetchApiHealth()
      if (cancelled || !next) return
      setHealth(next)
      if (next.ais_rate_limited) {
        const mins = Math.max(1, Math.ceil((next.ais_rate_limited_for_seconds || 0) / 60))
        setError(
          `AISstream is rate-limiting this API key (HTTP 429). Connection attempts — not open-socket messages — are throttled on the free tier. Retrying in ~${mins} min. Leave one backend process running; do not open a second client with the same key.`
        )
      } else if (
        next.ais_connected === false &&
        (next.ais_vessels ?? 0) === 0 &&
        next.ais_last_error
      ) {
        setError(`AIS ingest not connected yet: ${next.ais_last_error}`)
      } else if ((next.ais_vessels ?? 0) === 0 && next.ais_connected) {
        setError("AIS connected — waiting for the first position reports…")
      } else if ((next.ais_vessels ?? 0) > 0) {
        setError(null)
      }
    }

    void poll()
    const id = setInterval(() => void poll(), 8000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  // Deep links
  useEffect(() => {
    const mmsi = searchParams.get("mmsi")
    const q = searchParams.get("q")
    const lat = searchParams.get("lat")
    const lon = searchParams.get("lon")
    const z = searchParams.get("z")

    if (lat && lon) {
      const la = Number(lat)
      const lo = Number(lon)
      if (Number.isFinite(la) && Number.isFinite(lo)) {
        setFlyTo({
          lon: lo,
          lat: la,
          zoom: z ? Number(z) : 7,
          key: Date.now(),
        })
        void loadVessels({ near: { lat: la, lon: lo } })
      }
    }

    if (mmsi) {
      void (async () => {
        try {
          const detail = await fetchVessel(mmsi)
          if (detail) {
            setVessels((prev) => upsertVessel(prev, detail))
            setSelectedMmsi(detail.mmsi)
            setFlyTo({
              lon: detail.lon,
              lat: detail.lat,
              zoom: 8,
              key: Date.now(),
            })
          } else {
            selectVessel(mmsi)
          }
        } catch {
          selectVessel(mmsi)
        }
      })()
    }

    if (q && !mmsi) {
      // search component picks up initialQuery; also try direct vessel search
      void (async () => {
        try {
          const { searchVessels } = await import("@/lib/api")
          const hits = await searchVessels(q, 1)
          if (hits[0]) {
            setVessels((prev) => upsertVessel(prev, hits[0]))
            setSelectedMmsi(hits[0].mmsi)
            setFlyTo({
              lon: hits[0].lon,
              lat: hits[0].lat,
              zoom: 8,
              key: Date.now(),
            })
          }
        } catch {
          // ignore
        }
      })()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  // WebSocket live patches
  useEffect(() => {
    const wsUrl = getWsUrl()
    if (!wsUrl) {
      if (!getApiBase()) setConn("offline")
      return
    }

    let closed = false
    let ws: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let pulseTimer: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      if (closed) return
      setConn((c) => (c === "connected" ? c : "reconnecting"))
      ws = new WebSocket(wsUrl)
      ws.onopen = () => setConn("connected")
      ws.onclose = () => {
        if (!closed) {
          setConn("reconnecting")
          timer = setTimeout(connect, 3500)
        }
      }
      ws.onerror = () => ws?.close()
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string)
          if (msg.type !== "tx" || !msg.data) return
          const tx = msg.data as TxEvent
          const next: VesselSummary = {
            mmsi: String(tx.mmsi),
            name: tx.vessel_name || "",
            call_sign: tx.call_sign || "",
            destination: tx.destination || "",
            imo: tx.imo || "",
            ship_type: tx.ship_type ?? null,
            lat: tx.lat,
            lon: tx.lon,
            speed: tx.speed,
            heading: tx.heading ?? null,
            timestamp: tx.timestamp,
            last_txid: tx.txid,
            fee_sat: tx.fee_sat ?? null,
          }
          setVessels((prev) => upsertVessel(prev, next))
          setPulseMmsi(next.mmsi)
          if (pulseTimer) clearTimeout(pulseTimer)
          pulseTimer = setTimeout(() => setPulseMmsi(null), 1600)
        } catch {
          // ignore
        }
      }
    }

    connect()
    return () => {
      closed = true
      if (timer) clearTimeout(timer)
      if (pulseTimer) clearTimeout(pulseTimer)
      ws?.close()
    }
  }, [])

  const onSearchSelect = (selection: SearchSelection) => {
    trackEvent("search_performed", { kind: selection.kind })
    if (selection.kind === "vessel") {
      setVessels((prev) => upsertVessel(prev, selection.vessel))
      setSelectedMmsi(selection.vessel.mmsi)
      setFlyTo({
        lon: selection.vessel.lon,
        lat: selection.vessel.lat,
        zoom: 8,
        key: Date.now(),
      })
      const url = new URL(window.location.href)
      url.searchParams.set("mmsi", selection.vessel.mmsi)
      url.searchParams.delete("q")
      window.history.replaceState({}, "", url.toString())
      return
    }
    setFlyTo({
      lon: selection.place.lon,
      lat: selection.place.lat,
      zoom: 7,
      key: Date.now(),
    })
    void loadVessels({ near: { lat: selection.place.lat, lon: selection.place.lon } })
    const url = new URL(window.location.href)
    url.searchParams.set("lat", String(selection.place.lat))
    url.searchParams.set("lon", String(selection.place.lon))
    url.searchParams.set("z", "7")
    window.history.replaceState({}, "", url.toString())
  }

  const statusLabel =
    conn === "connected"
      ? "Connected"
      : conn === "reconnecting"
        ? "Reconnecting"
        : conn === "limited"
          ? "Limited"
          : conn === "offline"
            ? "Offline"
            : "Connecting"

  const aisLabel = health?.ais_rate_limited
    ? "AIS rate-limited"
    : health?.ais_connected
      ? `${(health.ais_vessels ?? vessels.length).toLocaleString("en-GB")} vessels`
      : vessels.length > 0
        ? `${vessels.length.toLocaleString("en-GB")} vessels`
        : "AIS offline"

  return (
    <div className="live-shell">
      <VesselMap
        vessels={vessels}
        selectedMmsi={selectedMmsi}
        onSelect={(mmsi) => selectVessel(mmsi)}
        flyTo={flyTo}
        pulseMmsi={pulseMmsi}
        onAvailabilityChange={(available) => setChartUnavailable(!available)}
      />

      <div className="absolute z-20 top-0 left-0 right-0 p-3 md:p-4 pointer-events-none">
        <div className="flex flex-col md:flex-row md:items-start gap-3 md:gap-4 pointer-events-auto">
          <div className="live-panel rounded-xl px-3 py-2 flex items-center gap-3">
            <BrandMark href="/" compact />
            <span
              className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.14em] text-white/55"
              aria-live="polite"
            >
              <span
                className={`live-dot ${conn === "connected" && !health?.ais_rate_limited ? "" : "opacity-40"}`}
                aria-hidden="true"
              />
              {statusLabel}
              <span className="text-white/30">·</span>
              <span className="normal-case tracking-normal text-white/45">{aisLabel}</span>
            </span>
          </div>
          <div className="flex-1">
            <LiveSearch
              onSelect={onSearchSelect}
              initialQuery={searchParams.get("q") || ""}
            />
          </div>
          <Link
            href="/"
            className="live-panel rounded-xl px-3 py-2.5 text-sm text-white/70 hover:text-teal-300 transition-colors self-start"
          >
            About Ocechain
          </Link>
        </div>
      </div>

      {/* Fleet/AIS status only — never centred over the chart panel. */}
      {error && (
        <div className="absolute z-20 left-3 right-3 top-36 md:left-auto md:right-4 md:top-28 md:max-w-sm live-panel rounded-xl px-4 py-3 text-sm text-amber-100/90">
          {error}
        </div>
      )}

      {chartUnavailable && vessels.length === 0 && !error && (
        <div className="absolute z-20 left-3 right-3 bottom-10 md:left-4 md:right-auto md:bottom-8 md:max-w-sm live-panel rounded-xl px-4 py-3 text-sm text-white/60">
          Chart needs WebGL. Vessel search still works once AIS delivers positions.
        </div>
      )}

      <VesselPanel vessel={selected} onClose={() => setSelectedMmsi(null)} />

      <p className="absolute z-10 bottom-2 left-3 text-[10px] text-white/35 max-w-md">
        Not a navigational aid. AIS via AISstream. Positions may also be recorded on Bitcoin.
      </p>
    </div>
  )
}
