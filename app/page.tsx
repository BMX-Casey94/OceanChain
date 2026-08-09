import { Navigation } from "@/components/navigation"
import { Hero } from "@/components/hero"
import { Ticker } from "@/components/ticker"
import { HowItWorks } from "@/components/how-it-works"
import { UseCases } from "@/components/use-cases"
import { Architecture } from "@/components/architecture"
import { Stats } from "@/components/stats"
import { Trust } from "@/components/trust"
import { Footer } from "@/components/footer"
import { Reveal } from "@/components/parallax"

export default function HomePage() {
  return (
    <>
      <Navigation />
      <main id="main-content">
        <Hero />
        <Ticker />
        <section className="px-4 py-24 max-w-6xl mx-auto">
          <Reveal>
            <p className="font-display text-3xl md:text-4xl text-white/85 leading-[1.25] max-w-4xl">
              Ocechain is maritime intelligence on Bitcoin: live AIS vessel positions recorded as
              permanent, publicly verifiable ledger entries — for marine insurance, logistics,
              compliance, and operators who need{" "}
              <em className="italic text-teal-300">evidence, not screenshots</em>.
            </p>
          </Reveal>
        </section>
        <HowItWorks />
        <UseCases />
        <Architecture />
        <Stats />
        <Trust />
      </main>
      <Footer />
    </>
  )
}
