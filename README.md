# Ocechain

**Maritime intelligence on Bitcoin** — permanent, publicly verifiable records of global vessel tracking data.

Ocechain ingests real-time AIS vessel positions via AISstream.io and records each position as an OP_RETURN transaction on Bitcoin. The public site includes a cinematic product landing page and a live fleet map with ship and location search.

> Brand: **Ocechain**. On-chain OP_RETURN prefix is `Ocechain`. Ops identifiers (`OCEANCHAIN_*`, DB user `oceanchain`) are unchanged.

```
AISstream.io → Python engine (AIS + UTXO pool + broadcaster)
                    ├─→ Bitcoin (permanent OP_RETURN records)
                    └─→ FastAPI (/vessels, /stats, /ws)
                              ↓
               Next.js site — /  ·  /live  ·  /faq
```

## Features

- **Live fleet map** (`/live`) — MapLibre map, clustering, vessel panel, WebSocket updates
- **Search** — ships (MMSI / name / call sign) and locations (ports, places, coordinates)
- **Deep links** — `/live?mmsi=`, `/live?q=`, `/live?lat=&lon=&z=`
- **Bitcoin permanence** — compact on-chain position records, publicly verifiable
- **Enterprise narrative** — insurance, logistics, compliance, operators
- **SEO + LLM pack** — sitemap, robots, JSON-LD, `llms.txt`, `llms-full.txt`, FAQ

## Project structure

```
ocechain/
├── app/                      # Next.js App Router
│   ├── page.tsx              # Marketing landing
│   ├── live/page.tsx         # Live fleet map
│   ├── faq/page.tsx
│   ├── api/geocode/          # Nominatim proxy (cached, rate-limited)
│   ├── sitemap.ts
│   └── robots.ts
├── components/               # UI + live map components
├── lib/                      # site config, API client, analytics
├── public/llms.txt           # LLM-oriented summary
├── backend/                  # Python broadcasting engine + API
│   ├── main.py
│   ├── ais_client.py
│   ├── vessel_api.py         # Snapshot serialisation + search
│   ├── api_server.py         # FastAPI HTTP + WebSocket
│   └── …
└── docs/
```

## Frontend (Vercel / local)

### Environment variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SITE_URL` | Canonical site URL (production: `https://watching.boats`) |
| `NEXT_PUBLIC_API_BASE` | Browser API origin. Prefer `/ocechain-api` on Vercel (same-origin proxy). Local: `http://localhost:8000` |
| `API_PROXY_TARGET` | Server-only rewrite target for `/ocechain-api/*` (e.g. `http://185.249.72.134:8000`) |
| `NEXT_PUBLIC_WS_URL` | Optional explicit `ws(s)://…/ws` when REST uses the proxy (needs `wss://` from HTTPS) |
| `NEXT_PUBLIC_CONTACT_URL` | Optional enterprise contact target (defaults to `https://x.com/BSVCasey`) |

Copy [`.env.example`](.env.example) to `.env.local` for local development.

```bash
pnpm install
pnpm dev
```

Production build:

```bash
pnpm build
pnpm start
```

> This repo uses `node-linker=hoisted` in [`.npmrc`](.npmrc) for exFAT-compatible installs on Windows.

### Security headers

[`next.config.mjs`](next.config.mjs) sets CSP, `Referrer-Policy`, `X-Content-Type-Options`, and frame protections.

## Backend API (public)

Ensure `CORS_ALLOW_ORIGINS` includes your frontend origin(s).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Engine health |
| GET | `/stats/summary` | Aggregate stats |
| GET | `/stats/timeseries` | TX counts per minute |
| GET | `/vessels` | Snapshot list (`bbox`, `near`, `radius_nm`, `limit`) |
| GET | `/vessels/search?q=` | Search MMSI / name / call sign / IMO |
| GET | `/vessels/{mmsi}` | Vessel detail |
| WS | `/ws` | Live `stats`, `tx`, `utxo` events |

Admin/UTXO routes remain available on the VPS; protect with `OCEANCHAIN_ADMIN_API_KEY` where required. Do not expose admin keys to the browser.

### Read-only mode (local frontend development)

To develop the frontend against real live vessel data without Postgres, a funded wallet, or any
chain writes, run the read-only API. It starts the AIS ingest client and the query endpoints only,
and rejects every mutating request:

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env      # only AISSTREAM_API_KEY is required for this mode
python read_only_api.py   # http://127.0.0.1:8000
```

Point the frontend at it with `NEXT_PUBLIC_API_BASE=http://localhost:8000` in `.env.local`.
Vessels appear as AIS messages arrive, so the first positions take a few seconds. Because nothing
is broadcast, `last_txid` stays empty and transaction counters remain at zero — the map, search,
and vessel details all work.

## Backend deployment (Linux VPS)

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- systemd
- Funded wallet for transaction fees (network tooling remains BSV-compatible in ops)

### Installation (summary)

```bash
sudo useradd -r -s /bin/false oceanchain
sudo mkdir -p /opt/oceanchain
sudo chown -R oceanchain:oceanchain /opt/oceanchain
# copy files → /opt/oceanchain
cd /opt/oceanchain/backend
sudo -u oceanchain python3 -m venv venv
sudo -u oceanchain venv/bin/pip install -r requirements.txt
sudo -u oceanchain cp .env.example .env
# edit .env — include CORS_ALLOW_ORIGINS for your Vercel domain
```

See [`backend/.env.example`](backend/.env.example) for the full variable list, UTXO pool tuning, and ARC settings.

Enable the systemd unit from [`backend/systemd/oceanchain.service`](backend/systemd/oceanchain.service).

### Further documentation

- [AIS message expansion plan](docs/AIS_MESSAGE_EXPANSION_PLAN.md)
- [Arcade / Teranode notes](docs/ARCADE_TERANODE_NOTES.md)

## Disclaimer

Ocechain is **not a navigational aid** and must not be used for collision avoidance or voyage planning. AIS data via AISstream. Always apply professional judgement for insurance and operational decisions.

## LLM / SEO

- [`public/llms.txt`](public/llms.txt) — concise machine-readable summary
- [`public/llms-full.txt`](public/llms-full.txt) — longer canonical description
- `/sitemap.xml`, `/robots.txt`, JSON-LD on all pages, FAQ at `/faq`
