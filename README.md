# OceanChain

**BSV Maritime Intelligence** — Permanent blockchain records of global vessel tracking data.

OceanChain ingests real-time global maritime vessel position data via the AISstream.io WebSocket API and permanently records each vessel position as an OP_RETURN transaction on the BSV blockchain.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OceanChain Architecture                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐     ┌─────────────────────────────────────────────────┐   │
│   │             │     │              Python Backend (VPS)               │   │
│   │ AISstream.io│────▶│  ┌─────────────┐  ┌──────────────────────────┐  │   │
│   │  WebSocket  │     │  │ AIS Client  │  │     Broadcasting Loop    │  │   │
│   │             │     │  │ (ais_client)│─▶│  ┌────────┐ ┌─────────┐  │  │   │
│   └─────────────┘     │  └─────────────┘  │  │TX Build│ │Broadcast│  │  │   │
│                       │                   │  └────────┘ └────┬────┘  │  │   │
│                       │  ┌─────────────┐  │                  │       │  │   │
│                       │  │ PostgreSQL  │◀─┤  ┌───────────────▼────┐  │  │   │
│                       │  │ UTXO Pool   │  │  │ GorillaPool ARC    │  │  │   │
│                       │  └─────────────┘  │  │ (TAAL fallback)    │  │  │   │
│                       │                   │  └───────────────┬────┘  │  │   │
│                       │  ┌─────────────┐  └──────────────────┼──────┘  │   │
│                       │  │ FastAPI     │                     │         │   │
│                       │  │ HTTP + WS   │                     │         │   │
│                       │  └─────────────┘                     │         │   │
│                       └──────────────────────────────────────┼─────────┘   │
│                                                              │             │
│   ┌─────────────┐                              ┌─────────────▼───────────┐ │
│   │ Next.js     │                              │     BSV Blockchain      │ │
│   │ Landing Page│                              │  (OP_RETURN Records)    │ │
│   │ (Vercel)    │                              │                         │ │
│   └─────────────┘                              └─────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Features

- **Real-time Ingestion**: Continuous WebSocket connection to AISstream.io for global vessel positions
- **Efficient Encoding**: 20-byte compact payload per vessel position
- **Low Cost**: ~22 satoshis (~$0.000013 USD) per permanent record
- **High Throughput**: UTXO fan-out pool for parallel transaction broadcasting
- **Fault Tolerant**: GorillaPool ARC primary with automatic TAAL fallback
- **Publicly Verifiable**: All records on BSV blockchain, viewable on any explorer

## Project Structure

```
oceanchain/
├── app/                    # Next.js frontend (landing page)
│   ├── layout.tsx
│   ├── page.tsx
│   └── globals.css
├── components/             # React components
│   ├── navigation.tsx
│   ├── hero.tsx
│   ├── ticker.tsx
│   ├── how-it-works.tsx
│   ├── architecture.tsx
│   ├── stats.tsx
│   ├── open-source-cta.tsx
│   └── footer.tsx
├── backend/                # Python broadcasting engine
│   ├── main.py             # Asyncio orchestrator
│   ├── ais_client.py       # AISstream WebSocket client
│   ├── tx_builder.py       # BSV transaction construction
│   ├── utxo_manager.py     # PostgreSQL UTXO pool
│   ├── broadcaster.py      # ARC submission with fallback
│   ├── api_server.py       # FastAPI HTTP + WebSocket
│   ├── config.py           # Configuration loading
│   ├── requirements.txt
│   ├── .env.example
│   └── systemd/
│       └── oceanchain.service
├── docs/                   # Architecture & rollout references
│   └── AIS_MESSAGE_EXPANSION_PLAN.md
├── vercel.json
└── README.md
```

### Further documentation

- **[AIS message expansion plan](docs/AIS_MESSAGE_EXPANSION_PLAN.md)** — Phased rollout for extra AISStream message types (Class B, SAR, static data, AtoN, safety), throughput guardrails, and monitoring checklist. Use this to add features **incrementally** and avoid unsustainable on-chain TPS.

---

## Frontend Deployment (Vercel)

### Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SITE_URL` | Your production domain URL |

### Deployment Steps

