"use client"

import { Copy, ExternalLink, Link2, Route, X } from "lucide-react"
import type { VesselSummary } from "@/lib/api"
import { WHATS_ON_CHAIN_TX } from "@/lib/site"
import { trackEvent } from "@/lib/analytics"
import { VesselSilhouette, vesselKindDetail, vesselKindLabel } from "@/components/live/vessel-silhouette"

type VesselPanelProps = {
  vessel: VesselSummary | null
  onClose: () => void
  showTrail?: boolean
  trailCount?: number
  trailLoading?: boolean
  onToggleTrail?: () => void
}

async function copyText(label: string, value: string) {
  try {
    await navigator.clipboard.writeText(value)
    trackEvent("copy_vessel_field", { field: label })
  } catch {
    // ignore
  }
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-white/6">
      <span className="text-[11px] uppercase tracking-[0.16em] text-white/40">{label}</span>
      <span className="text-sm text-white/90 text-right font-mono break-all">{value}</span>
    </div>
  )
}

export function VesselPanel({
  vessel,
  onClose,
  showTrail = false,
  trailCount = 0,
  trailLoading = false,
  onToggleTrail,
}: VesselPanelProps) {
  if (!vessel) return null

  const title = vessel.name || `MMSI ${vessel.mmsi}`
  const shareUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/live?mmsi=${encodeURIComponent(vessel.mmsi)}`
      : `/live?mmsi=${encodeURIComponent(vessel.mmsi)}`
  const heading =
    vessel.heading == null ? "—" : `${vessel.heading}°`
  const when = vessel.timestamp
    ? new Date(vessel.timestamp * 1000).toLocaleString("en-GB", {
        timeZone: "UTC",
        dateStyle: "medium",
        timeStyle: "short",
      }) + " UTC"
    : "—"

  return (
    <aside
      className="live-panel absolute z-20 left-3 right-3 bottom-3 md:left-auto md:right-4 md:top-24 md:bottom-auto md:w-[360px] rounded-2xl p-5"
      aria-label={`Vessel details for ${title}`}
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.18em] text-teal-300/80 mb-1">
            {vesselKindLabel(vessel.ship_type, vessel.name, vessel.length_m, vessel.beam_m)}
          </p>
          <h2 className="font-heading text-2xl tracking-wide text-white leading-tight">{title}</h2>
        </div>
        <div className="flex items-start gap-1 shrink-0">
          <div className="w-40 opacity-90">
            <VesselSilhouette
              shipType={vessel.ship_type}
              name={vessel.name}
              lengthM={vessel.length_m}
              beamM={vessel.beam_m}
            />
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-white/50 hover:text-white transition-colors"
            aria-label="Close vessel panel"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="space-y-0">
        <Row label="Type" value={vesselKindDetail(vessel.ship_type, vessel.name, vessel.length_m, vessel.beam_m)} />
        <Row label="MMSI" value={vessel.mmsi} />
        <Row label="Call sign" value={vessel.call_sign || "—"} />
        <Row label="IMO" value={vessel.imo || "—"} />
        <Row label="Destination" value={vessel.destination || "—"} />
        <Row label="Speed" value={`${vessel.speed.toFixed(1)} kn`} />
        <Row label="Heading" value={heading} />
        <Row
          label="Position"
          value={`${vessel.lat.toFixed(4)}, ${vessel.lon.toFixed(4)}`}
        />
        <Row label="Last seen" value={when} />
        <Row
          label="Last Bitcoin tx"
          value={
            vessel.last_txid
              ? `0-conf · ${vessel.last_txid.slice(0, 16)}…`
              : "Not broadcast yet"
          }
        />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {onToggleTrail && (
          <button
            type="button"
            disabled={trailLoading}
            className={`!py-2 !px-3 text-xs inline-flex items-center gap-1.5 ${
              showTrail ? "btn-neon" : "btn-outline-neon"
            } ${trailLoading ? "opacity-60 cursor-wait" : ""}`}
            onClick={onToggleTrail}
            aria-pressed={showTrail}
          >
            <Route size={14} aria-hidden="true" />
            {trailLoading
              ? "Loading…"
              : showTrail
                ? `Hide route (${trailCount})`
                : "Show route"}
          </button>
        )}
        <button
          type="button"
          className="btn-outline-neon !py-2 !px-3 text-xs inline-flex items-center gap-1.5"
          onClick={() => {
            void copyText("link", shareUrl)
            trackEvent("share_copied", { mmsi: vessel.mmsi })
          }}
        >
          <Link2 size={14} aria-hidden="true" />
          Copy link
        </button>
        <button
          type="button"
          className="btn-outline-neon !py-2 !px-3 text-xs inline-flex items-center gap-1.5"
          onClick={() => void copyText("mmsi", vessel.mmsi)}
        >
          <Copy size={14} aria-hidden="true" />
          Copy MMSI
        </button>
        {vessel.last_txid && (
          <>
            <button
              type="button"
              className="btn-outline-neon !py-2 !px-3 text-xs inline-flex items-center gap-1.5"
              onClick={() => void copyText("txid", vessel.last_txid!)}
            >
              <Copy size={14} aria-hidden="true" />
              Copy txid
            </button>
            <a
              href={WHATS_ON_CHAIN_TX(vessel.last_txid)}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-neon !py-2 !px-3 text-xs inline-flex items-center gap-1.5"
            >
              Explorer
              <ExternalLink size={14} aria-hidden="true" />
            </a>
          </>
        )}
      </div>
    </aside>
  )
}
