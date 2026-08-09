export const SITE_NAME = "Ocechain"
export const SITE_TAGLINE = "Maritime intelligence on Bitcoin"
export const SITE_DESCRIPTION =
  "Ocechain permanently records global maritime AIS vessel positions on Bitcoin — an immutable, publicly verifiable evidence layer for insurers, logistics, compliance teams, and operators."

export function getSiteUrl(): string {
  const raw = process.env.NEXT_PUBLIC_SITE_URL?.trim()
  if (raw) return raw.replace(/\/$/, "")
  return "https://ocechain.com"
}

export function getEnterpriseEmail(): string {
  return (
    process.env.NEXT_PUBLIC_ENTERPRISE_EMAIL?.trim() ||
    "enterprise@ocechain.com"
  )
}

export function getEnterpriseMailto(subject = "Ocechain enterprise enquiry"): string {
  return `mailto:${getEnterpriseEmail()}?subject=${encodeURIComponent(subject)}`
}

export const WHATS_ON_CHAIN_TX = (txid: string) =>
  `https://whatsonchain.com/tx/${txid}`
