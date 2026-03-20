"use client"

import { useMemo } from "react"

interface Particle {
  id: number
  x: number
  y: number
  size: number
  duration: number
  delay: number
}

export function Particles() {
  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: 24 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: 2 + Math.random() * 2,
      duration: 6 + Math.random() * 8,
      delay: Math.random() * 10,
    }))
  }, [])

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      {particles.map((particle) => (
        <span
          key={particle.id}
          className="particle absolute rounded-full"
          style={{
            left: `${particle.x}%`,
            top: `${particle.y}%`,
            width: `${particle.size}px`,
            height: `${particle.size}px`,
            backgroundColor: "rgba(20, 184, 166, 0.25)",
            "--duration": `${particle.duration}s`,
            "--delay": `${particle.delay}s`,
          } as React.CSSProperties}
        />
      ))}
    </div>
  )
}
