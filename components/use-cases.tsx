"use client"

import Link from "next/link"
import { getEnterpriseMailto } from "@/lib/site"
import { ParallaxBackdrop, Reveal } from "@/components/parallax"
import {
  AnchorShieldIcon,
  BeaconIcon,
  ContainerShipIcon,
  PortCraneIcon,
} from "@/components/icons/marine"

const cases = [
  {
    Icon: AnchorShieldIcon,
    title: "Marine insurance & claims",
    body: "Reconstruct voyages with timestamped, tamper-evident positions. Verify incident locations, accelerate claims, and reduce fraud disputes.",
  },
  {
    Icon: ContainerShipIcon,
    title: "Operators & P&I",
    body: "Independent proof of where a vessel was when timelines are contested — useful for owners, managers, and mutual clubs.",
  },
  {
    Icon: BeaconIcon,
    title: "Compliance & disputes",
    body: "Cite a publicly auditable movement trail for high-stakes reviews without relying solely on a closed database.",
  },
  {
    Icon: PortCraneIcon,
    title: "Ports & logistics",
    body: "Add confidence around vessel presence and ETA context for terminals, cargo teams, and supply-chain operations.",
  },
]

export function UseCases() {
  return (
    <section id="use-cases" className="relative py-32 px-4 scroll-mt-24 overflow-hidden">
      <ParallaxBackdrop className="section-veil" distance={160} />

      <div className="max-w-6xl mx-auto relative">
        <Reveal className="max-w-2xl mb-20">
          <p className="eyebrow mb-4">Who it serves</p>
          <h2 className="font-display text-5xl md:text-6xl text-white leading-[1.02]">
            Built for decisions <em className="italic text-teal-300">at sea</em>
          </h2>
          <div className="rule-hairline mt-6 mb-6 w-40" />
          <p className="text-white/65 font-sans text-lg leading-relaxed">
            Ocechain is an evidence layer — permanent vessel positions on Bitcoin for teams
            who underwrite risk, move cargo, or settle disputes.
          </p>
        </Reveal>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-14">
          {cases.map((item, i) => (
            <Reveal key={item.title} delay={i * 0.09}>
              <article className="flex gap-6 group">
                <div className="shrink-0 transition-transform duration-700 group-hover:-translate-y-1.5">
                  <item.Icon size={72} />
                </div>
                <div>
                  <h3 className="font-heading text-2xl tracking-wide text-white mb-2.5">
                    {item.title}
                  </h3>
                  <p className="text-sm text-white/65 font-sans leading-relaxed max-w-md">
                    {item.body}
                  </p>
                </div>
              </article>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.1}>
          <div className="mt-16 flex flex-col sm:flex-row gap-4 items-start sm:items-center">
            <Link href="/live" className="btn-neon">
              Explore the live map
            </Link>
            <a
              href={getEnterpriseMailto("Ocechain — insurance & enterprise")}
              className="btn-outline-neon"
            >
              Discuss enterprise access
            </a>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
