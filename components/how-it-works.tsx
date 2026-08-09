"use client"

import { ParallaxBackdrop, Reveal } from "@/components/parallax"
import { ChainBlockIcon, ContainerShipIcon, RadarIcon } from "@/components/icons/marine"

const steps = [
  {
    number: "01",
    Icon: RadarIcon,
    title: "AIS ingestion",
    description:
      "Global AIS streams feed a live vessel snapshot — MMSI, coordinates, speed, heading, and voyage metadata updated continuously as ships move.",
  },
  {
    number: "02",
    Icon: ContainerShipIcon,
    title: "Compact recording",
    description:
      "Each position is encoded into a compact payload and written into a Bitcoin transaction. Small records keep permanence affordable at fleet scale.",
  },
  {
    number: "03",
    Icon: ChainBlockIcon,
    title: "Permanent on Bitcoin",
    description:
      "Once mined, the record is immutable and publicly verifiable. Anyone can inspect the trail — without trusting a single proprietary database.",
  },
]

export function HowItWorks() {
  return (
    <section id="how-it-works" className="relative py-32 px-4 scroll-mt-24">
      <ParallaxBackdrop className="section-veil opacity-70" distance={140} />

      <div className="max-w-6xl mx-auto relative">
        <Reveal className="max-w-2xl mb-20">
          <p className="eyebrow mb-4">Signal to permanence</p>
          <h2 className="font-display text-5xl md:text-6xl text-white leading-[1.02]">
            How it works
          </h2>
          <div className="rule-hairline mt-6 mb-6 w-40" />
          <p className="text-white/65 font-sans text-lg leading-relaxed">
            From the bridge of a ship to a permanent Bitcoin record — built for evidence,
            not guesswork.
          </p>
        </Reveal>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
          {steps.map((step, i) => (
            <Reveal key={step.number} delay={i * 0.1}>
              <article className="group">
                <div className="mb-6 transition-transform duration-700 group-hover:-translate-y-1.5">
                  <step.Icon size={80} />
                </div>
                <p className="data-label mb-3">Step {step.number}</p>
                <h3 className="font-heading text-2xl tracking-wide text-white mb-3">
                  {step.title}
                </h3>
                <p className="text-sm text-white/65 font-sans leading-relaxed">
                  {step.description}
                </p>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
