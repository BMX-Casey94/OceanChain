"use client"

import { useEffect, useState } from "react"
import {
  fetchApiHealth,
  fetchTickerBroadcasts,
  getApiBase,
  getWsUrl,
  type TxEvent,
} from "@/lib/api"
import { WHATS_ON_CHAIN_TX } from "@/lib/site"

type TickerItem = {
  key: string
  name: string
  coords: string
  speed: string
  tx: string
  txid?: string
}

const TICKER_POLL_MS = 10_000
const TICKER_LIMIT = 24
const MARQUEE_MIN_ITEMS = 16

function formatCoords(lat: number, lon: number): string {
  const ns = lat >= 0 ? "N" : "S"
  const ew = lon >= 0 ? "E" : "W"
  return `${Math.abs(lat).toFixed(1)}°${ns} ${Math.abs(lon).toFixed(1)}°${ew}`
}

function toTickerItem(tx: TxEvent): TickerItem | null {
  const txid = String(tx.txid || "").trim()
  const mmsi = String(tx.mmsi || "").trim()
  if (!txid || !mmsi) return null
  const lat = Number(tx.lat)
  const lon = Number(tx.lon)
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
  const name = (tx.vessel_name || `MMSI ${mmsi}`).trim()
  return {
    key: `${txid}:${mmsi}`,
    name,
    coords: formatCoords(lat, lon),
    speed: `${Number(tx.speed || 0).toFixed(0)}kn`,
    tx: `${txid.slice(0, 8)}…`,
    txid,
  }
}

function isBsvTxid(value: string): boolean {
  return /^[0-9a-fA-F]{64}$/.test(value)
}

function mergeItems(prev: TickerItem[], incoming: TickerItem[]): TickerItem[] {
  const seen = new Set<string>()
  const out: TickerItem[] = []
  for (const item of [...incoming, ...prev]) {
    if (seen.has(item.key)) continue
    seen.add(item.key)
    out.push(item)
    if (out.length >= TICKER_LIMIT) break
  }
  return out
}

function fillSequence(items: TickerItem[]): TickerItem[] {
  if (items.length === 0) return items
  const out = [...items]
  while (out.length < MARQUEE_MIN_ITEMS) {
    out.push(...items)
  }
  return out
}

function VesselEntry({ vessel }: { vessel: TickerItem }) {
  return (
    <span className="flex items-center gap-2 whitespace-nowrap">
      <span className="live-dot" aria-hidden="true" />
      <span className="text-white text-sm font-sans">{vessel.name}</span>
      <span className="text-muted-foreground text-xs font-mono">{vessel.coords}</span>
      <span className="text-muted-foreground text-xs font-mono">{vessel.speed}</span>
      <span className="text-teal-300/90 text-xs font-mono">
        tx:{" "}
        {vessel.txid && isBsvTxid(vessel.txid) ? (
          <a
            href={WHATS_ON_CHAIN_TX(vessel.txid)}
            target="_blank"
            rel="noopener noreferrer"
            title="View this transaction on WhatsOnChain"
            className="underline decoration-teal-400/40 underline-offset-2 hover:text-teal-200 hover:decoration-teal-200"
            onClick={(event) => event.stopPropagation()}
          >
            {vessel.tx}
          </a>
        ) : (
          vessel.tx
        )}
      </span>
    </span>
  )
}

export function Ticker() {
  const [items, setItems] = useState<TickerItem[]>([])
  const [live, setLive] = useState(false)

  useEffect(() => {
    const base = getApiBase()
    const wsUrl = getWsUrl()
    if (!base && !wsUrl) return

    let closed = false
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let pollTimer: ReturnType<typeof setInterval> | undefined

    const pushEvent = (tx: TxEvent) => {
      const item = toTickerItem(tx)
      if (!item) return
      setItems((prev) => mergeItems(prev, [item]))
      setLive(true)
    }

    const seedFromRest = async () => {
      if (!base) return
      const rows = await fetchTickerBroadcasts(TICKER_LIMIT)
      if (closed) return
      const mapped = rows
        .map(toTickerItem)
        .filter((row): row is TickerItem => row !== null)
      if (mapped.length > 0) {
        setItems((prev) => mergeItems(prev, mapped))
        setLive(true)
        return
      }
      const health = await fetchApiHealth()
      if (closed) return
      if (health?.status === "ok") setLive(true)
    }

    const connect = () => {
      if (!wsUrl || closed) return
      ws = new WebSocket(wsUrl)
      ws.onopen = () => setLive(true)
      ws.onclose = () => {
        if (!closed) reconnectTimer = setTimeout(connect, 4000)
      }
      ws.onerror = () => ws?.close()
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string)
          if (msg.type === "tx" && msg.data) pushEvent(msg.data as TxEvent)
        } catch {
          // ignore malformed frames
        }
      }
    }

    void seedFromRest()
    if (base) {
      pollTimer = setInterval(() => {
        void seedFromRest()
      }, TICKER_POLL_MS)
    }
    connect()

    return () => {
      closed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (pollTimer) clearInterval(pollTimer)
      ws?.close()
    }
  }, [])

  const display =
    items.length > 0
      ? items
      : [
          {
            key: "placeholder",
            name: live ? "Awaiting next vessel record…" : "Connecting to live fleet…",
            coords: "—",
            speed: "—",
            tx: "—",
          },
        ]

  const sequence = fillSequence(display)
  const loop = [...sequence, ...sequence]

  return (
    <div
      id="presence"
      className="w-full border-y border-white/8 bg-black/35 backdrop-blur-sm overflow-hidden py-3 scroll-mt-24"
      aria-label="Live vessel tracking ticker"
    >
      <div className="marquee-content flex items-center">
        {loop.map((vessel, index) => (
          <div key={`${vessel.key}-${index}`} className="flex items-center">
            <VesselEntry vessel={vessel} />
            <span className="text-teal-400/40 mx-6" aria-hidden="true">
              |
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
