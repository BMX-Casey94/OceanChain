"use client"

import { useEffect, useState } from "react"
import { Wifi, Cpu, Layers, Send, Database } from "lucide-react"
import { motion, useReducedMotion } from "framer-motion"
import { ParallaxBackdrop, Reveal } from "@/components/parallax"

const flowSteps = [
  {
    icon: Wifi,
    name: "AIS stream",
    description: "Global vessel positions ingested in real time",
  },
  {
    icon: Cpu,
    name: "Ocechain engine",
    description: "Live snapshot, encoding, and broadcast orchestration",
  },
  {
    icon: Layers,
    name: "UTXO throughput pool",
    description: "Pre-warmed outputs for high-volume recording",
  },
  {
    icon: Send,
    name: "Network submission",
    description: "Primary broadcaster with automatic fallback path",
  },
  {
    icon: Database,
    name: "Bitcoin ledger",
    description: "Permanent, publicly verifiable position records",
  },
]

const payloadFields = [
  { bytes: "0–3", end: 4, name: "MMSI", type: "uint32", note: "vessel identifier" },
  { bytes: "4–7", end: 8, name: "Latitude", type: "int32", note: "degrees × 600,000" },
  { bytes: "8–11", end: 12, name: "Longitude", type: "int32", note: "degrees × 600,000" },
  { bytes: "12–13", end: 14, name: "Speed", type: "uint16", note: "knots × 10" },
  { bytes: "14–15", end: 16, name: "Heading", type: "uint16", note: "degrees (0xFFFF = N/A)" },
  { bytes: "16–19", end: 20, name: "Timestamp", type: "uint32", note: "unix seconds" },
] as const

const TOTAL_BYTES = 20
const HEADER = "OP_RETURN <Ocechain>"

