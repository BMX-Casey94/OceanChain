/**
 * Copy MapLibre worker + shared ESM into public/ for Next.js (Turbopack/webpack).
 * Run after upgrading maplibre-gl: pnpm sync:maplibre-worker
 */
import { copyFileSync, mkdirSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { createRequire } from "node:module"

const root = join(dirname(fileURLToPath(import.meta.url)), "..")
const require = createRequire(import.meta.url)
const pkgDir = dirname(require.resolve("maplibre-gl/package.json"))
const dist = join(pkgDir, "dist")
const out = join(root, "public", "maplibre")

mkdirSync(out, { recursive: true })
for (const name of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(dist, name), join(out, name))
  console.log(`synced ${name}`)
}
