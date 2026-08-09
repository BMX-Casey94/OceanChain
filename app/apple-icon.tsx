import { ImageResponse } from "next/og"

export const runtime = "edge"
export const size = { width: 180, height: 180 }
export const contentType = "image/png"

/** Apple touch icon — beacon mark on Ocechain night-ocean ground. */
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#020b12",
          borderRadius: 40,
          position: "relative",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 96,
            height: 96,
            borderRadius: 999,
            border: "8px solid #2dd4bf",
            marginBottom: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 54,
              height: 54,
              borderRadius: 999,
              border: "5px solid rgba(94, 234, 212, 0.45)",
            }}
          >
            <div
              style={{
                width: 22,
                height: 22,
                borderRadius: 999,
                background: "#5eead4",
              }}
            />
          </div>
        </div>
        <div
          style={{
            width: 120,
            height: 14,
            borderBottom: "7px solid #5eead4",
            borderRadius: "0 0 120px 120px",
            opacity: 0.9,
            marginTop: -4,
          }}
        />
      </div>
    ),
    { ...size }
  )
}
