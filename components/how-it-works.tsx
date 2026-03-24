"use client"

import { Radio, Binary, ShieldCheck } from "lucide-react"

const steps = [
  {
    number: "01",
    icon: Radio,
    title: "AIS Ingestion",
    description: "AISstream.io streams real-time vessel positions via WebSocket from 300,000+ active ships globally. Our engine maintains a live snapshot, updated continuously, capturing MMSI, coordinates, speed, and heading.",
  },
  {
    number: "02",
    icon: Binary,
    title: "TX Construction",
    description: "Each vessel position is encoded into a compact 20-byte payload and embedded in a BSV OP_RETURN output. The fee is ceil(tx size / 1000 × your sat/KB rate); the builder measures the signed transaction so the fee matches the real payload and scripts, not a rough estimate.",
  },
  {
    number: "03",
    icon: ShieldCheck,
    title: "Broadcast & Mine",
    description: "Transactions are submitted to GorillaPool Arcade with automatic TAAL fallback. Once mined, the position record is permanently written to the BSV blockchain — immutable, tamper-proof, and publicly verifiable by anyone.",
  },
]

export function HowItWorks() {
  return (
    <section id="how-it-works" className="py-24 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Section Header */}
        <div className="text-center mb-16">
          <h2 className="font-heading text-5xl md:text-6xl text-white">
            How It Works
          </h2>
          <p className="mt-4 text-muted-foreground font-sans text-lg">
            Three steps. Millions of records. Zero trust required.
          </p>
        </div>

        {/* Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {steps.map((step) => (
            <div
              key={step.number}
              className="glass-card card-hover relative overflow-hidden p-8"
            >
              {/* Background Step Number */}
              <span 
                className="font-heading text-7xl text-white/[0.06] absolute top-4 right-6 select-none pointer-events-none"
                aria-hidden="true"
              >
                {step.number}
              </span>

              {/* Icon */}
              <div className="inner-panel rounded-lg p-2 w-fit mb-6">
                <step.icon className="text-teal-400" size={28} aria-hidden="true" />
              </div>

              {/* Title */}
              <h3 className="font-heading text-2xl text-white mb-4">
                {step.title}
              </h3>

              {/* Description */}
              <p className="text-sm text-muted-foreground font-sans leading-relaxed">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
