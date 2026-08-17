export type ShipKind =
  | "cruise"
  | "ferry"
  | "passenger"
  | "cargo"
  | "tanker"
  | "fishing"
  | "sailing"
  | "pleasure"
  | "canal"
  | "tug"
  | "hsc"
  | "special"
  | "unknown"

const LABELS: Record<ShipKind, string> = {
  cruise: "Cruise liner",
  ferry: "Ferry",
  passenger: "Passenger",
  cargo: "Cargo / shipping",
  tanker: "Tanker",
  fishing: "Fishing",
  sailing: "Sailing",
  pleasure: "Small boat",
  canal: "Canal / barge",
  tug: "Tug",
  hsc: "High-speed craft",
  special: "Special craft",
  unknown: "Vessel",
}

function nameHaystack(name?: string | null): string {
  return (name || "").toUpperCase().replace(/[^A-Z0-9 ]+/g, " ")
}

function fromName(name?: string | null): ShipKind | null {
  const n = nameHaystack(name)
  if (!n.trim()) return null
  if (/\b(NARROWBOAT|NARROW BOAT|CANAL|PENICHE|BARGE)\b/.test(n)) return "canal"
  if (/\b(CRUISE|CRUISER|LINER)\b/.test(n)) return "cruise"
  if (/\b(FERRY|FERRIES)\b/.test(n)) return "ferry"
  if (/\b(TANKER|VLCC|ULCC)\b/.test(n)) return "tanker"
  if (/\b(CONTAINER|CARGO|FREIGHTER|BULKER|BULK)\b/.test(n)) return "cargo"
  if (/\b(TUG|TOWING)\b/.test(n)) return "tug"
  if (/\b(YACHT|RIB|PILOT BOAT|LIFEBOAT)\b/.test(n)) return "pleasure"
  if (/\b(SAIL|YAWL|KETCH|SLOOP)\b/.test(n)) return "sailing"
  if (/\b(FISH|TRAWLER|LONGLINER)\b/.test(n)) return "fishing"
  return null
}

function fromAisType(shipType: number): ShipKind {
  if (shipType === 30) return "fishing"
  if (shipType === 36) return "sailing"
  if (shipType === 37) return "pleasure"
  if (shipType === 31 || shipType === 32 || shipType === 52) return "tug"
  if (shipType >= 40 && shipType <= 49) return "hsc"
  if (shipType >= 50 && shipType <= 59) return "special"
  if (shipType >= 60 && shipType <= 69) return "passenger"
  if (shipType >= 70 && shipType <= 79) return "cargo"
  if (shipType >= 80 && shipType <= 89) return "tanker"
  return "unknown"
}

/**
 * Classify a vessel for silhouette + label.
 * AIS Type (ITU-R M.1371) is primary; name keywords refine passenger / inland craft.
 */
export function classifyShip(
  shipType: number | null | undefined,
  name?: string | null
): { kind: ShipKind; label: string; aisType: number | null } {
  const aisType =
    shipType != null && Number.isFinite(shipType) ? Math.trunc(shipType) : null
  const named = fromName(name)
  let kind: ShipKind = "unknown"

  if (aisType != null) {
    kind = fromAisType(aisType)
    if (kind === "passenger" && (named === "cruise" || named === "ferry")) {
      kind = named
    }
    if (kind === "unknown" && named) {
      kind = named
    }
    if (kind === "cargo" && named === "canal") {
      kind = "canal"
    }
  } else if (named) {
    kind = named
  }

  return { kind, label: LABELS[kind], aisType }
}
