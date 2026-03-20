"use client"

import { Gem } from "lucide-react"

export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer 
      className="border-t border-white/5 backdrop-blur-sm"
      style={{ background: "rgba(0,0,0,0.6)" }}
    >
      <div className="max-w-6xl mx-auto px-4 py-12">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8">
          {/* Logo Section */}
          <div>
            <div className="flex items-baseline">
              <span className="font-heading text-2xl tracking-wide text-teal-400">OCEAN</span>
              <span className="font-heading text-2xl tracking-wide text-white">CHAIN</span>
            </div>
            <p className="text-xs text-muted-foreground font-sans mt-1">
              BSV Maritime Intelligence
            </p>
          </div>

          {/* BSV Badge */}
          <div className="inline-flex items-center gap-2 border border-teal-500/30 rounded-full px-4 py-2">
            <Gem className="text-teal-400" size={14} aria-hidden="true" />
            <span className="text-xs text-muted-foreground font-sans">
              Powered by BSV Blockchain
            </span>
          </div>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="border-t border-white/5">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <p className="text-center text-xs text-muted-foreground font-sans">
            OceanChain · Maritime intelligence on BSV · {currentYear}
          </p>
        </div>
      </div>
    </footer>
  )
}
