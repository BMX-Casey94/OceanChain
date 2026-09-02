import { FAQ_ITEMS } from "@/lib/faq"
import {
  SITE_DESCRIPTION,
  SITE_NAME,
  SITE_TAGLINE,
  X_PROFILE_URL,
  getSiteUrl,
} from "@/lib/site"

/** Site-wide Organization / WebSite / SoftwareApplication graph. */
export function JsonLd() {
  const siteUrl = getSiteUrl()
  const logoUrl = `${siteUrl}/apple-icon`

  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${siteUrl}/#organisation`,
        name: SITE_NAME,
        legalName: SITE_NAME,
        alternateName: "watching.boats",
        url: siteUrl,
        description: SITE_DESCRIPTION,
        slogan: SITE_TAGLINE,
        logo: {
          "@type": "ImageObject",
          url: logoUrl,
          width: 180,
          height: 180,
        },
        image: logoUrl,
        sameAs: [X_PROFILE_URL],
        contactPoint: [
          {
            "@type": "ContactPoint",
            contactType: "sales",
            url: X_PROFILE_URL,
            areaServed: "Worldwide",
            availableLanguage: ["en-GB", "en"],
          },
        ],
        knowsAbout: [
          "AIS vessel tracking",
          "maritime intelligence",
          "marine insurance evidence",
          "Bitcoin",
          "ship position records",
          "boat watching",
          "vessel spotting",
          "fleet monitoring",
          "shipping intelligence",
        ],
      },
      {
        "@type": "WebSite",
        "@id": `${siteUrl}/#website`,
        url: siteUrl,
        name: SITE_NAME,
        description: SITE_DESCRIPTION,
        inLanguage: "en-GB",
        publisher: { "@id": `${siteUrl}/#organisation` },
        potentialAction: {
          "@type": "SearchAction",
          target: {
            "@type": "EntryPoint",
            urlTemplate: `${siteUrl}/live?q={search_term_string}`,
          },
          "query-input": "required name=search_term_string",
        },
      },
      {
        "@type": "SoftwareApplication",
        "@id": `${siteUrl}/#app`,
        name: `${SITE_NAME} Live Fleet`,
        applicationCategory: "BusinessApplication",
        applicationSubCategory: "Maritime intelligence",
        operatingSystem: "Web",
        description: SITE_DESCRIPTION,
        url: `${siteUrl}/live`,
        image: logoUrl,
        publisher: { "@id": `${siteUrl}/#organisation` },
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "GBP",
        },
        featureList: [
          "Live AIS vessel map",
          "Vessel search by name, MMSI, and call sign",
          "Location search for ports, places, and coordinates",
          "Bitcoin-recorded position evidence",
        ],
      },
    ],
  }

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(graph) }}
    />
  )
}

/** FAQPage schema — only mount on the FAQ route so it matches visible content. */
export function FaqJsonLd() {
  const siteUrl = getSiteUrl()

  const graph = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "@id": `${siteUrl}/faq#faq`,
    url: `${siteUrl}/faq`,
    mainEntity: FAQ_ITEMS.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: item.answer,
      },
    })),
  }

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(graph) }}
    />
  )
}
