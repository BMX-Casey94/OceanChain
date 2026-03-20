"use client"

const vesselData = [
  { name: "MV EVER GIVEN", coords: "31.2°N 32.6°E", speed: "14kn", tx: "a3f8c2d1..." },
  { name: "CMA CGM MARCO POLO", coords: "48.8°N 2.3°W", speed: "18kn", tx: "b7e91a04..." },
  { name: "MSC OSCAR", coords: "1.3°N 103.8°E", speed: "12kn", tx: "f2c44d8b..." },
  { name: "MAERSK EVORA", coords: "55.6°N 12.5°E", speed: "9kn", tx: "09a3e712..." },
  { name: "COSCO SHIPPING", coords: "22.3°N 114.1°E", speed: "16kn", tx: "d5b82f33..." },
  { name: "OOCL HONG KONG", coords: "35.4°N 139.7°E", speed: "20kn", tx: "e8f21c44..." },
  { name: "NYK BLUE JAY", coords: "51.9°N 4.5°E", speed: "11kn", tx: "12ab34cd..." },
  { name: "HAPAG LLOYD EXPRESS", coords: "40.7°N 74.0°W", speed: "15kn", tx: "56ef78gh..." },
]

function VesselEntry({ vessel }: { vessel: typeof vesselData[0] }) {
  return (
    <span className="flex items-center gap-2 whitespace-nowrap">
      <span className="text-teal-400 text-sm">●</span>
      <span className="text-white text-sm font-sans">{vessel.name}</span>
      <span className="text-muted-foreground text-xs font-mono">{vessel.coords}</span>
      <span className="text-muted-foreground text-xs font-mono">{vessel.speed}</span>
      <span className="text-teal-400 text-xs font-mono">tx: {vessel.tx}</span>
    </span>
  )
}

export function Ticker() {
  return (
    <div 
      className="w-full border-y border-white/5 backdrop-blur-sm overflow-hidden py-3"
      style={{ background: "rgba(0,0,0,0.4)" }}
      aria-label="Live vessel tracking ticker"
    >
      <div className="marquee-content flex items-center">
        {/* First set of entries */}
        {vesselData.map((vessel, index) => (
          <div key={`first-${index}`} className="flex items-center">
            <VesselEntry vessel={vessel} />
            <span className="text-teal-400/50 mx-6">|</span>
          </div>
        ))}
        {/* Duplicate for seamless loop */}
        {vesselData.map((vessel, index) => (
          <div key={`second-${index}`} className="flex items-center">
            <VesselEntry vessel={vessel} />
            <span className="text-teal-400/50 mx-6">|</span>
          </div>
        ))}
      </div>
    </div>
  )
}
