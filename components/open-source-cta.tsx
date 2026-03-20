"use client"

const badges = [
  "Python 3.11",
  "FastAPI",
  "BSV Blockchain",
  "AISstream.io",
  "GorillaPool ARC",
]

export function OpenSourceCTA() {
  return (
    <section className="py-24 px-4">
      <div className="max-w-2xl mx-auto text-center">
        <div className="glass-card p-12">
          {/* Heading */}
          <h2 className="font-heading text-5xl text-white mb-6">
            Enterprise Grade Infrastructure
          </h2>

          {/* Description */}
          <p className="text-muted-foreground font-sans leading-relaxed mb-8">
            OceanChain is built with enterprise-grade infrastructure featuring a Python broadcasting engine, BSV transaction logic, and a modern Next.js frontend designed for reliability and scale.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-10">
            <a
              href="#architecture"
              className="btn-neon"
            >
              Learn More
            </a>
            <a
              href="#"
              className="btn-outline-neon"
            >
              Documentation
            </a>
          </div>

          {/* Tech Badges */}
          <div className="flex flex-wrap items-center justify-center gap-3">
            {badges.map((badge) => (
              <span
                key={badge}
                className="inner-panel px-3 py-1.5 text-xs text-muted-foreground font-sans border border-white/10 rounded-full"
              >
                {badge}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
