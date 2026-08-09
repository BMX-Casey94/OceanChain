"use client"

import { useEffect, useId, useMemo, useRef, useState } from "react"
import { MapPin, Search, Ship } from "lucide-react"
import {
  geocodePlaces,
  searchVessels,
  type GeocodeResult,
  type VesselSummary,
} from "@/lib/api"
import { trackEvent } from "@/lib/analytics"

export type SearchSelection =
  | { kind: "vessel"; vessel: VesselSummary }
  | { kind: "place"; place: GeocodeResult }

type LiveSearchProps = {
  onSelect: (selection: SearchSelection) => void
  initialQuery?: string
}

function parseCoords(q: string): GeocodeResult | null {
  const m = q.trim().match(/^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$/)
  if (!m) return null
  const lat = Number(m[1])
  const lon = Number(m[2])
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null
  return { label: `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon, type: "coordinates" }
}

export function LiveSearch({ onSelect, initialQuery = "" }: LiveSearchProps) {
  const listId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState(initialQuery)
  const [vessels, setVessels] = useState<VesselSummary[]>([])
  const [places, setPlaces] = useState<GeocodeResult[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        inputRef.current?.focus()
        setOpen(true)
      }
      if (e.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  useEffect(() => {
    if (initialQuery) setQ(initialQuery)
  }, [initialQuery])

  useEffect(() => {
    const query = q.trim()
    if (query.length < 2) {
      setVessels([])
      setPlaces([])
      return
    }

    const coords = parseCoords(query)
    if (coords) {
      setPlaces([coords])
      setVessels([])
      return
    }

    let cancelled = false
    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        const [shipHits, placeHits] = await Promise.all([
          searchVessels(query, 8).catch(() => []),
          geocodePlaces(query).catch(() => []),
        ])
        if (cancelled) return
        setVessels(shipHits)
        setPlaces(placeHits)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 220)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [q])

  const hasResults = vessels.length > 0 || places.length > 0

  const hint = useMemo(() => {
    if (loading) return "Searching…"
    if (q.trim().length < 2) return "Ship name, MMSI, port, or coordinates"
    if (!hasResults) return "No matches yet"
    return `${vessels.length} vessels · ${places.length} places`
  }, [loading, q, hasResults, vessels.length, places.length])

  return (
    <div className="relative w-full max-w-xl">
      <label className="sr-only" htmlFor="live-search">
        Search ships or locations
      </label>
      <div className="live-search-shell live-panel rounded-xl flex items-center gap-2 px-3 py-2.5">
        <Search className="text-teal-300/80 shrink-0" size={18} aria-hidden="true" />
        <input
          id="live-search"
          ref={inputRef}
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search ship or location…"
          className="live-search-input w-full bg-transparent text-sm text-white placeholder:text-white/35 outline-none border-0 shadow-none ring-0 focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0 focus-visible:shadow-none"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          autoComplete="off"
        />
        <kbd className="hidden sm:inline text-[10px] text-white/35 border border-white/10 rounded px-1.5 py-0.5">
          ⌘K
        </kbd>
      </div>
      <p className="mt-1.5 text-[11px] text-white/40 px-1">{hint}</p>

      {open && (hasResults || loading) && (
        <ul
          id={listId}
          role="listbox"
          className="live-panel absolute z-30 mt-2 w-full rounded-xl overflow-hidden max-h-80 overflow-y-auto"
        >
          {vessels.map((v) => (
            <li key={`v-${v.mmsi}`} role="option">
              <button
                type="button"
                className="w-full text-left px-4 py-3 hover:bg-teal-400/10 transition-colors flex items-start gap-3"
                onClick={() => {
                  trackEvent("search_selected", { kind: "vessel", mmsi: v.mmsi })
                  onSelect({ kind: "vessel", vessel: v })
                  setQ(v.name || v.mmsi)
                  setOpen(false)
                }}
              >
                <Ship size={16} className="text-teal-300 mt-0.5" aria-hidden="true" />
                <span>
                  <span className="block text-sm text-white">{v.name || `MMSI ${v.mmsi}`}</span>
                  <span className="block text-xs text-white/45 font-mono mt-0.5">
                    {v.mmsi}
                    {v.call_sign ? ` · ${v.call_sign}` : ""}
                  </span>
                </span>
              </button>
            </li>
          ))}
          {places.map((p) => (
            <li key={`p-${p.label}-${p.lat}`} role="option">
              <button
                type="button"
                className="w-full text-left px-4 py-3 hover:bg-teal-400/10 transition-colors flex items-start gap-3"
                onClick={() => {
                  trackEvent("search_selected", { kind: "place" })
                  onSelect({ kind: "place", place: p })
                  setQ(p.label)
                  setOpen(false)
                }}
              >
                <MapPin size={16} className="text-sky-300 mt-0.5" aria-hidden="true" />
                <span>
                  <span className="block text-sm text-white">{p.label}</span>
                  <span className="block text-xs text-white/45 font-mono mt-0.5">
                    {p.lat.toFixed(3)}, {p.lon.toFixed(3)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
