"use client"

import { Copy, ExternalLink, Link2, Route, X } from "lucide-react"
import type { VesselSummary } from "@/lib/api"
import { WHATS_ON_CHAIN_TX } from "@/lib/site"
import { trackEvent } from "@/lib/analytics"

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

/** AIS ship_type (first digit = broad category). */
function shipTypeLabel(shipType: number | null | undefined): string {
  if (shipType == null || !Number.isFinite(shipType)) return "Vessel"
  const d = Math.floor(shipType / 10)
  switch (d) {
    case 3:
      return "Tug / pilot"
    case 4:
      return "High speed craft"
    case 5:
      return "Special craft"
    case 6:
      return "Passenger"
    case 7:
      return "Cargo"
    case 8:
      return "Tanker"
    case 9:
      return "Other"
    default:
      return shipType >= 30 && shipType <= 35 ? "Fishing" : "Vessel"
  }
}

function VesselSilhouette({ shipType }: { shipType: number | null | undefined }) {
  const d = shipType == null ? -1 : Math.floor(shipType / 10)
  const hull =
    d === 8 ? (
      <path
        d="M18 46 L26 34 H74 L82 46 L78 52 H22 Z M30 30 H70 V34 H30 Z"
        fill="currentColor"
        opacity="0.9"
      />
    ) : d === 6 ? (
      <path
        d="M16 48 L24 32 H76 L84 48 L80 54 H20 Z M28 26 H72 V32 H28 Z M36 20 H64 V26 H36 Z"
        fill="currentColor"
        opacity="0.9"
      />
    ) : d === 7 ? (
      <path
        d="M14 48 L22 36 H78 L86 48 L82 54 H18 Z M26 28 H44 V36 H26 Z M50 28 H74 V36 H50 Z"
        fill="currentColor"
        opacity="0.9"
      />
    ) : (
      <path
        d="M20 48 L28 38 H72 L80 48 L76 52 H24 Z M34 32 H66 V38 H34 Z"
        fill="currentColor"
        opacity="0.9"
      />
    )
  return (
    <svg
      viewBox="0 0 100 64"
      className="h-16 w-full text-teal-200/70"
      role="img"
      aria-label={shipTypeLabel(shipType)}
    >
      <path d="M4 58 Q50 52 96 58" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.35" />
      {hull}
    </svg>
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
            {shipTypeLabel(vessel.ship_type)}
          </p>
          <h2 className="font-heading text-2xl tracking-wide text-white leading-tight">{title}</h2>
        </div>
        <div className="flex items-start gap-1 shrink-0">
          <div className="w-24 opacity-80">
            <VesselSilhouette shipType={vessel.ship_type} />
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
          value={vessel.last_txid ? `${vessel.last_txid.slice(0, 14)}…` : "Pending / unavailable"}
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
