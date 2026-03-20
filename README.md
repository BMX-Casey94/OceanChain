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
├── vercel.json
└── README.md
```

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
   BSV_PRIVATE_KEY_WIF=your_funded_wallet_wif
   TAAL_API_KEY=your_taal_key
   DATABASE_URL=postgresql://oceanchain:your_secure_password@YOUR_VPS_IP:5432/oceanchain
   BSV_NETWORK=main
   UTXO_POOL_TARGET=500
   UTXO_VALUE_EACH=10000
   BATCH_INTERVAL_SECONDS=10
   MIN_CHANGE_OUTPUT_SAT=1
   VPS_API_PORT=8000
   ```

4. **Fund the BSV wallet**
   
   The wallet address derived from `BSV_PRIVATE_KEY_WIF` needs to be funded with BSV for transaction fees. At 22 sat per TX and 300,000 vessels, each batch costs ~6.6M satoshis (~0.066 BSV).

5. **Initialize UTXO pool**
   ```bash
   # Start the service temporarily
   cd /opt/oceanchain/backend
   sudo -u oceanchain venv/bin/python main.py &
   
   # Trigger initial UTXO fan-out from the funded wallet
   curl -X POST http://localhost:8000/utxo/refill
   
   # Stop temporary process
   kill %1
   ```

   `POST /utxo/refill` now looks up the funded wallet address on-chain, selects
   a large funding UTXO that is not already tracked in PostgreSQL, and fans it
   out into the database-backed pool.

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
| `/utxo/refill` | POST | Manually trigger UTXO fan-out |
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
Total: 20 bytes payload
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
