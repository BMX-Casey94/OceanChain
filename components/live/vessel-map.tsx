"use client"

import { useEffect, useRef, useState } from "react"
import {
  Map as MapLibreMap,
  NavigationControl,
  setWorkerUrl,
  type GeoJSONSource,
} from "maplibre-gl"
import type { TrailPoint, VesselSummary } from "@/lib/api"

const STYLE_URL = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"

// Next/Turbopack does not emit the worker's sibling shared chunk. Serve both from
// /public/maplibre (see MapLibre v6 Next.js install notes) or the browser requests
// /live as a module and fails with MIME text/html.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs")

type VesselMapProps = {
  vessels: VesselSummary[]
  selectedMmsi: string | null
  onSelect: (mmsi: string) => void
  flyTo?: { lon: number; lat: number; zoom?: number; key: number } | null
  pulseMmsi?: string | null
  onAvailabilityChange?: (available: boolean) => void
  /** Route tracker polyline (oldest → newest), or null to hide. */
  trail?: TrailPoint[] | null
  /** Bumps only on a full fleet replace — not on single-vessel upserts or selection. */
  fleetRevision?: number
}

type WebGLStatus = "ok" | "webgl1-only" | "none"

type WebGLDiagnostics = {
  status: WebGLStatus
  /** Driver-supplied reason, when the browser provides one. */
  reason: string | null
  renderer: string | null
}

/**
 * `webglcontextcreationerror` carries the only reliable reason a context was
 * refused (driver blocklist, acceleration disabled, out of contexts).
 */
function probeContext(
  canvas: HTMLCanvasElement,
  kind: "webgl2" | "webgl"
): { context: RenderingContext | null; reason: string | null } {
  let reason: string | null = null
  const onError = (event: Event) => {
    const message = (event as WebGLContextEvent).statusMessage
    if (message) reason = message
  }
  canvas.addEventListener("webglcontextcreationerror", onError)
  let context: RenderingContext | null = null
  try {
    context = canvas.getContext(kind)
  } catch {
    context = null
  }
  canvas.removeEventListener("webglcontextcreationerror", onError)
  return { context, reason }
}

function readRenderer(context: RenderingContext | null): string | null {
  const gl = context as WebGLRenderingContext | null
  if (!gl || typeof gl.getExtension !== "function") return null
  try {
    const info = gl.getExtension("WEBGL_debug_renderer_info")
    if (!info) return null
    const value = gl.getParameter(info.UNMASKED_RENDERER_WEBGL)
    return typeof value === "string" ? value : null
  } catch {
    return null
  }
}

function diagnoseWebGL(): WebGLDiagnostics {
  try {
    const canvas = document.createElement("canvas")
    const gl2 = probeContext(canvas, "webgl2")
    if (gl2.context) {
      return { status: "ok", reason: null, renderer: readRenderer(gl2.context) }
    }
    const gl1 = probeContext(document.createElement("canvas"), "webgl")
    if (gl1.context) {
      return {
        status: "webgl1-only",
        reason: gl2.reason,
        renderer: readRenderer(gl1.context),
      }
    }
    return { status: "none", reason: gl1.reason ?? gl2.reason, renderer: null }
  } catch {
    return { status: "none", reason: null, renderer: null }
  }
}

function webglHelp(status: Exclude<WebGLStatus, "ok">, reason: string | null): string {
  const gpuDisabled =
    !!reason &&
    (/GL_VENDOR\s*=\s*Disabled/i.test(reason) || /Sandboxed\s*=\s*yes/i.test(reason))
  const bindFailed = !!reason && /BindToCurrentSequence failed/i.test(reason)

  if (gpuDisabled || bindFailed) {
    return (
      "Opera’s GPU process is not giving this page a WebGL context " +
      "(GL_VENDOR=Disabled / Sandboxed — this can happen even when “Use graphics acceleration” is already on). " +
      "Open opera://gpu and check whether WebGL/WebGL2 are Hardware accelerated or Disabled. " +
      "Then: fully quit Opera (tray icon too) and reopen; in opera://flags set any WebGL-related flags to Default; " +
      "update your GPU driver; try Chrome/Edge as a control. MapLibre needs a real GPU WebGL2 context."
    )
  }
  if (status === "webgl1-only") {
    return (
      "This browser provides WebGL 1 but not WebGL 2, which the chart requires. " +
      "Check opera://gpu — WebGL2 must be Hardware accelerated."
    )
  }
  return (
    "This browser refused to create any WebGL context, so the chart cannot render. " +
    "Check opera://gpu for the block reason, or try Chrome/Edge with hardware acceleration on."
  )
}

