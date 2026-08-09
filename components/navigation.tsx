"use client"

import { useState } from "react"
import Link from "next/link"
import { Menu, X } from "lucide-react"
import { BrandMark } from "@/components/brand-mark"
import { getEnterpriseMailto } from "@/lib/site"

const navLinks = [
  { href: "/live", label: "Live fleet" },
  { href: "/#use-cases", label: "Use cases" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/faq", label: "FAQ" },
]

export function Navigation() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 border-b border-white/8 bg-[#020b12]/72 backdrop-blur-xl"
      aria-label="Main navigation"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <BrandMark />

          <div className="hidden md:flex items-center gap-8">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm font-sans text-white/65 hover:text-teal-300 transition-colors duration-300"
              >
                {link.label}
              </Link>
            ))}
            <Link href="/live" className="btn-neon !py-2 !px-4 text-sm">
              Search vessels
            </Link>
            <a
              href={getEnterpriseMailto()}
              className="text-sm font-sans text-teal-300/90 hover:text-teal-200 transition-colors"
            >
              Talk to us
            </a>
          </div>

          <button
            className="md:hidden p-2 text-white/70 hover:text-teal-300 transition-colors"
            onClick={() => setIsOpen(!isOpen)}
            aria-expanded={isOpen}
            aria-label={isOpen ? "Close menu" : "Open menu"}
          >
            {isOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </div>

      {isOpen && (
        <div className="md:hidden border-t border-white/8 bg-[#020b12]/95">
          <div className="px-4 py-4 space-y-3">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="block text-sm font-sans text-white/70 hover:text-teal-300 transition-colors"
                onClick={() => setIsOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <Link
              href="/live"
              className="block btn-neon text-center"
              onClick={() => setIsOpen(false)}
            >
              Search vessels
            </Link>
            <a
              href={getEnterpriseMailto()}
              className="block text-sm text-teal-300"
              onClick={() => setIsOpen(false)}
            >
              Enterprise enquiry
            </a>
          </div>
        </div>
      )}
    </nav>
  )
}
