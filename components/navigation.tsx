"use client"

import { useState } from "react"
import { Menu, X } from "lucide-react"

const navLinks = [
  { href: "#features", label: "Features" },
  { href: "#how-it-works", label: "How It Works" },
  { href: "#architecture", label: "Architecture" },
]

export function Navigation() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <nav 
      className="fixed top-0 left-0 right-0 z-50 backdrop-blur-xl border-b border-white/5"
      style={{ background: "rgba(0,0,0,0.6)" }}
      aria-label="Main navigation"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex flex-col">
            <div className="flex items-baseline">
              <span className="font-heading text-2xl tracking-wide text-teal-400">OCEAN</span>
              <span className="font-heading text-2xl tracking-wide text-white">CHAIN</span>
            </div>
            <span className="text-xs text-muted-foreground font-sans -mt-1">BSV Maritime Intelligence</span>
          </div>

          {/* Desktop Nav Links */}
          <div className="hidden md:flex items-center gap-8">
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-sm font-sans text-muted-foreground hover:text-teal-400 transition-colors duration-300"
              >
                {link.label}
              </a>
            ))}
          </div>

          {/* Mobile Menu Button */}
          <button
            className="md:hidden p-2 text-muted-foreground hover:text-teal-400 transition-colors"
            onClick={() => setIsOpen(!isOpen)}
            aria-expanded={isOpen}
            aria-label={isOpen ? "Close menu" : "Open menu"}
          >
            {isOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </div>

      {/* Mobile Menu Drawer */}
      {isOpen && (
        <div className="md:hidden border-t border-white/5" style={{ background: "rgba(0,0,0,0.95)" }}>
          <div className="px-4 py-4 space-y-4">
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="block text-sm font-sans text-muted-foreground hover:text-teal-400 transition-colors duration-300"
                onClick={() => setIsOpen(false)}
              >
                {link.label}
              </a>
            ))}
          </div>
        </div>
      )}
    </nav>
  )
}
