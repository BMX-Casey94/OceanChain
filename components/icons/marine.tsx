"use client"

/**
 * Dimensional maritime icons.
 *
 * Drawn free-standing (no plate, card, or bounding shape) so they read as
 * objects sitting on the page rather than glyphs in a box. Depth comes from
 * a shared light direction: highlights top-left, shadow faces bottom-right.
 *
 * Subtle CSS motion lives on named groups (see `.icon-marine-*` in globals.css)
 * and respects prefers-reduced-motion. Gradient ids are namespaced per instance.
 */

import { useId } from "react"

type IconProps = {
  size?: number
  className?: string
}

const TEAL = "#5eead4"
const TEAL_DEEP = "#0d9488"
const STEEL = "#94a3b8"
const STEEL_DEEP = "#334155"

function useIconId(prefix: string) {
  const reactId = useId().replace(/:/g, "")
  return `${prefix}-${reactId}`
}

function Defs({ id }: { id: string }) {
  return (
    <defs>
      <linearGradient id={`${id}-hull`} x1="0" y1="0" x2="0.7" y2="1">
        <stop offset="0%" stopColor={TEAL} />
        <stop offset="55%" stopColor={TEAL_DEEP} />
        <stop offset="100%" stopColor="#065f5b" />
      </linearGradient>
      <linearGradient id={`${id}-steel`} x1="0.1" y1="0" x2="0.9" y2="1">
        <stop offset="0%" stopColor="#e2e8f0" />
        <stop offset="45%" stopColor={STEEL} />
        <stop offset="100%" stopColor={STEEL_DEEP} />
      </linearGradient>
      <linearGradient id={`${id}-glass`} x1="0" y1="0" x2="0.6" y2="1">
        <stop offset="0%" stopColor="#ffffff" stopOpacity="0.55" />
        <stop offset="100%" stopColor="#ffffff" stopOpacity="0.04" />
      </linearGradient>
      <radialGradient id={`${id}-halo`} cx="0.5" cy="0.5" r="0.5">
        <stop offset="0%" stopColor={TEAL} stopOpacity="0.4" />
        <stop offset="100%" stopColor={TEAL} stopOpacity="0" />
      </radialGradient>
    </defs>
  )
}

/** Isometric container vessel — used for fleet / vessel concepts. */
export function ContainerShipIcon({ size = 72, className }: IconProps) {
  const id = useIconId("ship3d")
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <Defs id={id} />
      <ellipse
        className="icon-marine-halo"
        cx="48"
        cy="70"
        rx="38"
        ry="10"
        fill={`url(#${id}-halo)`}
      />

      <g className="icon-marine-bob">
        {/* hull: top deck plane then the shadowed side */}
        <path d="M14 52 L48 44 L86 52 L74 60 L26 60 Z" fill={`url(#${id}-steel)`} opacity="0.9" />
        <path d="M26 60 L74 60 L64 72 Q48 76 32 72 Z" fill={`url(#${id}-hull)`} />
        <path d="M26 60 L32 72 Q48 76 64 72 L74 60 Z" fill="#020b12" opacity="0.22" />

        {/* containers, stacked with lit tops */}
        <g>
          <path d="M32 36 L44 33 L44 45 L32 48 Z" fill={TEAL} opacity="0.85" />
          <path d="M44 33 L56 36 L56 48 L44 45 Z" fill={TEAL_DEEP} />
          <path d="M32 36 L44 33 L56 36 L44 39 Z" fill="#a7f3d0" opacity="0.9" />
        </g>
        <g>
          <path d="M56 40 L64 38 L64 48 L56 50 Z" fill={STEEL} opacity="0.75" />
          <path d="M64 38 L72 40 L72 50 L64 48 Z" fill={STEEL_DEEP} />
          <path d="M56 40 L64 38 L72 40 L64 42 Z" fill="#e2e8f0" opacity="0.8" />
        </g>

        {/* bridge tower */}
        <path d="M20 40 L28 38 L28 52 L20 54 Z" fill={STEEL} opacity="0.8" />
        <path d="M28 38 L34 40 L34 53 L28 52 Z" fill={STEEL_DEEP} />
        <path d="M22 43 L27 42 L27 46 L22 47 Z" fill={`url(#${id}-glass)`} />
      </g>

      {/* waterline */}
      <path
        className="icon-marine-wave"
        d="M8 74 Q24 70 40 74 T72 74 T90 71"
        stroke={TEAL}
        strokeOpacity="0.45"
        strokeWidth="1.5"
        strokeLinecap="round"
        fill="none"
      />
      <path
        className="icon-marine-wave icon-marine-wave-delayed"
        d="M14 82 Q30 78 46 82 T78 81"
        stroke={TEAL}
        strokeOpacity="0.2"
        strokeWidth="1.5"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  )
}

