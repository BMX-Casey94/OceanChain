import { classifyShip, type ShipKind } from "@/lib/ship-kind"

/** Side-profile silhouettes, bow to the right, waterline ≈ y=58. */
function Hull({ kind }: { kind: ShipKind }) {
  switch (kind) {
    case "cruise":
      return (
        <>
          <path d="M4 58 L10 50 L18 48 H148 L156 54 L152 58 Z" fill="currentColor" />
          <path d="M22 48 H140 V36 H28 L22 42 Z" fill="currentColor" opacity="0.92" />
          <path d="M32 36 H128 V26 H38 L32 30 Z" fill="currentColor" opacity="0.8" />
          <path d="M44 26 H112 V18 H50 L44 21 Z" fill="currentColor" opacity="0.68" />
          <path d="M56 18 H92 V12 H60 Z" fill="currentColor" opacity="0.55" />
          <rect x="98" y="8" width="5" height="10" rx="0.6" fill="currentColor" opacity="0.5" />
          <rect x="108" y="6" width="5" height="12" rx="0.6" fill="currentColor" opacity="0.5" />
          <path d="M26 40 h6 v3 h-6 z M38 40 h6 v3 h-6 z M50 40 h6 v3 h-6 z M62 40 h6 v3 h-6 z M74 40 h6 v3 h-6 z M86 40 h6 v3 h-6 z M98 40 h6 v3 h-6 z M110 40 h6 v3 h-6 z" fill="#020b12" opacity="0.28" />
        </>
      )
    case "ferry":
      return (
        <>
          <path d="M10 58 L16 46 H132 L148 50 L154 58 Z" fill="currentColor" />
          <path d="M18 46 H128 V30 H24 L18 36 Z" fill="currentColor" opacity="0.9" />
          <path d="M132 46 L148 50 L142 36 H128 Z" fill="currentColor" opacity="0.75" />
          <rect x="30" y="34" width="10" height="7" fill="#020b12" opacity="0.3" />
          <rect x="48" y="34" width="10" height="7" fill="#020b12" opacity="0.3" />
          <rect x="66" y="34" width="10" height="7" fill="#020b12" opacity="0.3" />
          <rect x="84" y="34" width="10" height="7" fill="#020b12" opacity="0.3" />
          <rect x="102" y="34" width="10" height="7" fill="#020b12" opacity="0.3" />
          <rect x="70" y="22" width="18" height="8" rx="1" fill="currentColor" opacity="0.7" />
        </>
      )
    case "passenger":
      return (
        <>
          <path d="M8 58 L16 48 H140 L152 54 L148 58 Z" fill="currentColor" />
          <path d="M24 48 H132 V34 H30 L24 40 Z" fill="currentColor" opacity="0.88" />
          <path d="M40 34 H110 V24 H46 Z" fill="currentColor" opacity="0.72" />
          <rect x="118" y="20" width="6" height="14" fill="currentColor" opacity="0.5" />
        </>
      )
    case "cargo":
      return (
        <>
          <path d="M4 58 L12 50 H146 L156 56 L152 58 Z" fill="currentColor" />
          <rect x="18" y="28" width="16" height="22" fill="currentColor" opacity="0.55" />
          <rect x="36" y="22" width="16" height="28" fill="currentColor" opacity="0.7" />
          <rect x="54" y="26" width="16" height="24" fill="currentColor" opacity="0.55" />
          <rect x="72" y="20" width="16" height="30" fill="currentColor" opacity="0.75" />
          <rect x="90" y="26" width="16" height="24" fill="currentColor" opacity="0.55" />
          <path d="M112 50 H146 V32 H118 L112 38 Z" fill="currentColor" opacity="0.95" />
          <rect x="136" y="18" width="6" height="14" fill="currentColor" opacity="0.55" />
        </>
      )
    case "tanker":
      return (
        <>
          <path d="M4 58 L10 50 H146 L156 55 L150 58 Z" fill="currentColor" />
          <ellipse cx="48" cy="46" rx="28" ry="7" fill="currentColor" opacity="0.35" />
          <ellipse cx="88" cy="46" rx="22" ry="6" fill="currentColor" opacity="0.28" />
          <path d="M16 48 H118" stroke="currentColor" strokeWidth="1.6" opacity="0.45" />
          <circle cx="40" cy="44" r="2.2" fill="currentColor" opacity="0.55" />
          <circle cx="62" cy="44" r="2.2" fill="currentColor" opacity="0.55" />
          <circle cx="84" cy="44" r="2.2" fill="currentColor" opacity="0.55" />
          <path d="M122 50 H148 V34 H128 L122 40 Z" fill="currentColor" opacity="0.95" />
          <rect x="140" y="20" width="6" height="14" fill="currentColor" opacity="0.5" />
        </>
      )
    case "fishing":
      return (
        <>
          <path d="M28 58 L36 48 H118 L136 54 L130 58 Z" fill="currentColor" />
          <path d="M96 48 H122 V28 H100 L96 34 Z" fill="currentColor" opacity="0.95" />
          <path d="M48 48 L58 16 H64 L56 48 Z" fill="currentColor" opacity="0.55" />
          <path d="M62 20 L108 36" stroke="currentColor" strokeWidth="2" opacity="0.7" />
          <path d="M36 50 H88" stroke="currentColor" strokeWidth="2" opacity="0.25" />
        </>
      )
    case "sailing":
      return (
        <>
          <path d="M36 58 L46 50 H118 L128 58 Z" fill="currentColor" />
          <path d="M82 50 V10" stroke="currentColor" strokeWidth="2.2" />
          <path d="M82 12 L124 48 H82 Z" fill="currentColor" opacity="0.5" />
          <path d="M82 18 L48 48 H82 Z" fill="currentColor" opacity="0.32" />
        </>
      )
    case "pleasure":
      return (
        <>
          <path d="M40 58 L50 48 H118 L132 54 L126 58 Z" fill="currentColor" />
          <path d="M68 48 L74 34 H100 L96 48 Z" fill="currentColor" opacity="0.88" />
          <path d="M44 54 Q86 48 128 54" stroke="currentColor" strokeWidth="1.2" fill="none" opacity="0.35" />
        </>
      )
    case "canal":
      return (
        <>
          <rect x="8" y="44" width="144" height="14" rx="2" fill="currentColor" />
          <rect x="62" y="30" width="28" height="14" rx="1.5" fill="currentColor" opacity="0.88" />
          <rect x="16" y="48" width="14" height="4" fill="#020b12" opacity="0.22" />
          <rect x="130" y="48" width="14" height="4" fill="#020b12" opacity="0.22" />
        </>
      )
    case "tug":
      return (
        <>
          <path d="M38 58 L46 48 H108 L124 56 L118 58 Z" fill="currentColor" />
          <rect x="58" y="20" width="36" height="28" rx="2" fill="currentColor" opacity="0.95" />
          <rect x="64" y="26" width="8" height="6" fill="#020b12" opacity="0.32" />
          <rect x="80" y="18" width="5" height="10" fill="currentColor" opacity="0.55" />
          <path d="M40 52 H54" stroke="currentColor" strokeWidth="3" opacity="0.4" />
          <path d="M108 52 H122" stroke="currentColor" strokeWidth="3" opacity="0.4" />
        </>
      )
    case "hsc":
      return (
        <>
          <path d="M16 58 L56 40 H138 L154 50 L142 58 Z" fill="currentColor" />
          <path d="M64 40 L78 24 H118 L108 40 Z" fill="currentColor" opacity="0.78" />
          <path d="M20 56 L50 44" stroke="currentColor" strokeWidth="2" opacity="0.35" />
        </>
      )
    case "military":
      return (
        <>
          <path d="M12 58 L22 50 H138 L150 54 L146 58 Z" fill="currentColor" />
          <path d="M70 50 H100 V28 H78 L70 36 Z" fill="currentColor" opacity="0.9" />
          <path d="M86 28 V10" stroke="currentColor" strokeWidth="2" />
          <path d="M78 16 H94" stroke="currentColor" strokeWidth="1.6" />
          <rect x="40" y="44" width="18" height="6" fill="currentColor" opacity="0.45" />
        </>
      )
    case "dredger":
      return (
        <>
          <path d="M20 58 L28 48 H120 L134 56 L128 58 Z" fill="currentColor" />
          <rect x="88" y="28" width="24" height="20" fill="currentColor" opacity="0.9" />
          <path d="M96 30 L48 18 L44 22 L92 34 Z" fill="currentColor" opacity="0.55" />
          <circle cx="46" cy="20" r="5" fill="currentColor" opacity="0.45" />
        </>
      )
    case "pilot":
      return (
        <>
          <path d="M36 58 L46 46 H118 L132 54 L126 58 Z" fill="currentColor" />
          <path d="M70 46 H110 V26 H76 L70 32 Z" fill="currentColor" opacity="0.92" />
          <rect x="96" y="18" width="5" height="8" fill="currentColor" opacity="0.5" />
        </>
      )
    case "special":
      return (
        <>
          <path d="M24 58 L32 48 H124 L138 56 L132 58 Z" fill="currentColor" />
          <rect x="68" y="26" width="28" height="22" fill="currentColor" opacity="0.88" />
          <circle cx="82" cy="20" r="6" fill="currentColor" opacity="0.4" />
        </>
      )
    default:
      return (
        <>
          <path d="M22 58 L32 48 H128 L142 56 L136 58 Z" fill="currentColor" />
          <rect x="62" y="34" width="36" height="14" fill="currentColor" opacity="0.75" />
        </>
      )
  }
}

