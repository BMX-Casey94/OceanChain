export const SITE_NAME = "Ocechain"
export const SITE_TAGLINE = "Maritime intelligence on Bitcoin"
export const SITE_DESCRIPTION =
  "Ocechain permanently records global maritime AIS vessel positions on Bitcoin — an immutable, publicly verifiable evidence layer for insurers, logistics, compliance teams, and operators."

export function getSiteUrl(): string {
  const raw = process.env.NEXT_PUBLIC_SITE_URL?.trim()
  if (raw) return raw.replace(/\/$/, "")
  return "https://watching.boats"
}

export const X_HANDLE = "@BSVCasey"
export const X_PROFILE_URL = "https://x.com/BSVCasey"

// No mailbox is operated today; enterprise contact routes to X unless overridden.
export function getEnterpriseContactUrl(): string {
  return process.env.NEXT_PUBLIC_CONTACT_URL?.trim() || X_PROFILE_URL
}

export const WHATS_ON_CHAIN_TX = (txid: string) =>
  `https://whatsonchain.com/tx/${txid}`
