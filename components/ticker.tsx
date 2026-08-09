"use client"

import { useEffect, useState } from "react"
import { getApiBase, getWsUrl, type TxEvent } from "@/lib/api"

type TickerItem = {
  name: string
  coords: string
  speed: string
  tx: string
}

function formatCoords(lat: number, lon: number): string {
  const ns = lat >= 0 ? "N" : "S"
  const ew = lon >= 0 ? "E" : "W"
  return `${Math.abs(lat).toFixed(1)}°${ns} ${Math.abs(lon).toFixed(1)}°${ew}`
}

function VesselEntry({ vessel }: { vessel: TickerItem }) {
  return (
    <span className="flex items-center gap-2 whitespace-nowrap">
      <span className="live-dot" aria-hidden="true" />
      <span className="text-white text-sm font-sans">{vessel.name}</span>
      <span className="text-muted-foreground text-xs font-mono">{vessel.coords}</span>
      <span className="text-muted-foreground text-xs font-mono">{vessel.speed}</span>
      <span className="text-teal-300/90 text-xs font-mono">tx: {vessel.tx}</span>
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

    const pushEvent = (tx: TxEvent) => {
      const name = (tx.vessel_name || `MMSI ${tx.mmsi}`).trim()
      const item: TickerItem = {
        name,
        coords: formatCoords(tx.lat, tx.lon),
        speed: `${Number(tx.speed || 0).toFixed(0)}kn`,
        tx: `${String(tx.txid || "").slice(0, 8)}…`,
      }
      setItems((prev) => [item, ...prev].slice(0, 24))
      setLive(true)
    }

    const connect = () => {
      if (!wsUrl || closed) return
      ws = new WebSocket(wsUrl)
      ws.onopen = () => setLive(true)
      ws.onclose = () => {
        setLive(false)
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

    connect()
    return () => {
      closed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [])

  const display =
    items.length > 0
      ? items
      : [
          {
            name: live ? "Awaiting next vessel record…" : "Connecting to live fleet…",
            coords: "—",
            speed: "—",
            tx: "—",
          },
        ]

  return (
    <div
      id="presence"
      className="w-full border-y border-white/8 bg-black/35 backdrop-blur-sm overflow-hidden py-3 scroll-mt-24"
      aria-label="Live vessel tracking ticker"
    >
      <div className="marquee-content flex items-center">
        {[...display, ...display].map((vessel, index) => (
          <div key={`${vessel.name}-${index}`} className="flex items-center">
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