/** Radar / AIS reception. */
export function RadarIcon({ size = 72, className }: IconProps) {
  const id = useIconId("radar3d")
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <Defs id={id} />
      <ellipse
        className="icon-marine-halo"
        cx="48"
        cy="76"
        rx="30"
        ry="8"
        fill={`url(#${id}-halo)`}
      />

      {/* dish */}
      <g className="icon-marine-radar-dish">
        <path d="M26 44 Q48 16 70 44 Q48 56 26 44 Z" fill={`url(#${id}-steel)`} />
        <path d="M32 44 Q48 24 64 44 Q48 52 32 44 Z" fill={`url(#${id}-glass)`} opacity="0.5" />
        <path d="M26 44 Q48 56 70 44 Q48 60 26 44 Z" fill="#020b12" opacity="0.28" />
      </g>

      {/* mast and base */}
      <path d="M46 48 L52 48 L54 72 L44 72 Z" fill={STEEL_DEEP} />
      <path d="M46 48 L49 48 L49 72 L44 72 Z" fill={STEEL} opacity="0.7" />
      <ellipse cx="49" cy="74" rx="14" ry="4" fill={STEEL_DEEP} />
      <ellipse cx="49" cy="73" rx="14" ry="4" fill={`url(#${id}-steel)`} />

      {/* emission arcs */}
      <g stroke={TEAL} fill="none" strokeLinecap="round">
        <path className="icon-marine-ping" d="M70 30 Q80 34 82 44" strokeWidth="2" strokeOpacity="0.75" />
        <path
          className="icon-marine-ping icon-marine-ping-2"
          d="M74 22 Q90 30 90 46"
          strokeWidth="2"
          strokeOpacity="0.4"
        />
        <path
          className="icon-marine-ping icon-marine-ping-3"
          d="M78 14 Q98 26 96 48"
          strokeWidth="2"
          strokeOpacity="0.18"
        />
      </g>
      <circle className="icon-marine-beacon-core" cx="48" cy="30" r="3" fill={TEAL} />
    </svg>
  )
}

/** Chain link block — permanence / ledger. */
export function ChainBlockIcon({ size = 72, className }: IconProps) {
  const id = useIconId("block3d")
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <Defs id={id} />
      <ellipse
        className="icon-marine-halo"
        cx="48"
        cy="78"
        rx="30"
        ry="8"
        fill={`url(#${id}-halo)`}
      />

      {/* rear block */}
      <g className="icon-marine-block-rear" opacity="0.45">
        <path d="M54 26 L72 20 L86 26 L68 32 Z" fill="#a7f3d0" />
        <path d="M54 26 L68 32 L68 50 L54 44 Z" fill={TEAL_DEEP} />
        <path d="M68 32 L86 26 L86 44 L68 50 Z" fill="#065f5b" />
      </g>

      {/* front block */}
      <g className="icon-marine-block-front">
        <path d="M14 38 L40 28 L64 38 L38 48 Z" fill="#a7f3d0" />
        <path d="M14 38 L38 48 L38 74 L14 64 Z" fill={`url(#${id}-hull)`} />
        <path d="M38 48 L64 38 L64 64 L38 74 Z" fill="#04443f" />

        {/* etched record lines on the lit face */}
        <g stroke="#020b12" strokeOpacity="0.35" strokeWidth="1.5" strokeLinecap="round">
          <path d="M20 48 L31 52" />
          <path d="M20 55 L31 59" />
          <path d="M20 62 L27 65" />
        </g>
      </g>

      {/* connector between blocks */}
      <path
        className="icon-marine-link"
        d="M58 40 Q66 34 70 36"
        stroke={TEAL}
        strokeOpacity="0.7"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  )
}

