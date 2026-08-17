import { classifyShip, type ShipKind } from "@/lib/ship-kind"

function Hull({ kind }: { kind: ShipKind }) {
  switch (kind) {
    case "cruise":
      return (
        <>
          <path d="M6 50 L16 42 H90 L96 50 L92 56 H10 Z" fill="currentColor" />
          <rect x="22" y="28" width="58" height="14" rx="1" fill="currentColor" opacity="0.88" />
          <rect x="28" y="18" width="46" height="10" rx="1" fill="currentColor" opacity="0.75" />
          <rect x="36" y="10" width="22" height="8" rx="1" fill="currentColor" opacity="0.65" />
          <rect x="62" y="6" width="5" height="10" fill="currentColor" opacity="0.55" />
          <rect x="70" y="4" width="5" height="12" fill="currentColor" opacity="0.55" />
        </>
      )
    case "ferry":
      return (
        <>
          <path d="M8 52 L14 40 H86 L94 52 L88 56 H12 Z" fill="currentColor" />
          <rect x="20" y="26" width="56" height="14" rx="1.5" fill="currentColor" opacity="0.85" />
          <path d="M14 40 L8 52 H20 Z" fill="currentColor" opacity="0.7" />
          <rect x="28" y="30" width="8" height="6" fill="#020b12" opacity="0.35" />
          <rect x="42" y="30" width="8" height="6" fill="#020b12" opacity="0.35" />
          <rect x="56" y="30" width="8" height="6" fill="#020b12" opacity="0.35" />
        </>
      )
    case "passenger":
      return (
        <>
          <path d="M10 52 L18 40 H84 L92 52 L86 56 H14 Z" fill="currentColor" />
          <rect x="24" y="28" width="52" height="12" rx="1" fill="currentColor" opacity="0.82" />
          <rect x="32" y="20" width="28" height="8" rx="1" fill="currentColor" opacity="0.7" />
        </>
      )
    case "cargo":
      return (
        <>
          <path d="M4 52 L14 40 H88 L98 52 L92 56 H8 Z" fill="currentColor" />
          <rect x="18" y="24" width="14" height="16" fill="currentColor" opacity="0.55" />
          <rect x="34" y="20" width="14" height="20" fill="currentColor" opacity="0.7" />
          <rect x="50" y="24" width="14" height="16" fill="currentColor" opacity="0.55" />
          <rect x="66" y="22" width="12" height="18" fill="currentColor" opacity="0.65" />
          <rect x="80" y="30" width="10" height="10" fill="currentColor" opacity="0.9" />
        </>
      )
    case "tanker":
      return (
        <>
          <path d="M4 50 L12 42 H86 L96 50 L90 56 H8 Z" fill="currentColor" />
          <ellipse cx="38" cy="40" rx="22" ry="6" fill="currentColor" opacity="0.45" />
          <ellipse cx="62" cy="40" rx="16" ry="5" fill="currentColor" opacity="0.35" />
          <rect x="78" y="28" width="12" height="14" fill="currentColor" opacity="0.9" />
          <path d="M20 38 H70" stroke="currentColor" strokeWidth="1.4" opacity="0.5" />
        </>
      )
    case "fishing":
      return (
        <>
          <path d="M14 52 L22 42 H70 L82 52 L76 56 H18 Z" fill="currentColor" />
          <rect x="52" y="26" width="16" height="16" fill="currentColor" opacity="0.9" />
          <path d="M28 42 L36 18 H40 L34 42 Z" fill="currentColor" opacity="0.55" />
          <path d="M36 22 L58 30" stroke="currentColor" strokeWidth="1.6" opacity="0.7" />
        </>
      )
    case "sailing":
      return (
        <>
          <path d="M22 54 L30 48 H72 L80 54 L74 58 H26 Z" fill="currentColor" />
          <path d="M48 48 V12" stroke="currentColor" strokeWidth="2" />
          <path d="M48 14 L72 44 H48 Z" fill="currentColor" opacity="0.55" />
          <path d="M48 20 L28 44 H48 Z" fill="currentColor" opacity="0.35" />
        </>
      )
    case "pleasure":
      return (
        <>
          <path d="M24 52 L32 44 H68 L78 52 L72 56 H28 Z" fill="currentColor" />
          <path d="M40 44 L44 34 H58 L54 44 Z" fill="currentColor" opacity="0.85" />
          <path d="M28 50 Q50 46 74 50" stroke="currentColor" strokeWidth="1" fill="none" opacity="0.4" />
        </>
      )
    case "canal":
      return (
        <>
          <rect x="8" y="40" width="84" height="14" rx="2" fill="currentColor" />
          <rect x="36" y="28" width="22" height="12" rx="1" fill="currentColor" opacity="0.85" />
          <rect x="14" y="44" width="10" height="4" fill="#020b12" opacity="0.25" />
          <rect x="76" y="44" width="10" height="4" fill="#020b12" opacity="0.25" />
        </>
      )
    case "tug":
      return (
        <>
          <path d="M22 54 L28 44 H62 L74 54 L68 58 H26 Z" fill="currentColor" />
          <rect x="34" y="22" width="22" height="22" rx="2" fill="currentColor" opacity="0.9" />
          <rect x="38" y="26" width="6" height="5" fill="#020b12" opacity="0.3" />
          <rect x="48" y="26" width="4" height="8" fill="currentColor" opacity="0.55" />
        </>
      )
    case "hsc":
      return (
        <>
          <path d="M10 50 L40 36 H88 L96 46 L88 54 H18 Z" fill="currentColor" />
          <path d="M40 36 L52 24 H78 L70 36 Z" fill="currentColor" opacity="0.75" />
        </>
      )
    case "special":
      return (
        <>
          <path d="M16 52 L24 42 H76 L86 52 L80 56 H20 Z" fill="currentColor" />
          <rect x="42" y="24" width="16" height="18" fill="currentColor" opacity="0.85" />
          <circle cx="50" cy="20" r="5" fill="currentColor" opacity="0.5" />
        </>
      )
    default:
      return (
        <>
          <path d="M18 52 L26 42 H74 L84 52 L78 56 H22 Z" fill="currentColor" />
          <rect x="38" y="32" width="24" height="10" fill="currentColor" opacity="0.75" />
        </>
      )
  }
}

export function VesselSilhouette({
  shipType,
  name,
}: {
  shipType: number | null | undefined
  name?: string | null
}) {
  const { kind, label } = classifyShip(shipType, name)
  return (
    <svg
      viewBox="0 0 100 64"
      className="h-[4.5rem] w-full text-teal-200/85"
      role="img"
      aria-label={label}
    >
      <path
        d="M2 58 Q50 50 98 58"
        stroke="currentColor"
        strokeWidth="1.4"
        fill="none"
        opacity="0.28"
      />
      <Hull kind={kind} />
    </svg>
  )
}

export function vesselKindLabel(shipType: number | null | undefined, name?: string | null) {
  return classifyShip(shipType, name).label
}

export function vesselKindDetail(shipType: number | null | undefined, name?: string | null) {
  const { label, aisType } = classifyShip(shipType, name)
  if (aisType == null) return label
  return `${label} · AIS ${aisType}`
}
