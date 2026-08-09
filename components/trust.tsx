"use client"

import Link from "next/link"
import { ParallaxBackdrop, Reveal } from "@/components/parallax"
import { BeaconIcon } from "@/components/icons/marine"

export function Trust() {
  return (
    <section id="trust" className="relative py-28 px-4 scroll-mt-24 overflow-hidden">
      <ParallaxBackdrop className="section-veil opacity-80" distance={180} />

      <div className="max-w-6xl mx-auto relative">
        <Reveal className="max-w-3xl">
          <div className="mb-8">
            <BeaconIcon size={84} />
          </div>
          <p className="eyebrow mb-4">No trust required</p>
          <h2 className="font-display text-5xl md:text-6xl text-white leading-[1.02]">
            Publicly <em className="italic text-teal-300">verifiable</em>
          </h2>
          <div className="rule-hairline mt-6 mb-6 w-40" />
          <p className="text-lg text-white/70 font-sans leading-relaxed">
            Ocechain does not ask you to trust a private database. Vessel positions are written to Bitcoin
            so counterparties — insurers, counsel, operators, journalists — can inspect the same permanent trail.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link href="/live" className="btn-neon">
              Open the live map
            </Link>
            <Link href="/faq" className="btn-outline-neon">
              Read the FAQ
            </Link>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
