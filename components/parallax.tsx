"use client"

import { useRef, type CSSProperties, type ReactNode } from "react"
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion"

type RevealProps = {
  children: ReactNode
  className?: string
  delay?: number
  y?: number
}

/** Scroll-triggered entrance, fires once per element. */
export function Reveal({ children, className, delay = 0, y = 28 }: RevealProps) {
  const reduceMotion = useReducedMotion()

  return (
    <motion.div
      className={className}
      initial={reduceMotion ? false : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{ duration: 0.75, delay, ease: [0.22, 0.61, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}

/** Slow counter-drift backdrop used behind marketing sections. */
export function ParallaxBackdrop({
  className = "",
  distance = 120,
  style,
}: {
  className?: string
  distance?: number
  style?: CSSProperties
}) {
  const ref = useRef<HTMLDivElement>(null)
  const reduceMotion = useReducedMotion()
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  })
  const y = useTransform(scrollYProgress, [0, 1], [-distance / 2, distance / 2])

  return (
    <div
      ref={ref}
      className={`absolute inset-0 pointer-events-none overflow-hidden ${className}`}
      aria-hidden="true"
    >
      <motion.div
        className="absolute inset-[-15%]"
        style={reduceMotion ? style : { ...style, y }}
      />
    </div>
  )
}
