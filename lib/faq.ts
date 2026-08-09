export type FaqItem = {
  question: string
  answer: string
}

/** Canonical FAQ copy — shared by the FAQ page and JSON-LD. */
export const FAQ_ITEMS: FaqItem[] = [
  {
    question: "What is Ocechain?",
    answer:
      "Ocechain is a maritime intelligence system that ingests live AIS vessel positions and permanently records them on Bitcoin, creating a publicly verifiable evidence layer for shipping activity.",
  },
  {
    question: "How does Ocechain help marine insurance?",
    answer:
      "Insurers and claims teams can use timestamped, tamper-evident vessel positions to reconstruct voyages, verify incident locations, and reduce disputes over where a ship was at a given time.",
  },
  {
    question: "Can I search for a ship or a location?",
    answer:
      "Yes. On the live map you can search by vessel name, MMSI, call sign, port, place name, or pasted coordinates. Selecting a result flies the map to that ship or region.",
  },
  {
    question: "Where are positions recorded?",
    answer:
      "Vessel positions are written into Bitcoin transactions using a compact payload. The on-chain protocol prefix is Ocechain. Records can be inspected in a public explorer.",
  },
  {
    question: "Is Ocechain a navigational aid?",
    answer:
      "No. Ocechain must not be used for collision avoidance, voyage planning, or navigation. It is an intelligence and evidence layer based on public AIS data.",
  },
  {
    question: "What data source do you use?",
    answer:
      "Live AIS ingestion is provided via AISstream. Availability and coverage depend on that upstream feed and the Ocechain broadcast engine.",
  },
  {
    question: "Who is Ocechain for?",
    answer:
      "Marine insurers, underwriters, shipowners and operators, P&I clubs, ports and logistics teams, compliance reviewers, maritime counsel, researchers, and journalists who need verifiable movement evidence.",
  },
]
