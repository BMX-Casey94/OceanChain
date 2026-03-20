"use client"

import { useEffect, useState, useRef } from "react"
import { useInView } from "framer-motion"

const statsData = [
  { value: 300000, suffix: "+", label: "Vessels Per Snapshot" },
  { value: 1000000, suffix: "+", label: "Daily Transactions" },
  { value: 20, suffix: "", label: "Bytes Per Record" },
  { value: 22, suffix: "", label: "Sat Per TX" },
  { value: 30, suffix: "", label: "Min Snapshot Interval" },
  { value: null, display: "∞", label: "Record Permanence" },
]

function AnimatedNumber({ 
  value, 
  suffix = "", 
  display,
  inView 
}: { 
  value: number | null
  suffix?: string
  display?: string
  inView: boolean
}) {
  const [count, setCount] = useState(0)
  const hasAnimated = useRef(false)

  useEffect(() => {
    if (!inView || hasAnimated.current || value === null) return
    
    hasAnimated.current = true
    const duration = 2000
    const steps = 60
    const increment = value / steps
    let current = 0
    
    const timer = setInterval(() => {
      current += increment
      if (current >= value) {
        setCount(value)
        clearInterval(timer)
      } else {
        setCount(Math.floor(current))
      }
    }, duration / steps)

    return () => clearInterval(timer)
  }, [inView, value])

  if (display) {
    return <span>{display}</span>
  }

  return (
    <span>
      {count.toLocaleString()}{suffix}
    </span>
  )
}

export function Stats() {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref, { once: true, amount: 0.3 })

  return (
    <section 
      className="py-24 px-4 border-y border-white/5"
      style={{ background: "rgba(0,0,0,0.3)" }}
    >
      <div className="max-w-6xl mx-auto">
        {/* Section Header */}
        <div className="text-center mb-16">
          <h2 className="font-heading text-5xl text-white">
            Scale That Means Something
          </h2>
        </div>

        {/* Stats Grid */}
        <div 
          ref={ref}
          className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-8"
        >
          {statsData.map((stat) => (
            <div key={stat.label} className="text-center">
              <div 
                className="font-heading text-4xl md:text-5xl text-teal-400"
                style={{
                  textShadow: "0 0 30px rgba(20,184,166,0.5)"
                }}
              >
                <AnimatedNumber 
                  value={stat.value} 
                  suffix={stat.suffix}
                  display={stat.display}
                  inView={isInView}
                />
              </div>
              <div className="text-xs text-muted-foreground font-sans mt-2">
                {stat.label}
              </div>
            </div>
          ))}
        </div>

        {/* Footnote */}
        <p className="text-center text-sm text-muted-foreground font-sans mt-12 max-w-2xl mx-auto">
          All figures represent steady-state operation. Blockchain records are permanent and independently verifiable on any BSV block explorer.
        </p>
      </div>
    </section>
  )
}