function toFeatureCollection(vessels: VesselSummary[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: vessels
      .filter(
        (v) =>
          Number.isFinite(v.lat) &&
          Number.isFinite(v.lon) &&
          Math.abs(v.lat) <= 90 &&
          Math.abs(v.lon) <= 180
      )
      .map((v) => ({
        type: "Feature",
        properties: {
          mmsi: v.mmsi,
          name: v.name || v.mmsi,
          heading: v.heading ?? 0,
          speed: v.speed,
          selected: 0,
        },
        geometry: {
          type: "Point",
          coordinates: [v.lon, v.lat],
        },
      })),
  }
}

function safeRemoveMap(map: MapLibreMap | null) {
  if (!map) return
  try {
    map.remove()
  } catch {
    // MapLibre can throw if WebGL/context failed mid-init
  }
}

export function VesselMap({
  vessels,
  selectedMmsi,
  onSelect,
  flyTo,
  pulseMmsi,
  onAvailabilityChange,
  trail = null,
  fleetRevision = 0,
}: VesselMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const vesselsRef = useRef(vessels)
  const onSelectRef = useRef(onSelect)
  const [mapError, setMapError] = useState<string | null>(null)
  const [diagnostics, setDiagnostics] = useState<WebGLDiagnostics | null>(null)
  /** True after vessels GeoJSON source + layers exist — avoids race with early /vessels fetch. */
  const [sourceReady, setSourceReady] = useState(false)
  onSelectRef.current = onSelect
  vesselsRef.current = vessels

  useEffect(() => {
    onAvailabilityChange?.(!mapError)
  }, [mapError, onAvailabilityChange])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const webgl = diagnoseWebGL()
    if (webgl.status !== "ok") {
      setDiagnostics(webgl)
      setMapError(webglHelp(webgl.status, webgl.reason))
      return
    }

    let map: MapLibreMap | null = null
    let cancelled = false

    try {
      map = new MapLibreMap({
        container: containerRef.current,
        style: STYLE_URL,
        center: [5, 25],
        zoom: 1.6,
        attributionControl: { compact: true },
        canvasContextAttributes: {
          // Render on a software GL fallback rather than refusing the context.
          failIfMajorPerformanceCaveat: false,
          powerPreference: "high-performance",
        },
      })
    } catch {
      setMapError(
        "The map renderer could not start. This is usually GPU access being blocked — enable hardware acceleration and reload."
      )
      return
    }

    mapRef.current = map
    map.addControl(new NavigationControl({ visualizePitch: false }), "bottom-right")

    map.on("error", (e) => {
      const msg = e?.error?.message || "Map failed to load"
      if (/webgl/i.test(msg)) {
        const webgl = diagnoseWebGL()
        setDiagnostics(webgl)
        const status = webgl.status === "ok" ? "webgl1-only" : webgl.status
        setMapError(webglHelp(status, webgl.reason))
      }
    })

    map.on("load", () => {
      if (cancelled || !map) return

      // Seed with whatever the fleet fetch already returned (often before style load).
      map.addSource("vessels", {
        type: "geojson",
        data: toFeatureCollection(vesselsRef.current),
        cluster: true,
        clusterMaxZoom: 9,
        clusterRadius: 48,
      })

      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "vessels",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#0f766e",
          "circle-stroke-color": "#5eead4",
          "circle-stroke-width": 1.2,
          "circle-opacity": 0.85,
          "circle-radius": ["step", ["get", "point_count"], 16, 25, 20, 100, 26, 500, 34],
        },
      })

      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "vessels",
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-size": 11,
          // Match Carto Dark Matter glyphs; missing fonts can break symbol layers.
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
        },
        paint: {
          "text-color": "#ecfeff",
        },
      })

      map.addLayer({
        id: "vessel-points",
        type: "circle",
        source: "vessels",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": "#14b8a6",
          "circle-radius": 4.5,
          "circle-stroke-width": 1,
          "circle-stroke-color": "rgba(255,255,255,0.35)",
          "circle-opacity": 0.95,
        },
      })

      // Selected vessel sits above clusters so search hits stay visible in a crowd.
      map.addSource("selected-vessel", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      })
      map.addLayer({
        id: "selected-vessel-pulse",
        type: "circle",
        source: "selected-vessel",
        paint: {
          "circle-color": "#fbbf24",
          "circle-radius": 16,
          "circle-opacity": 0.22,
          "circle-blur": 0.35,
        },
      })
      map.addLayer({
        id: "selected-vessel-core",
        type: "circle",
        source: "selected-vessel",
        paint: {
          "circle-color": "#f59e0b",
          "circle-radius": 7,
          "circle-stroke-width": 2.4,
          "circle-stroke-color": "#fffbeb",
          "circle-opacity": 1,
        },
      })

      map.addSource("vessel-trail", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      })
      map.addLayer({
        id: "vessel-trail-line",
        type: "line",
        source: "vessel-trail",
        paint: {
          "line-color": "#5eead4",
          "line-width": 2.5,
          "line-opacity": 0.85,
        },
      })
      map.addLayer({
        id: "vessel-trail-points",
        type: "circle",
        source: "vessel-trail",
        paint: {
          "circle-color": "#99f6e4",
          "circle-radius": 3.5,
          "circle-stroke-width": 1,
          "circle-stroke-color": "rgba(255,255,255,0.5)",
        },
      })

      map.on("click", "clusters", async (e) => {
        const features = map!.queryRenderedFeatures(e.point, { layers: ["clusters"] })
        const clusterId = features[0]?.properties?.cluster_id
        const source = map!.getSource("vessels") as GeoJSONSource
        if (clusterId == null) return
        const zoom = await source.getClusterExpansionZoom(clusterId)
        const coords = (features[0].geometry as GeoJSON.Point).coordinates as [number, number]
        map!.easeTo({ center: coords, zoom })
      })

      map.on("click", "vessel-points", (e) => {
        const mmsi = e.features?.[0]?.properties?.mmsi
        if (typeof mmsi === "string") onSelectRef.current(mmsi)
      })

      map.on("mouseenter", "vessel-points", () => {
        map!.getCanvas().style.cursor = "pointer"
      })
      map.on("mouseleave", "vessel-points", () => {
        map!.getCanvas().style.cursor = ""
      })
      map.on("mouseenter", "clusters", () => {
        map!.getCanvas().style.cursor = "pointer"
      })
      map.on("mouseleave", "clusters", () => {
        map!.getCanvas().style.cursor = ""
      })

      if (!cancelled) setSourceReady(true)
    })

    return () => {
      cancelled = true
      setSourceReady(false)
      safeRemoveMap(map)
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!sourceReady || mapError) return
    const map = mapRef.current
    if (!map) return
    const source = map.getSource("vessels") as GeoJSONSource | undefined
    if (!source) return
    source.setData(toFeatureCollection(vesselsRef.current))
  }, [fleetRevision, vessels.length, mapError, sourceReady])

  useEffect(() => {
    if (!sourceReady || mapError) return
    const map = mapRef.current
    if (!map || !map.getLayer("vessel-points")) return
    map.setPaintProperty("vessel-points", "circle-color", [
      "case",
      ["==", ["get", "mmsi"], selectedMmsi || ""],
      "#5eead4",
      ["==", ["get", "mmsi"], pulseMmsi || ""],
      "#99f6e4",
      "#14b8a6",
    ])
    map.setPaintProperty("vessel-points", "circle-radius", [
      "case",
      ["==", ["get", "mmsi"], selectedMmsi || ""],
      7.5,
      ["==", ["get", "mmsi"], pulseMmsi || ""],
      6.5,
      4.5,
    ])
  }, [selectedMmsi, pulseMmsi, mapError, sourceReady])

  useEffect(() => {
    if (!sourceReady || mapError) return
    const map = mapRef.current
    if (!map) return
    const source = map.getSource("selected-vessel") as GeoJSONSource | undefined
    if (!source) return
    const selected = selectedMmsi
      ? vessels.find((v) => v.mmsi === selectedMmsi)
      : undefined
    if (!selected || !Number.isFinite(selected.lat) || !Number.isFinite(selected.lon)) {
      source.setData({ type: "FeatureCollection", features: [] })
      return
    }
    source.setData({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { mmsi: selected.mmsi },
          geometry: { type: "Point", coordinates: [selected.lon, selected.lat] },
        },
      ],
    })
  }, [vessels, selectedMmsi, mapError, sourceReady])

  useEffect(() => {
    if (!sourceReady || mapError || !selectedMmsi) return
    const map = mapRef.current
    if (!map || !map.getLayer("selected-vessel-pulse")) return
    let frame = 0
    const tick = (now: number) => {
      const wave = (Math.sin(now / 320) + 1) / 2
      try {
        map.setPaintProperty("selected-vessel-pulse", "circle-radius", 11 + wave * 16)
        map.setPaintProperty("selected-vessel-pulse", "circle-opacity", 0.32 - wave * 0.24)
      } catch {
        // layer may be gone during teardown
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [selectedMmsi, mapError, sourceReady])

  useEffect(() => {
    if (!sourceReady || mapError) return
    const map = mapRef.current
    if (!map) return
    const source = map.getSource("vessel-trail") as GeoJSONSource | undefined
    if (!source) return
    if (!trail || trail.length === 0) {
      source.setData({ type: "FeatureCollection", features: [] })
      return
    }
    const coords = trail.map((p) => [p.lon, p.lat] as [number, number])
    const line: GeoJSON.Feature = {
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: coords },
    }
    const points: GeoJSON.Feature[] = trail.map((p) => ({
      type: "Feature",
      properties: { timestamp: p.timestamp, txid: p.txid ?? "" },
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
    }))
    source.setData({ type: "FeatureCollection", features: [line, ...points] })
  }, [trail, mapError, sourceReady])

  useEffect(() => {
    if (!flyTo || !mapRef.current || mapError) return
    try {
      const map = mapRef.current
      const currentZoom = map.getZoom()
      // Keep current zoom if already closer than the requested target (vessel select default 8).
      const targetZoom =
        flyTo.zoom != null ? Math.max(currentZoom, flyTo.zoom) : currentZoom
      map.flyTo({
        center: [flyTo.lon, flyTo.lat],
        zoom: targetZoom,
        essential: true,
        speed: 1.1,
      })
    } catch {
      // ignore fly errors during teardown
    }
  }, [flyTo, mapError])

  return (
    <div className="live-map-root relative" role="presentation">
      <div ref={containerRef} className="absolute inset-0" />
      {mapError && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#020b12]/92 px-6">
          <div className="live-panel rounded-2xl max-w-lg p-6 text-left">
            <p className="font-heading text-xl tracking-wide text-white">Chart unavailable</p>
            <p className="mt-3 text-sm text-white/65 leading-relaxed">{mapError}</p>

            {diagnostics && (
              <dl className="mt-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs font-mono">
                <dt className="text-white/40">webgl2</dt>
                <dd className="text-white/75">
                  {diagnostics.status === "ok" ? "available" : "unavailable"}
                </dd>
                <dt className="text-white/40">webgl1</dt>
                <dd className="text-white/75">
                  {diagnostics.status === "none" ? "unavailable" : "available"}
                </dd>
                {diagnostics.renderer && (
                  <>
                    <dt className="text-white/40">renderer</dt>
                    <dd className="text-white/75 break-all">{diagnostics.renderer}</dd>
                  </>
                )}
                {diagnostics.reason && (
                  <>
                    <dt className="text-white/40">driver</dt>
                    <dd className="text-white/75 break-all">{diagnostics.reason}</dd>
                  </>
                )}
              </dl>
            )}

            <p className="mt-5 text-xs text-white/40 leading-relaxed">
              Vessel search and details work without the chart. To fix rendering, enable
              hardware acceleration in your browser settings and restart it.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
