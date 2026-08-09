"use client"

import Link from "next/link"

export function OpenSourceCTA() {
  return (
    <section className="py-20 px-4">
      <div className="max-w-4xl mx-auto text-center">
        <h2 className="font-heading text-4xl md:text-5xl tracking-wide text-white mb-4">
          Built for production maritime evidence
        </h2>
        <p className="text-sm md:text-base text-white/65 font-sans leading-relaxed max-w-2xl mx-auto">
          Ocechain combines a Python broadcasting engine, Bitcoin transaction logic, and a modern
          Next.js experience — designed for reliability at fleet scale.
        </p>
        <div className="mt-8 flex flex-col sm:flex-row gap-4 justify-center">
          <Link href="/live" className="btn-neon">
            Open the live fleet
          </Link>
          <Link href="/faq" className="btn-outline-neon">
            Read the FAQ
          </Link>
        </div>
      </div>
    </section>
  )
}
