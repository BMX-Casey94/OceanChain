# AIS message expansion — phased plan & reference

This document is the **single reference** for extending OceanChain beyond **`PositionReport`** only. Use it to add capabilities **one phase at a time**, measure impact, and avoid jumping straight to unsustainable on-chain throughput (and cost).

**Official AISStream reference:** [AIS Stream API Reference](https://aisstream.io/documentation)  
**Message models (OpenAPI / languages):** [aisstream/ais-message-models](https://github.com/aisstream/ais-message-models)

---

## 1. Principles (do not skip)

1. **Ingest ≠ anchor** — Subscribing to more AIS types increases **WebSocket volume** immediately. **On-chain** volume should follow **explicit policy** (throttle, dedupe, “on change only”, caps).
2. **No target of ~300 tx/s** unless deliberately funded and architected for it — AISStream notes world-scale streams can require processing on the order of **~300 messages/s**; that is **ingress**, not a recommended **broadcast** rate. Fees × sustained TPS × years dominates lifetime cost.
3. **One WebSocket** — All subscribed types arrive on the **same** connection; discriminate with `MessageType` and parse `Message.<TypeKey>`.
4. **Entity identity** — Ships use **MMSI**; aids-to-navigation, base stations, and SAR aircraft use **UserID** in the same numeric space but **different semantics**. Plan a clear **`entity_kind`** (or equivalent) in your internal model and any on-chain encoding so records are not misinterpreted.
5. **Untrusted content** — Especially **safety** and **text** fields: treat as **data**, cap length, never interpret as instructions inside privileged code paths.

---

## 2. Current behaviour (baseline)

| Item | Today |
|------|--------|
| Subscription | `FilterMessageTypes: ["PositionReport"]`, global bounding box |
| Client | `backend/ais_client.py` — ignores non–`PositionReport` |
| Snapshot | `dict[MMSI → position]` — one row per MMSI, overwritten on update |
| Broadcast loop | Processes **full snapshot** each batch (`backend/main.py`) |

**Throughput monitoring already available (no code required for basics):**

- `GET /health` — pool depth, reserves, `uptime_seconds`
- `GET /stats/summary` — cumulative `txs_today`, `bsv_spent_today`, `avg_fee_sat`, `active_vessels`
- `GET /stats/timeseries` — per-minute `tx_count` (last 60 minutes)

After each phase, record **before/after**: AIS message rate (if you add metrics), **ws CPU**, **`tx_count`/minute**, **`bsv_spent_today` growth**, and **ARC errors**.

---

## 3. AISStream message types — quick map

Use exact strings in `FilterMessageTypes` as per AISStream docs. Common groups:

### Position-class (vessel / aircraft tracks)

| Type | Notes |
|------|--------|
| `PositionReport` | **Current default** — Class A–style positions |
| `StandardClassBPositionReport` | Smaller craft (Class B) |
| `ExtendedClassBPositionReport` | Class B with extra fields |
| `LongRangeAisBroadcastMessage` | Coarser, lower-rate positions (e.g. long-range context) |
| `StandardSearchAndRescueAircraftReport` | SAR aircraft position/status |

**Class B vs current:** Many vessels only appear on Class B reports; expect **overlap** with `PositionReport` for some MMSIs — **merge by MMSI** with freshness / precedence rules.

**Long-range:** Less precision; useful for **coverage** when full reports are absent, not for sub-100 m accuracy.

### Static / metadata (usually low change rate)

| Type | Notes |
|------|--------|
| `ShipStaticData` | Name, dimensions, type, destination, etc. |
| `StaticDataReport` | Static data in another AIS packaging |

**Typical pattern:** Maintain **side state** keyed by MMSI; merge into position payloads **or** emit **infrequent** on-chain updates when fields change.

### Fixed infrastructure & safety

| Type | Notes |
|------|--------|
| `BaseStationReport` | Fixed stations — not ships |
| `AidsToNavigationReport` | Buoys, lights — distinct semantics from vessels |
| `SafetyBroadcastMessage` | Broadcast safety text |
| `AddressedSafetyMessage` | Addressed safety text |

**Safety:** High operational value; **highest abuse/PII/size risk** — policy and **rate limits** before wide on-chain use.

### Other (lower priority for first iterations)

Examples from AISStream docs: `UnknownMessage`, `Interrogation`, `BinaryAcknowledge`, `ChannelManagement`, `AssignedModeCommand`, `MultiSlotBinaryMessage`, `SingleSlotBinaryMessage`, `GnssBroadcastBinaryMessage`, `DataLinkManagementMessage`, `AddressedBinaryMessage`, `CoordinatedUTCInquiry`, `BinaryBroadcastMessage`, `GroupAssignmentCommand`, etc. Add only when there is a **clear product / chain** requirement.

---

## 4. Suggested phases (add one at a time)

Complete **monitoring** and **cost review** after each phase before starting the next.

### Phase 0 — Baseline (done)

- `PositionReport` only; document **typical** `/stats/timeseries` and fee spend over 24–48 h at your current settings.

### Phase 1 — Extra position-class types (largest “more tracks” win) — **implemented**

**Subscribe (example):**  
`PositionReport`, `StandardClassBPositionReport`, `ExtendedClassBPositionReport`, `LongRangeAisBroadcastMessage`

**Configuration:** `AISSTREAM_FILTER_MESSAGE_TYPES` in `backend/.env` (comma-separated, no duplicates). Default: **`PositionReport` only** (same ingress as before). Add the other three types when you want Phase 1 (see `.env.example`).

**Implemented (`ais_client.py`, `config.py`):**

- Parsers normalise each type into the same position dict used for OP_RETURN.
- Snapshot **merges by MMSI**: newer metadata timestamp wins; on a tie, **higher-detail** type wins (`PositionReport` > `ExtendedClassB` > `StandardClassB` > `LongRange`).
- Internal `_ais_message_type` is stripped before encoding (`tx_builder` removes `_`-prefixed keys).

**Risk:** Higher **WebSocket / CPU** load when extra types are enabled; **on-chain tx rate** for a given MMSI set is unchanged (still one snapshot row per MMSI).

### Phase 2 — Static data merged with vessels

**Subscribe:** `ShipStaticData`, optionally `StaticDataReport`

**Work items:**

- Store **MMSI → static** in memory or DB; TTL or “last updated” for staleness.
- **On-chain options:** (a) enrich existing position payload when space allows, (b) separate **metadata tx** only when name/destination/dimensions **change**, (c) off-chain index with rare on-chain commitment — choose explicitly.

**Risk:** Larger OP_RETURNs → **higher fees** per tx if you pack full strings.

### Phase 3 — SAR, AtoN, base stations

**Subscribe:** `StandardSearchAndRescueAircraftReport`, `AidsToNavigationReport`, `BaseStationReport`

**Work items:**

- **Separate `entity_kind`** in model and on-chain discriminator (`VESSEL` / `SAR_AIRCRAFT` / `ATON` / `BASE_STATION`).
- **Throttle** SAR/AtoN/base-station **broadcasts** (time + distance + importance); do not mirror AIS rate 1:1 unless budgeted.

### Phase 4 — Safety messages

**Subscribe:** `SafetyBroadcastMessage`, optionally `AddressedSafetyMessage`

**Work items:**

- **Max length**, **sanitisation**, **rate limits**; consider **hash + short reference** vs full text on-chain.
- Legal/compliance review if you store or display text.

---

## 5. On-chain payload strategy (reference)

**Recommended direction:** one **versioned** envelope with:

- `record_type` (or version + type byte)
- `entity_kind` + identifier
- `timestamp`
- type-specific fields (compact binary where possible)

Avoid **one new transaction per raw AIS frame** for high-rate types unless you have explicit economic justification.

---

## 6. Throughput & cost guardrails

| Guardrail | Intent |
|-----------|--------|
| Target max **tx/s** (env or config) | Hard ceiling for broadcasts independent of AIS ingress |
| Min interval per **entity** | e.g. no more than one chain tx per MMSI per *N* seconds unless delta exceeds threshold |
| Min **distance / heading** delta | Skip redundant anchors |
| **Batch** metadata | Static/safety as periodic or on-change batches |
| **Pool + reserves** | Ensure UTXO pool and refill logic match **chosen** max TPS (`/health`, monitor logs) |
| **ARC / fee alerts** | Track failure rate and `avg_fee_sat` drift as payload size grows |

AISStream also notes: if the server’s **TCP queue** grows too large, the connection may be closed — **subscribe narrowly** until the process proves it can keep up.

---

## 7. Monitoring checklist (per phase)

After enabling a phase:

- [ ] `/stats/timeseries` — minute buckets stable or intentionally capped?
- [ ] `/stats/summary` — `bsv_spent_today` vs txs — fee per tx acceptable?
- [ ] `/health` — `pool_depth` not chronically zero; refills succeeding
- [ ] Server: CPU, RAM, network; WebSocket disconnect rate in logs
- [ ] Optional (future): Prometheus-style counters — **AIS messages in by type**, **tx out**, **drops by throttle**

---

## 8. Implementation tick-list (for PRs)

Use this as a PR template when coding each phase:

1. ~~`config` — `AISSTREAM_FILTER_MESSAGE_TYPES` (comma-separated)~~ **done**
2. ~~`ais_client.py` — dispatch on `MessageType`; normalised records; merge rules~~ **done (Phase 1)**
3. Snapshot / state model — `entity_kind`, optional static side table (later phases)
4. `tx_builder.py` — versioned / discriminated payload; size limits
5. `main.py` / broadcast policy — throttles and caps
6. Docs — update this file’s **phase status** (table below) and `.env.example`

### Phase status (maintainers: update as you ship)

| Phase | Status | Notes |
|-------|--------|--------|
| 0 Baseline | Live | Default env = `PositionReport` only |
| 1 Class B + long-range | **Code ready** | Enable via `AISSTREAM_FILTER_MESSAGE_TYPES` |
| 2 Static merge | Not started | |
| 3 SAR / AtoN / base | Not started | |
| 4 Safety | Not started | |

---

## 9. Related files in this repo

| File | Role |
|------|------|
| `backend/ais_client.py` | WebSocket subscription, Phase 1 multi-type parsing, MMSI merge |
| `backend/config.py` | Env loading, `AISSTREAM_FILTER_MESSAGE_TYPES`, validation |
| `backend/main.py` | Broadcasting loop, snapshot consumption |
| `backend/tx_builder.py` | OP_RETURN payload construction (strips `_` internal keys) |
| `backend/api_server.py` | `/health`, `/stats/*` |

---

*Last updated: reference created for incremental AIS expansion and throughput discipline.*