/** Navigation buoy / beacon — verification, signalling. */
export function BeaconIcon({ size = 72, className }: IconProps) {
  const id = useIconId("beacon3d")
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <Defs id={id} />
      <ellipse
        className="icon-marine-halo"
        cx="48"
        cy="74"
        rx="30"
        ry="9"
        fill={`url(#${id}-halo)`}
      />

      <g className="icon-marine-bob-soft">
        {/* float body */}
        <path d="M34 52 L48 46 L62 52 L62 62 Q48 70 34 62 Z" fill={`url(#${id}-hull)`} />
        <path d="M34 52 L48 46 L62 52 L48 58 Z" fill="#a7f3d0" opacity="0.85" />
        <path d="M48 58 L62 52 L62 62 Q55 66 48 66 Z" fill="#020b12" opacity="0.25" />

        {/* lantern cage */}
        <path d="M42 34 L48 30 L54 34 L54 46 L48 49 L42 46 Z" fill={`url(#${id}-steel)`} opacity="0.85" />
        <path d="M44 36 L48 34 L52 36 L52 44 L48 46 L44 44 Z" fill={`url(#${id}-glass)`} />
        <circle className="icon-marine-beacon-core" cx="48" cy="40" r="3.5" fill={TEAL} />

        {/* light beams */}
        <g className="icon-marine-beams" stroke={TEAL} strokeLinecap="round" strokeWidth="2">
          <path d="M34 40 L24 38" strokeOpacity="0.55" />
          <path d="M62 40 L72 38" strokeOpacity="0.55" />
          <path d="M48 26 L48 18" strokeOpacity="0.4" />
        </g>
      </g>

      {/* water */}
      <path
        className="icon-marine-wave"
        d="M12 68 Q28 64 44 68 T76 68 T88 66"
        stroke={TEAL}
        strokeOpacity="0.4"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  )
}

/** Anchor with shield facets — risk, underwriting, claims. */
export function AnchorShieldIcon({ size = 72, className }: IconProps) {
  const id = useIconId("anchor3d")
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <Defs id={id} />
      <ellipse
        className="icon-marine-halo"
        cx="48"
        cy="80"
        rx="28"
        ry="7"
        fill={`url(#${id}-halo)`}
      />

      <g className="icon-marine-shield">
        <path d="M48 12 L74 22 V46 Q74 68 48 82 Q22 68 22 46 V22 Z" fill={`url(#${id}-hull)`} />
        <path d="M48 12 L74 22 V46 Q74 68 48 82 Z" fill="#020b12" opacity="0.22" />
        <path d="M48 18 L68 26 V46 Q68 63 48 75 Q28 63 28 46 V26 Z" fill="#020b12" opacity="0.28" />

        <g
          className="icon-marine-gleam"
          stroke="#a7f3d0"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        >
          <path d="M48 34 V60" />
          <path d="M40 40 H56" />
          <path d="M36 52 Q40 62 48 62 Q56 62 60 52" />
        </g>
        <circle cx="48" cy="30" r="4" stroke="#a7f3d0" strokeWidth="2.5" fill="none" />
      </g>
    </svg>
  )
}

/** Cargo crane / port operations. */
export function PortCraneIcon({ size = 72, className }: IconProps) {
  const id = useIconId("crane3d")
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <Defs id={id} />
      <ellipse
        className="icon-marine-halo"
        cx="48"
        cy="80"
        rx="32"
        ry="8"
        fill={`url(#${id}-halo)`}
      />

      {/* gantry legs */}
      <path d="M24 34 L30 34 L36 76 L28 76 Z" fill={`url(#${id}-steel)`} />
      <path d="M66 34 L72 34 L76 76 L68 76 Z" fill={STEEL_DEEP} />

      {/* boom */}
      <path d="M14 28 L84 22 L84 32 L14 38 Z" fill={`url(#${id}-steel)`} />
      <path d="M14 34 L84 28 L84 32 L14 38 Z" fill="#020b12" opacity="0.25" />

      {/* hoist */}
      <g className="icon-marine-hoist">
        <path d="M58 32 L58 50" stroke={TEAL} strokeOpacity="0.7" strokeWidth="1.5" />
        <path d="M50 50 L66 50 L64 60 L52 60 Z" fill={TEAL_DEEP} />
        <path d="M50 50 L66 50 L64 53 L52 53 Z" fill="#a7f3d0" opacity="0.9" />
      </g>

      {/* quay */}
      <path d="M8 78 L88 78 L84 84 L12 84 Z" fill={STEEL_DEEP} opacity="0.7" />
    </svg>
  )
}
