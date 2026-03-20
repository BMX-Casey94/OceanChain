import { Navigation } from "@/components/navigation"
import { Hero } from "@/components/hero"
import { Ticker } from "@/components/ticker"
import { HowItWorks } from "@/components/how-it-works"
import { Architecture } from "@/components/architecture"
import { Stats } from "@/components/stats"
import { Footer } from "@/components/footer"

export default function HomePage() {
  return (
    <>
      <Navigation />
      <main>
        <Hero />
        <Ticker />
        <section id="features">
          <HowItWorks />
        </section>
        <Architecture />
        <Stats />
      </main>
      <Footer />
    </>
  )
}
