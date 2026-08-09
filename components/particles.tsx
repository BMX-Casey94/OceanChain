"use client"

/**
 * Deterministic particle field — avoids SSR/client hydration mismatch from Math.random().
 */
const PARTICLES = Array.from({ length: 24 }, (_, i) => {
  // Simple deterministic pseudo-random from index
  const a = ((i + 1) * 37) % 100
  const b = ((i + 1) * 53) % 100
  const c = ((i + 1) * 17) % 100
  return {
    id: i,
    x: (a * 0.97 + 1.5) % 100,
    y: (b * 0.91 + 2.1) % 100,
    size: 2 + (c % 20) / 10,
    duration: 6 + (c % 80) / 10,
    delay: (a % 100) / 10,
  }
})

export function Particles() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      {PARTICLES.map((particle) => (
        <span
          key={particle.id}
          className="particle absolute rounded-full"
          style={{
            left: `${particle.x}%`,
            top: `${particle.y}%`,
            width: `${particle.size}px`,
            height: `${particle.size}px`,
            backgroundColor: "rgba(20, 184, 166, 0.25)",
            ["--duration" as string]: `${particle.duration}s`,
            ["--delay" as string]: `${particle.delay}s`,
          }}
        />
      ))}
    </div>
  )
}
