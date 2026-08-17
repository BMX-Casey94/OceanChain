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
  | "military"
  | "dredger"
  | "pilot"
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
  military: "Military",
  dredger: "Dredger",
  pilot: "Pilot / workboat",
  special: "Special craft",
  unknown: "Vessel",
}

export type ClassifyInput = {
  shipType?: number | null
  name?: string | null
  lengthM?: number | null
  beamM?: number | null
}

function nameHaystack(name?: string | null): string {
  return (name || "").toUpperCase().replace(/[^A-Z0-9 ]+/g, " ")
}

function fromName(name?: string | null): ShipKind | null {
  const n = nameHaystack(name)
  if (!n.trim()) return null
  if (/\b(NARROWBOAT|NARROW BOAT|CANAL|PENICHE|BARGE)\b/.test(n)) return "canal"
  if (/\b(CRUISE|CRUISER|LINER)\b/.test(n)) return "cruise"
  if (/\b(FERRY|FERRIES|ROPAX|RO PAX|RO-RO)\b/.test(n)) return "ferry"
  if (/\b(TANKER|VLCC|ULCC|AFRAMAX|SUEZMAX)\b/.test(n)) return "tanker"
  if (/\b(CONTAINER|CARGO|FREIGHTER|BULKER|BULK)\b/.test(n)) return "cargo"
  if (/\b(TUG|TOWING)\b/.test(n)) return "tug"
  if (/\b(DREDG)\b/.test(n)) return "dredger"
  if (/\b(HMS |USS |FS |HMAS |BNS )\b/.test(n)) return "military"
  if (/\b(YACHT|RIB|LIFEBOAT)\b/.test(n)) return "pleasure"
  if (/\b(PILOT)\b/.test(n)) return "pilot"
  if (/\b(SAIL|YAWL|KETCH|SLOOP)\b/.test(n)) return "sailing"
  if (/\b(FISH|TRAWLER|LONGLINER)\b/.test(n)) return "fishing"
  return null
}

function fromAisType(shipType: number): ShipKind {
  if (shipType === 30) return "fishing"
  if (shipType === 33) return "dredger"
  if (shipType === 35) return "military"
  if (shipType === 36) return "sailing"
  if (shipType === 37) return "pleasure"
  if (shipType === 31 || shipType === 32 || shipType === 52) return "tug"
  if (shipType === 50 || shipType === 53) return "pilot"
  if (shipType >= 40 && shipType <= 49) return "hsc"
  if (shipType >= 50 && shipType <= 59) return "special"
  if (shipType >= 60 && shipType <= 69) return "passenger"
  if (shipType >= 70 && shipType <= 79) return "cargo"
  if (shipType >= 80 && shipType <= 89) return "tanker"
  return "unknown"
}

function refinePassenger(kind: ShipKind, lengthM: number | null, named: ShipKind | null): ShipKind {
  if (kind !== "passenger") return kind
  if (named === "cruise" || named === "ferry") return named
  if (lengthM != null) {
    if (lengthM >= 220) return "cruise"
    if (lengthM <= 170) return "ferry"
  }
  return "passenger"
}

function refineByHull(kind: ShipKind, lengthM: number | null, beamM: number | null): ShipKind {
  if (lengthM == null) return kind
  if (kind === "cargo" && lengthM <= 55 && (beamM == null || beamM <= 12)) {
    return "canal"
  }
  if (kind === "unknown" && lengthM >= 80 && lengthM <= 140 && beamM != null && beamM <= 16) {
    return "canal"
  }
  if (kind === "pleasure" && lengthM >= 100) {
    return "passenger"
  }
  return kind
}

/**
 * Classify a vessel for silhouette + label.
 * AIS Type is primary; hull length and name refine cruise vs ferry vs barge.
 */
export function classifyShip(
  shipTypeOrInput?: number | null | ClassifyInput,
  name?: string | null
): { kind: ShipKind; label: string; aisType: number | null } {
  const input: ClassifyInput =
    shipTypeOrInput != null && typeof shipTypeOrInput === "object"
      ? shipTypeOrInput
      : { shipType: shipTypeOrInput as number | null | undefined, name }

  const aisType =
    input.shipType != null && Number.isFinite(input.shipType)
      ? Math.trunc(input.shipType)
      : null
  const lengthM =
    input.lengthM != null && Number.isFinite(input.lengthM) ? input.lengthM : null
  const beamM =
    input.beamM != null && Number.isFinite(input.beamM) ? input.beamM : null
  const named = fromName(input.name)
  let kind: ShipKind = "unknown"

  if (aisType != null) {
    kind = fromAisType(aisType)
    kind = refinePassenger(kind, lengthM, named)
    if (kind === "unknown" && named) kind = named
    if (kind === "cargo" && named === "canal") kind = "canal"
  } else if (named) {
    kind = named
  }

  kind = refineByHull(kind, lengthM, beamM)
  return { kind, label: LABELS[kind], aisType }
}