function PayloadPanel() {
  const reduceMotion = useReducedMotion()
  const [inView, setInView] = useState(false)
  const [typedHeader, setTypedHeader] = useState("")
  const [visibleFields, setVisibleFields] = useState(0)
  const [showFooter, setShowFooter] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [done, setDone] = useState(false)

  const assembledBytes =
    visibleFields > 0 ? payloadFields[Math.min(visibleFields, payloadFields.length) - 1]?.end ?? 0 : 0

  useEffect(() => {
    if (!inView) return

    if (reduceMotion) {
      setTypedHeader(HEADER)
      setVisibleFields(payloadFields.length)
      setShowFooter(true)
      setActiveIndex(-1)
      setDone(true)
      return
    }

    let cancelled = false
    const timers: number[] = []
    const wait = (ms: number) =>
      new Promise<void>((resolve) => {
        const id = window.setTimeout(() => resolve(), ms)
        timers.push(id)
      })

    const run = async () => {
      setTypedHeader("")
      setVisibleFields(0)
      setShowFooter(false)
      setActiveIndex(-1)
      setDone(false)

      for (let i = 1; i <= HEADER.length; i++) {
        if (cancelled) return
        setTypedHeader(HEADER.slice(0, i))
        await wait(i < 10 ? 28 : 18)
      }

      await wait(220)

      for (let i = 0; i < payloadFields.length; i++) {
        if (cancelled) return
        setActiveIndex(i)
        setVisibleFields(i + 1)
        await wait(320)
      }

      if (cancelled) return
      setActiveIndex(-1)
      setShowFooter(true)
      await wait(180)
      setDone(true)
    }

    void run()
    return () => {
      cancelled = true
      timers.forEach((id) => window.clearTimeout(id))
    }
  }, [inView, reduceMotion])

  return (
    <motion.div
      className="glass-card p-6"
      initial={reduceMotion ? false : { opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.35 }}
      transition={{ duration: 0.75, delay: 0.12, ease: [0.22, 0.61, 0.36, 1] }}
      onViewportEnter={() => setInView(true)}
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <span className="text-sm text-muted-foreground font-sans">
            On-chain payload structure
          </span>
          <p className="mt-2 text-xs text-muted-foreground/90 font-sans leading-relaxed">
            Protocol prefix is <span className="text-teal-300/90 font-mono">Ocechain</span>.
            Anyone can verify records in a public explorer.
          </p>
        </div>
        <div
          className="shrink-0 font-mono text-[10px] uppercase tracking-[0.16em] text-teal-300/80 pt-0.5"
          aria-live="polite"
        >
          {done ? "committed" : inView ? "decoding" : "standby"}
          <span
            className={`ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-teal-300 align-middle ${
              done || reduceMotion ? "" : "payload-status-dot"
            }`}
            aria-hidden="true"
          />
        </div>
      </div>

      <div className="inner-panel relative overflow-hidden p-5 font-mono text-xs sm:text-sm leading-relaxed">
        {/* Soft scan sweep while decoding */}
        {!reduceMotion && inView && !done && (
          <motion.div
            className="pointer-events-none absolute inset-x-0 h-10 bg-gradient-to-b from-teal-300/10 via-teal-300/5 to-transparent"
            initial={{ top: "-10%" }}
            animate={{ top: ["-10%", "110%"] }}
            transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }}
            aria-hidden="true"
          />
        )}

        <p className="sr-only">
          {HEADER}. Fields:{" "}
          {payloadFields
            .map(
              (field) =>
                `bytes ${field.bytes} ${field.name} ${field.type} ${field.note}`
            )
            .join("; ")}
          . Total: {TOTAL_BYTES} bytes on the second push, compact binary mode. Network fee
          scales with signed transaction size.
        </p>

        <pre
          className="relative text-white whitespace-pre overflow-x-auto min-h-[14.5rem]"
          aria-hidden="true"
        >
          <code>
            <span className="block min-h-[1.35em]">
              <span className="text-white">{typedHeader}</span>
              {!reduceMotion && !done && typedHeader.length < HEADER.length && (
                <span className="payload-caret" />
              )}
            </span>

            <span className="block h-4" />

            {payloadFields.slice(0, visibleFields).map((field, i) => {
              const active = i === activeIndex
              return (
                <motion.span
                  key={field.name}
                  className={`block rounded-sm px-1 -mx-1 ${
                    active ? "bg-teal-400/10" : ""
                  }`}
                  initial={reduceMotion ? false : { opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, ease: [0.22, 0.61, 0.36, 1] }}
                >
                  <span className="text-teal-300">
                    [bytes {field.bytes.padEnd(5, " ")}]
                  </span>
                  <span className="text-white">
                    {"  "}
                    {field.name.padEnd(12, " ")}
                    {field.type.padEnd(8, " ")}
                    {field.note}
                  </span>
                  {active && !reduceMotion && <span className="payload-caret ml-1" />}
                </motion.span>
              )
            })}

            {showFooter && (
              <motion.span
                className="block"
                initial={reduceMotion ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.35 }}
              >
                <span className="block text-muted-foreground mt-1">
                  ─────────────────────────────────────────────────────
                </span>
                <span className="block text-muted-foreground">
                  Total: {TOTAL_BYTES} bytes on the second push (compact binary mode)
                </span>
                <span className="block text-muted-foreground">
                  Network fee: scales with signed transaction size
                </span>
              </motion.span>
            )}
          </code>
        </pre>

        {/* Byte assemble meter */}
        <div className="mt-4 pt-3 border-t border-white/8">
          <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-[0.14em] text-white/40 mb-2">
            <span>Payload fill</span>
            <span className="text-teal-300/80 tabular-nums">
              {assembledBytes.toString().padStart(2, "0")} / {TOTAL_BYTES} bytes
            </span>
          </div>
          <div className="h-1 rounded-full bg-white/8 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-teal-600 to-teal-300"
              initial={false}
              animate={{ width: `${(assembledBytes / TOTAL_BYTES) * 100}%` }}
              transition={{ duration: 0.35, ease: [0.22, 0.61, 0.36, 1] }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  )
}

export function Architecture() {
  return (
    <section id="architecture" className="relative py-28 px-4 scroll-mt-24 overflow-hidden">
      <ParallaxBackdrop className="section-veil opacity-60" distance={150} />

      <div className="max-w-6xl mx-auto relative">
        <Reveal className="mb-16 max-w-2xl">
          <p className="eyebrow mb-4">Under the hull</p>
          <h2 className="font-display text-5xl md:text-6xl text-white leading-[1.02]">
            Architecture
          </h2>
          <div className="rule-hairline mt-6 mb-6 w-40" />
          <p className="text-white/65 font-sans text-lg">
            From ocean signal to Bitcoin permanence — engineered for scale.
          </p>
        </Reveal>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
          <div className="flex flex-col">
            {flowSteps.map((step, index) => (
              <Reveal key={step.name} delay={index * 0.06}>
                <div className="border-l border-teal-400/40 pl-5 py-3 flex items-start gap-4">
                  <div className="p-2 rounded-lg bg-teal-500/10 border border-teal-400/15">
                    <step.icon className="text-teal-300" size={18} aria-hidden="true" />
                  </div>
                  <div>
                    <h3 className="font-sans font-semibold text-white text-sm">
                      {step.name}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">{step.description}</p>
                  </div>
                </div>
                {index < flowSteps.length - 1 && (
                  <div className="ml-[1px] h-4 border-l border-dashed border-teal-500/30" aria-hidden="true" />
                )}
              </Reveal>
            ))}
          </div>

          <PayloadPanel />
        </div>
      </div>
    </section>
  )
}
