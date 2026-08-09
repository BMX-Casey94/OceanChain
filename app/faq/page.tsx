import type { Metadata } from "next"
import Link from "next/link"
import { Navigation } from "@/components/navigation"
import { Footer } from "@/components/footer"
import { FaqJsonLd } from "@/components/seo/json-ld"
import { FAQ_ITEMS } from "@/lib/faq"
import { SITE_NAME } from "@/lib/site"

export const metadata: Metadata = {
  title: "FAQ",
  description:
    "Frequently asked questions about Ocechain — maritime AIS intelligence permanently recorded on Bitcoin for insurance, logistics, and compliance.",
  alternates: { canonical: "/faq" },
  openGraph: {
    title: `FAQ | ${SITE_NAME}`,
    description:
      "Answers on AIS evidence, Bitcoin records, live map search, and who Ocechain is built for.",
    url: "/faq",
  },
}

export default function FaqPage() {
  return (
    <>
      <FaqJsonLd />
      <Navigation />
      <main id="main-content" className="pt-28 pb-20 px-4">
        <div className="max-w-3xl mx-auto">
          <p className="text-xs uppercase tracking-[0.2em] text-teal-300/80 mb-3">Ocechain</p>
          <h1 className="font-heading text-5xl md:text-6xl tracking-wide text-white">
            Frequently asked questions
          </h1>
          <p className="mt-4 text-white/65 text-lg leading-relaxed">
            Clear answers for insurers, operators, and anyone evaluating maritime evidence on Bitcoin.
          </p>

          <div className="mt-12 space-y-8">
            {FAQ_ITEMS.map((item) => (
              <article key={item.question} className="border-t border-white/10 pt-6">
                <h2 className="font-heading text-2xl tracking-wide text-white">{item.question}</h2>
                <p className="mt-3 text-sm md:text-base text-white/65 leading-relaxed">{item.answer}</p>
              </article>
            ))}
          </div>

          <div className="mt-14 flex flex-wrap gap-4">
            <Link href="/live" className="btn-neon">
              Open the live fleet
            </Link>
            <Link href="/" className="btn-outline-neon">
              Back to {SITE_NAME}
            </Link>
          </div>
        </div>
      </main>
      <Footer />
    </>
  )
}
