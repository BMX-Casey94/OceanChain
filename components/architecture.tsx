"use client"

import { Wifi, Cpu, Layers, Send, Database } from "lucide-react"

const flowSteps = [
  {
    icon: Wifi,
    name: "AISstream WebSocket",
    description: "Global vessel positions streamed in real time",
  },
  {
    icon: Cpu,
    name: "Python Engine (VPS)",
    description: "Asyncio-based broadcaster with UTXO pool management",
  },
  {
    icon: Layers,
    name: "UTXO Fan-out Pool",
    description: "Pre-warmed outputs maintained in PostgreSQL for throughput",
  },
  {
    icon: Send,
    name: "GorillaPool ARC",
    description: "Primary broadcaster via ARC protocol with TAAL fallback",
  },
  {
    icon: Database,
    name: "BSV Blockchain",
    description: "Permanent, mined OP_RETURN records, publicly verifiable",
  },
]

const payloadSpec = `OP_RETURN <OCEANCHAIN>

[bytes 0–3  ]  MMSI         uint32  vessel identifier
[bytes 4–7  ]  Latitude     int32   degrees × 600,000
[bytes 8–11 ]  Longitude    int32   degrees × 600,000
[bytes 12–13]  Speed        uint16  knots × 10
[bytes 14–15]  Heading      uint16  degrees (0xFFFF = N/A)
[bytes 16–19]  Timestamp    uint32  unix seconds
─────────────────────────────────────────────────────
Total: 20 bytes payload
Fee:   ~220 byte TX × 102.5 sat/KB ≈ 22 sat/TX
Cost:  ~$0.0000032 USD per vessel position`

export function Architecture() {
  return (
    <section id="architecture" className="py-24 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Section Header */}
        <div className="mb-16">
          <h2 className="font-heading text-5xl md:text-6xl text-white">
            Architecture Deep Dive
          </h2>
          <p className="mt-4 text-muted-foreground font-sans text-lg">
            From ocean to blockchain in milliseconds.
          </p>
        </div>

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
          {/* Left Column - Flow Diagram */}
          <div className="flex flex-col">
            {flowSteps.map((step, index) => (
              <div key={step.name}>
                {/* Step Card */}
                <div className="inner-panel border-l-2 border-teal-500 p-4 flex items-start gap-4">
                  <div className="p-2 rounded-lg bg-teal-500/10">
                    <step.icon className="text-teal-400" size={20} aria-hidden="true" />
                  </div>
                  <div>
                    <h4 className="font-sans font-semibold text-white text-sm">
                      {step.name}
                    </h4>
                    <p className="text-xs text-muted-foreground mt-1">
                      {step.description}
                    </p>
                  </div>
                </div>
                
                {/* Connector Line */}
                {index < flowSteps.length - 1 && (
                  <div className="flex justify-center">
                    <div 
                      className="w-0.5 h-8 border-l-2 border-dashed border-teal-500/50"
                      aria-hidden="true"
                    />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Right Column - Payload Spec Block */}
          <div className="glass-card p-6">
            {/* Header */}
            <div className="mb-4">
              <span className="text-sm text-muted-foreground font-sans">
                OP_RETURN Payload Structure
              </span>
            </div>

            {/* Code Block */}
            <div className="inner-panel p-6 font-mono text-sm leading-relaxed overflow-x-auto">
              <pre className="text-white whitespace-pre">
                <code>
                  {payloadSpec.split('\n').map((line, i) => {
                    // Highlight byte ranges in teal
                    if (line.includes('[bytes')) {
                      const parts = line.split(']')
                      return (
                        <span key={i} className="block">
                          <span className="text-teal-400">{parts[0]}]</span>
                          <span className="text-white">{parts.slice(1).join(']')}</span>
                        </span>
                      )
                    }
                    // Comments/metadata in muted
                    if (line.startsWith('Total:') || line.startsWith('Fee:') || line.startsWith('Cost:') || line.includes('───')) {
                      return <span key={i} className="block text-muted-foreground">{line}</span>
                    }
                    return <span key={i} className="block">{line}</span>
                  })}
                </code>
              </pre>
            </div>

            {/* Stat Pills */}
            <div className="inner-panel mt-6 p-4 flex flex-wrap items-center justify-center gap-8">
              <div className="text-center">
                <span className="font-heading text-2xl text-teal-400">22 sat</span>
                <span className="block text-xs text-muted-foreground mt-1">Average TX Fee</span>
              </div>
              <div className="text-center">
                <span className="font-heading text-2xl text-teal-400">20 bytes</span>
                <span className="block text-xs text-muted-foreground mt-1">Payload Size</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
