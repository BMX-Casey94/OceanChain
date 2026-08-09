"use client"

import Link from "next/link"
import { BrandMark } from "@/components/brand-mark"
import { getEnterpriseMailto } from "@/lib/site"

export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="border-t border-white/8 bg-black/50 backdrop-blur-sm">
      <div className="max-w-6xl mx-auto px-4 py-14">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
          <div>
            <BrandMark href="/" />
            <p className="mt-4 text-sm text-white/55 font-sans max-w-xs leading-relaxed">
              Permanent maritime AIS records on Bitcoin — built for evidence, insurance, and operational truth.
            </p>
          </div>

          <div>
            <h3 className="text-xs uppercase tracking-[0.2em] text-white/40 mb-4">Explore</h3>
            <ul className="space-y-2 text-sm text-white/70">
              <li>
                <Link href="/live" className="hover:text-teal-300 transition-colors">
                  Live fleet
                </Link>
              </li>
              <li>
                <Link href="/#use-cases" className="hover:text-teal-300 transition-colors">
                  Use cases
                </Link>
              </li>
              <li>
                <Link href="/#how-it-works" className="hover:text-teal-300 transition-colors">
                  How it works
                </Link>
              </li>
              <li>
                <Link href="/faq" className="hover:text-teal-300 transition-colors">
                  FAQ
                </Link>
              </li>
              <li>
                <a href="/llms.txt" className="hover:text-teal-300 transition-colors">
                  LLM summary
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="text-xs uppercase tracking-[0.2em] text-white/40 mb-4">Enterprise</h3>
            <a
              href={getEnterpriseMailto()}
              className="text-sm text-teal-300 hover:text-teal-200 transition-colors"
            >
              Contact enterprise
            </a>
            <p className="mt-4 text-xs text-white/40 leading-relaxed">
              AIS data via AISstream. Ocechain is not a navigational aid and must not be used for collision avoidance or voyage planning.
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-white/8">
        <div className="max-w-6xl mx-auto px-4 py-6 flex flex-col sm:flex-row gap-2 sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground font-sans">
            Ocechain · Maritime intelligence on Bitcoin · {currentYear}
          </p>
          <p className="text-xs text-white/35 font-sans">
            On-chain prefix: Ocechain
          </p>
        </div>
      </div>
    </footer>
  )
}
