type TrackProps = Record<string, string | number | boolean | undefined>

export function trackEvent(name: string, props?: TrackProps): void {
  if (typeof window === "undefined") return
  try {
    const w = window as Window & {
      va?: (event: "event", payload: { name: string; data?: TrackProps }) => void
    }
    w.va?.("event", { name, data: props })
  } catch {
    // Analytics must never break UX
  }
}