type SilhouetteProps = {
  shipType: number | null | undefined
  name?: string | null
  lengthM?: number | null
  beamM?: number | null
}

export function VesselSilhouette({ shipType, name, lengthM, beamM }: SilhouetteProps) {
  const { kind, label } = classifyShip({ shipType, name, lengthM, beamM })
  return (
    <svg
      viewBox="0 0 160 72"
      className="h-[4.75rem] w-[9.5rem] text-teal-200/90"
      role="img"
      aria-label={label}
    >
      <path
        d="M2 62 C40 56 80 54 158 62"
        stroke="currentColor"
        strokeWidth="1.3"
        fill="none"
        opacity="0.22"
      />
      <Hull kind={kind} />
    </svg>
  )
}

export function vesselKindLabel(
  shipType: number | null | undefined,
  name?: string | null,
  lengthM?: number | null,
  beamM?: number | null
) {
  return classifyShip({ shipType, name, lengthM, beamM }).label
}

export function vesselKindDetail(
  shipType: number | null | undefined,
  name?: string | null,
  lengthM?: number | null,
  beamM?: number | null
) {
  const { label, aisType } = classifyShip({ shipType, name, lengthM, beamM })
  const bits = [label]
  if (aisType != null) bits.push(`AIS ${aisType}`)
  if (lengthM != null && lengthM > 0) bits.push(`${Math.round(lengthM)} m`)
  return bits.join(" · ")
}
