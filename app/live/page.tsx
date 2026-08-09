import type { Metadata } from "next"
import { Suspense } from "react"
import { LiveApp } from "@/components/live/live-app"
import { SITE_NAME } from "@/lib/site"

export const metadata: Metadata = {
  title: "Live fleet",
  description:
    "Search ships and locations on the Ocechain live map. Inspect vessel positions and Bitcoin-recorded evidence in real time.",
  alternates: { canonical: "/live" },
  openGraph: {
    title: `Live fleet | ${SITE_NAME}`,
    description:
      "Search vessels by name or MMSI, fly to ports and coordinates, and open Bitcoin-verifiable position records.",
    url: "/live",
  },
  twitter: {
    card: "summary_large_image",
    title: `Live fleet | ${SITE_NAME}`,
    description:
      "Search vessels by name or MMSI, fly to ports and coordinates, and open Bitcoin-verifiable position records.",
  },
}

export default function LivePage() {
  return (
    <main id="main-content" className="min-h-svh">
      <div className="sr-only">
        <h1>Ocechain live fleet map</h1>
        <p>
          Search for ships by name, MMSI, or call sign, and search locations by port, place, or
          coordinates. Select a vessel to view details and Bitcoin transaction evidence.
        </p>
      </div>
      <Suspense
        fallback={
          <div className="live-shell flex items-center justify-center text-white/70">
            Loading live map…
          </div>
        }
      >
        <LiveApp />
      </Suspense>
    </main>
  )
}