1. **Deploy to Vercel**
   - Go to [vercel.com](https://vercel.com)
   - Import your repository
   - Vercel will auto-detect Next.js settings
   - Add environment variables in project settings
   - Deploy

---

## Backend Deployment (Linux VPS)

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- systemd (for service management)
- Funded BSV wallet

### Installation

1. **Setup and installation**
   ```bash
   # Create service user
   sudo useradd -r -s /bin/false oceanchain
   
   # Prepare deployment directory
   sudo mkdir -p /opt/oceanchain
   sudo chown -R oceanchain:oceanchain /opt/oceanchain
   
   # Copy application files to /opt/oceanchain
   # Install Python dependencies
   cd /opt/oceanchain/backend
   sudo -u oceanchain python3 -m venv venv
   sudo -u oceanchain venv/bin/pip install -r requirements.txt
   ```

2. **Setup PostgreSQL**
   ```bash
   # Create database
   sudo -u postgres createuser oceanchain
   sudo -u postgres createdb oceanchain -O oceanchain
   sudo -u postgres psql -c "ALTER USER oceanchain WITH PASSWORD 'your_secure_password';"
   ```

3. **Configure environment**
   ```bash
   cd /opt/oceanchain/backend
   sudo -u oceanchain cp .env.example .env
   sudo -u oceanchain nano .env
   ```

   Edit `.env` with your values:
   ```env
   AISSTREAM_API_KEY=your_aisstream_key
   # Optional Phase 1: AISSTREAM_FILTER_MESSAGE_TYPES=PositionReport,StandardClassBPositionReport,ExtendedClassBPositionReport,LongRangeAisBroadcastMessage
   BSV_PRIVATE_KEY_WIF=your_funded_wallet_wif
   TAAL_API_KEY=your_taal_key
   DATABASE_URL=postgresql://oceanchain:your_secure_password@YOUR_VPS_IP:5432/oceanchain
   BSV_NETWORK=main
   UTXO_POOL_TARGET=800
   UTXO_VALUE_EACH=3000
   BATCH_INTERVAL_SECONDS=10
   MIN_CHANGE_OUTPUT_SAT=1
   VPS_API_PORT=8000
   ```

4. **Fund the BSV wallet**
   
   The wallet address derived from `BSV_PRIVATE_KEY_WIF` must cover the **fan-out** (roughly `UTXO_POOL_TARGET × UTXO_VALUE_EACH` plus fan-out fees) and ongoing per-vessel fees (see `FEE_RATE_SAT_PER_KB`). Smaller `UTXO_VALUE_EACH` (e.g. 2000–5000 sat) is usually enough for each AIS broadcast; increase if you use large JSON OP_RETURN payloads.

   **Internal UTXO tracking:** Vessel spends use only **`pool`** rows. Fan-out consumes **`reserve`** rows you track in Postgres (not live WOC lookups on every spend). For **many** unspents (e.g. thousands), set **`OCEANCHAIN_ADMIN_API_KEY`** and call **`POST /utxo/sync-reserves-woc`** with header **`X-OceanChain-Admin-Key`** once — it imports the current **unspent** list from WhatsOnChain (lighter than full tx history). Alternatively register outputs one-by-one with **`POST /utxo/reserve`**, or **consolidate** by sending yourself one payment to this address so a single `txid`/`vout` is easy to copy from any explorer withdrawal history.

5. **Initialize UTXO pool**
   ```bash
   # Start the service temporarily
   cd /opt/oceanchain/backend
   sudo -u oceanchain venv/bin/python main.py &
   
   # Register confirmed funding output(s) for fan-out (repeat per UTXO you control)
   curl -X POST http://localhost:8000/utxo/reserve \
     -H "Content-Type: application/json" \
     -d '{"txid":"<64-char_hex>","vout":0,"value_sat":50000000}'
   
   # Trigger fan-out from internal reserve rows into the pool (+ change back to reserve)
   curl -X POST http://localhost:8000/utxo/refill
   
   # Stop temporary process
   kill %1
   ```

   `POST /utxo/refill` spends **unlocked `reserve`** rows from PostgreSQL, builds and broadcasts the fan-out via ARC, then atomically updates the database: spent reserves removed, new **`pool`** outputs inserted, and any change output recorded as **`reserve`** again.

   **Bulk reserve import (busy wallets / no indexer):** with the service running, after setting **`OCEANCHAIN_ADMIN_API_KEY`** in `.env` and restarting, either:

   - **`POST /utxo/sync-reserves-woc`** (WhatsOnChain unspent only — often **fails** if the address has a massive tx count), or
   - **`POST /utxo/reserves/bulk-import`** with JSON **`{"utxos":[{"txid":"…64 hex…","vout":0,"value_sat":123456}]}`** — no WhatsOnChain; data from your node, a consolidation tx you sent yourself, or any trusted export.

   ```bash
   curl -sS -X POST http://127.0.0.1:8000/utxo/reserves/bulk-import \
     -H "Content-Type: application/json" \
     -H "X-OceanChain-Admin-Key: YOUR_KEY_HERE" \
     -d '{"utxos":[{"txid":"abcd…64 chars…","vout":0,"value_sat":90000000}]}'
   ```

   Then **`POST /utxo/refill`** as above. Restrict port **8000** (firewall / localhost + SSH tunnel) so admin routes are not exposed without TLS.

6. **Install systemd service**
   ```bash
   sudo cp /opt/oceanchain/backend/systemd/oceanchain.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable oceanchain
   sudo systemctl start oceanchain
   
   # Check status
   sudo systemctl status oceanchain
   sudo journalctl -u oceanchain -f
   ```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with spendable pool depth, pool balance and uptime |
| `/stats/summary` | GET | Current aggregate statistics |
| `/stats/timeseries` | GET | TX counts per minute (last 60 min) |
| `/engine/pause` | POST | Pause broadcasting loop |
| `/engine/resume` | POST | Resume broadcasting loop |
| `/utxo/reserve` | POST | Register a confirmed funding UTXO (`reserve`) for internal fan-out |
| `/utxo/sync-reserves-woc` | POST | Bulk `reserve` import from WhatsOnChain unspent (admin key; may fail on huge wallets) |
| `/utxo/reserves/bulk-import` | POST | Bulk `reserve` import from JSON body — **no WhatsOnChain** (admin key) |
| `/utxo/refill` | POST | Fan-out from internal `reserve` rows into the `pool` |
| `/ws` | WebSocket | Real-time TX, stats and UTXO pool events on the same `VPS_API_PORT` |

---

## ARC Endpoints

| Provider | URL | Documentation |
|----------|-----|---------------|
| GorillaPool | https://arc.gorillapool.io | [docs.gorillapool.io](https://docs.gorillapool.io) |
| TAAL | https://arc.taal.com | [docs.taal.com](https://docs.taal.com) |

## Verifying Transactions

All OceanChain transactions can be verified on WhatsOnChain:

```
https://whatsonchain.com/tx/{txid}
```

The OP_RETURN output contains:
- Protocol prefix: `OCEANCHAIN`
- 20-byte payload with MMSI, coordinates, speed, heading, timestamp

---

## OP_RETURN Payload Structure

```
OP_RETURN <OCEANCHAIN>

[bytes 0–3  ]  MMSI         uint32  vessel identifier
[bytes 4–7  ]  Latitude     int32   degrees × 600,000
[bytes 8–11 ]  Longitude    int32   degrees × 600,000
[bytes 12–13]  Speed        uint16  knots × 10
[bytes 14–15]  Heading      uint16  degrees (0xFFFF = N/A)
[bytes 16–19]  Timestamp    uint32  unix seconds
─────────────────────────────────────────────────────
Total: 20 bytes payload (binary mode), or UTF-8 JSON if `OP_RETURN_ENCODING=json` in `backend/.env`.
The hex you see after `OCEANCHAIN` in explorers is **not broken**: it is MMSI, lat/lon (×600000), speed (×10), heading, and Unix time packed for minimal size. Decode with `tx_builder.decode_op_return_payload` or set `OP_RETURN_ENCODING=json` for human-readable second push (larger transaction / slightly higher fee).
Fee:   ceil(serialized_tx_bytes / 1000 × `FEE_RATE_SAT_PER_KB`); default rate 102.5 sat/KB. The builder measures the signed tx and converges so fees match the real size (not a lowball estimate).
Cost:  Depends on BSV spot price and tx size; if an endpoint still returns HTTP 465, its minimum policy may exceed your chosen rate.
```

---

---

## Resources

- [AISstream.io](https://aisstream.io) — Real-time AIS data provider
- [GorillaPool](https://gorillapool.io) — BSV mining pool and ARC provider
- [TAAL](https://taal.com) — BSV infrastructure provider
- [WhatsOnChain](https://whatsonchain.com) — BSV block explorer
