"use client"

import { ChevronDown } from "lucide-react"
import { Particles } from "./particles"

const stats = [
  { value: "300,000+", label: "Active Vessels Tracked" },
  { value: "1,000,000+", label: "Daily Transactions" },
  { value: "20 bytes", label: "Per Position Record" },
]

export function Hero() {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center px-4 overflow-hidden">
      {/* Background Layer 1: Teal radial glow */}
      <div 
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse 60% 40% at 50% 60%, rgba(20,184,166,0.07), transparent)"
        }}
        aria-hidden="true"
      />
      
      {/* Background Layer 2: Ship bridge overlay with heavy transparency */}
      <div 
        className="absolute inset-0 pointer-events-none opacity-10"
        style={{
          backgroundImage: "url('https://hebbkx1anhila5yf.public.blob.vercel-storage.com/image-nWbwwzoSSXklmwsECxOBPaExHlpBC8.png')",
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundAttachment: "fixed"
        }}
        aria-hidden="true"
      />
      
      {/* Background Layer 3: Animated particles */}
      <Particles />

      {/* Hero Content */}
      <div className="relative z-10 text-center max-w-5xl mx-auto pt-24">
        {/* Headline */}
        <h1 className="font-heading tracking-wider leading-none text-white">
          <span className="block text-[72px] sm:text-[72px] md:text-[72px]">THE WORLD&apos;S OCEANS</span>
          <span className="block text-[96px] sm:text-[96px] md:text-[96px]">
            LIVE ON{" "}
            <span 
              className="text-teal-400"
              style={{
                textShadow: "0 0 40px rgba(20,184,166,0.9), 0 0 80px rgba(20,184,166,0.4)"
              }}
            >
              BSV
            </span>
          </span>
        </h1>

        {/* Subheadline */}
        <p className="mt-4 text-[14px] md:text-[14px] text-muted-foreground font-sans max-w-[580px] mx-auto leading-relaxed">
          Every vessel. Every coordinate. Every moment. OceanChain permanently records global maritime AIS data on the BSV blockchain — creating an immutable, publicly verifiable record of the world&apos;s oceans.
        </p>

        {/* CTAs */}
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <a href="#architecture" className="btn-neon">
            Explore the Architecture
          </a>
          <a
            href="#"
            className="btn-outline-neon"
          >
            Learn More
          </a>
        </div>

        {/* Stat Pills */}
        <div className="mt-12 flex flex-wrap items-center justify-center gap-6">
          <div className="inner-panel flex items-center gap-6 px-6 py-4">
            {stats.map((stat, index) => (
              <div key={stat.label} className="flex flex-col items-center text-center">
                {index > 0 && (
                  <div className="hidden sm:block absolute -left-3 top-1/2 -translate-y-1/2 w-px h-8 bg-white/10" />
                )}
                <span className="font-heading text-3xl text-teal-400">{stat.value}</span>
                <span className="text-xs text-muted-foreground font-sans mt-1">{stat.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Scroll Indicator */}
        <div className="mt-12 flex justify-center">
          <ChevronDown 
            className="text-teal-400 scroll-indicator" 
            size={32}
            aria-hidden="true"
          />
        </div>
      </div>
    </section>
  )
}
