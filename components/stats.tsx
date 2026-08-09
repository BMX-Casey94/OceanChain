"use client"

import { useEffect, useState } from "react"
import { fetchStatsSummary, getApiBase } from "@/lib/api"
import { Reveal } from "@/components/parallax"

type DisplayStat = {
  label: string
  value: string
}

const fallbackStats: DisplayStat[] = [
  { label: "Compact payload", value: "20 B" },
  { label: "Typical fee", value: "~22 sat" },
  { label: "Record permanence", value: "∞" },
  { label: "Public verification", value: "Open" },
]

export function Stats() {
  const [stats, setStats] = useState<DisplayStat[]>(fallbackStats)
  const [live, setLive] = useState(false)

  useEffect(() => {
    if (!getApiBase()) return
    let cancelled = false

    const load = async () => {
      const summary = await fetchStatsSummary()
      if (cancelled || !summary) return
      setLive(true)
      setStats([
        {
          label: "Active vessels",
          value: summary.active_vessels.toLocaleString("en-GB"),
        },
        {
          label: "Transactions today",
          value: summary.txs_today.toLocaleString("en-GB"),
        },
        {
          label: "Avg fee",
          value: `${summary.avg_fee_sat} sat`,
        },
        {
          label: "Record permanence",
          value: "∞",
        },
      ])
    }

    void load()
    const id = setInterval(() => void load(), 30000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return (
    <section
      id="features"
      aria-labelledby="features-heading"
      className="py-24 px-4 border-y border-white/8 scroll-mt-24 bg-black/25"
    >
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-14">
          <div>
            <p className="eyebrow mb-4">By the numbers</p>
            <h2 id="features-heading" className="font-display text-5xl md:text-6xl text-white leading-[1.02]">
              Scale with substance
            </h2>
          </div>
          <p className="data-label">
            {live ? "Live from the Ocechain engine" : "Indicative operating profile"}
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          {stats.map((stat, i) => (
            <Reveal key={stat.label} delay={i * 0.07}>
              <div className="text-left border-t border-teal-400/20 pt-4">
                <div className="font-display text-5xl md:text-6xl text-teal-300 text-glow-soft">
                  {stat.value}
                </div>
                <div className="data-label mt-3">{stat.label}</div>
              </div>
            </Reveal>
          ))}
        </div>

        <p className="text-sm text-muted-foreground font-sans mt-12 max-w-2xl">
          Records are independently verifiable on a public Bitcoin explorer. Ocechain is not a navigational aid.
        </p>
      </div>
    </section>
  )
}
