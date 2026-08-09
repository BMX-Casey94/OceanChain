"use client"

import { useRef } from "react"
import Link from "next/link"
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion"
import { ArrowRight, ChevronDown } from "lucide-react"
import { Particles } from "./particles"
import { ContainerShipIcon } from "./icons/marine"
import { getEnterpriseMailto } from "@/lib/site"

export function Hero() {
  const reduceMotion = useReducedMotion()
  const sectionRef = useRef<HTMLElement>(null)
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  })

  const bgY = useTransform(scrollYProgress, [0, 1], ["0%", "20%"])
  const bgScale = useTransform(scrollYProgress, [0, 1], [1.06, 1.15])
  const glowY = useTransform(scrollYProgress, [0, 1], ["0%", "38%"])
  const contentY = useTransform(scrollYProgress, [0, 1], ["0%", "-16%"])
  const contentOpacity = useTransform(scrollYProgress, [0, 0.72], [1, 0])
  const gridY = useTransform(scrollYProgress, [0, 1], ["0%", "-26%"])
  const shipY = useTransform(scrollYProgress, [0, 1], ["0%", "-46%"])

  const motionStyle = (style: Record<string, unknown>) =>
    reduceMotion ? undefined : style

  return (
    <section
      ref={sectionRef}
      className="relative min-h-[100svh] flex flex-col items-center justify-center px-4 overflow-hidden"
    >
      <motion.div
        className="absolute inset-[-8%] pointer-events-none hero-ocean-bg"
        style={motionStyle({ y: bgY, scale: bgScale })}
        aria-hidden="true"
      />

      {/* Anchored to the section so the darkening never drifts with the photo. */}
      <div className="absolute inset-0 pointer-events-none hero-scrim" aria-hidden="true" />

      <motion.div
        className="absolute inset-0 pointer-events-none"
        style={motionStyle({ y: glowY })}
        aria-hidden="true"
      >
        <div className="absolute inset-0 hero-glow" />
      </motion.div>

      <motion.div
        className="absolute inset-x-0 bottom-0 h-2/3 pointer-events-none hero-horizon"
        style={motionStyle({ y: gridY })}
        aria-hidden="true"
      />

      <Particles />

      <motion.div
        className="relative z-10 text-center max-w-5xl mx-auto pt-24 pb-16"
        style={motionStyle({ y: contentY, opacity: contentOpacity })}
      >
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.9, ease: [0.22, 0.61, 0.36, 1] }}
          className="flex justify-center mb-6"
          style={motionStyle({ y: shipY })}
        >
          <ContainerShipIcon size={92} className="drop-shadow-[0_10px_30px_rgba(13,148,136,0.35)]" />
        </motion.div>

        <motion.p
          initial={reduceMotion ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.05 }}
          className="eyebrow mb-6"
        >
          Maritime intelligence · Recorded on Bitcoin
        </motion.p>

        <motion.h1
          initial={reduceMotion ? false : { opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.1, ease: [0.22, 0.61, 0.36, 1] }}
          className="font-display text-white text-6xl sm:text-7xl md:text-8xl leading-[0.92]"
        >
          Every vessel,
          <span className="block mt-1">
            <em className="italic text-teal-300 text-glow-soft">permanently</em> on record
          </span>
        </motion.h1>

        <motion.p
          initial={reduceMotion ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="mt-7 text-base md:text-lg text-white/72 font-sans max-w-2xl mx-auto leading-relaxed"
        >
          Ocechain writes global AIS vessel positions to Bitcoin — an immutable, publicly
          verifiable evidence layer for insurers, logistics, compliance teams, and operators
          who need to know where a ship was, and prove it.
        </motion.p>

        <motion.div
          initial={reduceMotion ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.28 }}
          className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4"
        >
          <Link href="/live" className="btn-neon inline-flex items-center gap-2">
            Search the live fleet
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
          <a href="#how-it-works" className="btn-outline-neon">
            How it works
          </a>
          <a
            href={getEnterpriseMailto("Ocechain insurance & enterprise enquiry")}
            className="text-sm text-white/60 hover:text-teal-300 transition-colors"
          >
            Talk to enterprise
          </a>
        </motion.div>

        <motion.div
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.45 }}
          className="mt-14 flex justify-center"
        >
          <a
            href="#presence"
            className="text-teal-300/80 hover:text-teal-300 transition-colors"
            aria-label="Scroll to live presence"
          >
            <ChevronDown className="scroll-indicator" size={28} aria-hidden="true" />
          </a>
        </motion.div>
      </motion.div>
    </section>
  )
}
