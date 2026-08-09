import { ImageResponse } from "next/og"

export const runtime = "edge"
export const alt = "Ocechain — maritime intelligence on Bitcoin"
export const size = { width: 1200, height: 630 }
export const contentType = "image/png"

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background:
            "linear-gradient(145deg, #020b12 0%, #031820 45%, #000000 100%)",
          color: "white",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(circle at 30% 40%, rgba(45,212,191,0.22), transparent 45%)",
          }}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div
            style={{
              fontSize: 64,
              letterSpacing: 10,
              fontWeight: 700,
            }}
          >
            <span style={{ color: "#5eead4" }}>OCE</span>
            <span>CHAIN</span>
          </div>
          <div style={{ fontSize: 28, color: "rgba(255,255,255,0.62)" }}>
            Maritime intelligence on Bitcoin
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ fontSize: 44, fontWeight: 600, maxWidth: 900, lineHeight: 1.15 }}>
            Every vessel. Permanent evidence.
          </div>
          <div style={{ fontSize: 24, color: "rgba(255,255,255,0.58)", maxWidth: 820 }}>
            Live AIS positions recorded on Bitcoin for insurers, logistics, and operators.
          </div>
        </div>
      </div>
    ),
    { ...size }
  )
}
