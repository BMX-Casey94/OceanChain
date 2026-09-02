# Arcade and Teranode Notes

## Current Ocechain behaviour

- Ocechain submits JSON `{"rawTx":"..."}` to ARC-compatible endpoints.
- Payload format can now be switched for GorillaPool with `GORILLA_TX_FORMAT`:
  - `raw` (default): standard signed tx hex,
  - `ef`: BIP-239 Transaction Extended Format (TEF) hex in `rawTx`,
  - `auto`: prefer EF when context is available, else raw.
- TAAL submissions remain standard raw tx hex for now.
- The client polls `GET /tx/{txid}` and counts success once ARC reaches `ARC_WAIT_FOR_STATUS` (default `ACCEPTED_BY_NETWORK` — mempool acceptance, *not* a propagation guarantee). Separately, the pending-coin reaper gates change reuse on `PENDING_PROMOTE_STATUS` (default `SEEN_ON_NETWORK`).
- Vessel broadcasts use many parallel `POST /tx` calls.
- Fan-out refills use the same broadcaster path, but far less frequently.

## What the current evidence suggests

### `txStatus=RECEIVED` is not a broadcast guarantee

- `RECEIVED` means Arcade accepted the submission locally.
- It does **not** guarantee network propagation.
- If GorillaPool still reports `RECEIVED` and WhatsOnChain is still `404`, the transaction has not reached the wider network.

### GorillaPool HTTP `467`

- Client-side responses only show a generic error, for example:
  - `{"title":"Generic error","status":467,"detail":"Transaction could not be processed"}`
- Based on GorillaPool's server-side notes, this appears to come from validator-side verification failure rather than a transport-level rate-limit error.
- One concrete validator-side error already observed is:
  - `'PreviousTx' not supplied`
- That strongly suggests some raw transaction submissions need parent transaction context that plain `rawTx` submission does not provide.

### TAAL `460` / extended-format failures

- TAAL errors such as "Missing input scripts" / "parent transaction not found" point in the same direction:
  - the broadcaster can see the submitted transaction,
  - but it cannot derive enough parent-input context to validate or transform it.

### Raw tx vs EF / BEEF

- Ocechain can now submit EF for GorillaPool (`GORILLA_TX_FORMAT=ef|auto`), while retaining raw fallback behaviour.
- For chained spends, unconfirmed parents, or validator setups that do not already know the parent transaction, raw-only submission may be insufficient.
- That is currently the clearest explanation for:
  - GorillaPool `467`,
  - GorillaPool transactions stuck at `RECEIVED`,
  - TAAL extended-format / parent-lookup failures.

## EF results (2026-03-29)

### What EF resolved

- Zero `467` validator errors (previously 100% of Gorilla submissions).
- Zero `RECEIVED` timeouts (previously 100% of Gorilla submissions).
- GorillaPool now returns `ACCEPTED_BY_NETWORK` for a portion of EF submissions — this never happened with raw tx.

### Remaining `REJECTED` under load

- With EF enabled at ~50 tx/sec sustained (250 concurrent connections), ~70-80% of Gorilla submissions return `txStatus=REJECTED` with HTTP 200.
- Every rejection carries the identical detail:
  ```
  unexpected status code 500: Failed to process transaction: PROCESSING (4):
  [ProcessTransaction][txid] failed to validate transaction
  ```
- The rejection rate oscillates in ~20-30 second waves (45% to 98%), consistent with backend queue saturation.
- The same EF format is accepted for some txs and rejected for others within the same second — no format difference.
- Rejected txids remain permanently `REJECTED` in Arcade's `GET /tx/{txid}` status endpoint.
- Average submission latency: ~365ms (range 100ms–1s).

### Interpretation

- The `status code 500` and `PROCESSING (4)` indicate Arcade's Teranode submission pipeline is returning an internal server error during transaction processing, not a client format problem.
- David (Arcade lead) confirmed Arcade was not designed as high-load infrastructure for service providers, and that direct Teranode broadcast for high-scale use is being explored.
- The SQLite single-writer lock in Arcade serialises all DB writes; at ~50 tx/sec this likely contributes to the processing failures.

### Client-side mitigations applied

- **Skip Gorilla retry on terminal rejection**: when Gorilla returns `REJECTED` or `DOUBLE_SPEND_ATTEMPTED`, the client no longer wastes a 2-second retry to the same endpoint. It falls through to TAAL immediately.
- **Consume UTXO on submitted-but-failed broadcast**: if a tx was actually submitted to at least one ARC endpoint but all endpoints ultimately failed, the UTXO is consumed (burned) rather than released back to the pool. This prevents double-spend cascades where a released UTXO gets re-spent in a later batch while the original tx is still propagating.
- **Pending-change gate (orphan-chain fix)**: change outputs and fan-out outputs now enter the pool as `pending` and are never handed out for spending until the creating tx reaches `PENDING_PROMOTE_STATUS` (default `SEEN_ON_NETWORK`). A background reaper polls ARC off the hot path and promotes or quarantines pending rows. This eliminates the observed failure mode where a parent accepted at `ACCEPTED_BY_NETWORK` never propagated (`PENDING_RETRY`, explorer 404) and every descendant built on its change was silently invalidated. Quarantine is always safe because pending rows are never spent, so no descendants can exist. Pool sizing must cover the in-flight window (`tx_rate × promotion_lag`); see `UTXO_POOL_TARGET` guidance in `backend/.env.example`.
- **Dual broadcast + promotion quorum (propagation fix)**: a single operator's `SEEN_ON_NETWORK` proved unreliable — Arcade reported txs as network-visible while WhatsOnChain/Bitails returned 404. With `ARC_DUAL_BROADCAST=1` (default when `TAAL_API_KEY` is set) every tx is POSTed to GorillaPool *and* TAAL, so two independent miners/relays inject it into their mempools. The TAAL POST is **fire-and-forget**: it runs as a bounded background task (20s budget, 256 in-flight cap) the hot path never awaits, because TAAL's parent-aware validation of zero-conf chains regularly exceeds 5s and awaiting it taxed every tx with a ~5s floor for little acceptance. When a background POST lands, `mark_taal_accepted` flips the TAAL `submit_mask` bit on the tx's pending rows (an in-memory set covers the accept-before-insert race), so the reaper's quorum tightens retroactively; TAAL is awaited synchronously only when GorillaPool has failed and it is the safety net. Each pending row records a `submit_mask` of the endpoints that accepted the tx, and with `PENDING_PROMOTE_QUORUM=2` (default) the reaper only promotes once *every* accepting endpoint reports `PENDING_PROMOTE_STATUS` — a tx both miners hold will be mined and indexed, so phantom change can no longer enter circulation. A tx TAAL refused at POST time (e.g. 460 on a chain whose parent has not reached TAAL yet) degrades to GorillaPool-only tracking rather than stalling. Explorer APIs (WoC 3 RPS, Bitails ~8 RPS) are deliberately kept out of the hot path; ARC status endpoints are built for this poll rate. The only stronger signal is running our own BSV node (Teranode/SV Node with ZMQ mempool events) — ground truth, but an infrastructure project, not a config change.

## `POST /tx` vs `POST /txs`

- `POST /txs` is **not** currently a throughput fix for Ocechain.
- Based on the Arcade notes shared during debugging:
  - `/txs` still validates and writes each transaction individually,
  - transactions are processed sequentially inside the batch,
  - one failure can abort the batch,
  - a shared timeout can starve later transactions.
- For the current Arcade implementation, parallel `POST /tx` calls remain the better fit for high-throughput broadcasting.

## Why Ocechain "suddenly stops"

### Dust exhaustion

- Each successful vessel tx consumes one pool UTXO and adds its change back into the pool.
- If `UTXO_VALUE_EACH` is too small, repeated chaining steadily decays every coin into dust.
- Example at roughly `34 sat` fee per tx:
  - `200 -> 166 -> 132 -> 98 -> 64 -> 30`
- With a current minimum viable value of about `55 sat`, a `30 sat` output is dead dust.
- This creates a cliff-edge failure mode:
  - the service looks healthy,
  - AIS ingest keeps rising,
  - but `pool_depth` suddenly drops to `0` because all remaining rows are too small to spend.

### Reserve fragmentation

- If the reserve set is mostly tiny outputs, fan-out refills become huge multi-input transactions.
- Example seen in production:
  - `2268` fan-out inputs,
  - about `197,213 sat` total input value,
  - roughly `37,199 sat` fee,
  - approximately `363 KB` transaction size.
- That is operationally poor even before network propagation issues are considered.

## Practical operating guidance

- Prefer `UTXO_VALUE_EACH >= 1000` for sustained chaining.
- `UTXO_VALUE_EACH=3000` remains the safer baseline in this project unless you have confirmed a better production profile.
- Keep `RESERVE_MIN_IMPORT_SAT` and Bitails `--min-sat` / `BITAILS_IMPORT_MIN_SAT` high enough to avoid importing 40-50 sat dust into `reserve`.
- Treat `ARC_MAX_TIMEOUT_SECONDS=1` as a diagnostic setting, not a production default.
- Enable Gorilla EF explicitly during validation runs: `GORILLA_TX_FORMAT=ef`.
- Avoid giant refill fan-outs; larger reserve UTXOs are more important than a huge count of tiny ones.
- All outbound HTTP (ARC submits/polls, reaper checks, WoC sync) shares one process-wide keep-alive `httpx` client (`backend/http_client.py`). Per-request clients previously caused hundreds of fresh TLS handshakes per second — observed as `ConnectTimeout` floods against Cloudflare-fronted TAAL and 5-10s GorillaPool POST latencies under load. Never construct `httpx.AsyncClient()` in a hot path.

## Immediate VPS recovery playbook

### 1. Confirm the current operating envelope

```bash
cd /opt/oceanchain/backend
grep -E '^(UTXO_POOL_TARGET|UTXO_VALUE_EACH|RESERVE_MIN_IMPORT_SAT|ARC_MAX_TIMEOUT_SECONDS|GORILLA_TX_FORMAT|FANOUT_MAX_INPUTS|OCEANCHAIN_FUNDING_ADDRESS)=' .env
```

### 2. Inspect the largest current wallet unspents from Bitails

```bash
cd /opt/oceanchain/backend
set -a && source .env && set +a
python scripts/list_largest_bitails_unspents.py --address "$OCEANCHAIN_FUNDING_ADDRESS" --top 30 --min-sat 1000
```

### 3. Import only usable reserve UTXOs

```bash
cd /opt/oceanchain/backend
set -a && source .env && set +a
python scripts/import_reserves_bitails.py --address "$OCEANCHAIN_FUNDING_ADDRESS" --min-sat 1000
```

### 4. Trigger one refill and verify

```bash
curl -sS -X POST http://127.0.0.1:8000/utxo/refill
curl -sS http://127.0.0.1:8000/health | python -m json.tool
journalctl -u oceanchain --since "10 min ago" --no-pager | grep -Ei 'refill|fan-out|ARC response via|ARC status via|GorillaPool attempt|TAAL fallback|Summary'
```

### 5. If refill still fails

- Import one or more larger reserve outputs manually with `POST /utxo/reserve`, or fund the wallet with a fresh larger UTXO.
- Raise `UTXO_VALUE_EACH` back to a safer production value before rebuilding the pool.
- Do not rely on `RECEIVED` alone; confirm using `GET /tx/{txid}` plus an external explorer.

## References

- GorillaPool / Arcade operational notes shared during Ocechain debugging.
- ARC API docs / OpenAPI: [bitcoin-sv.github.io/arc/api.html](https://bitcoin-sv.github.io/arc/api.html)
- BIP-239 (Transaction Extended Format): [github.com/bitcoin-sv/arc/blob/main/doc/BIP-239.md](https://github.com/bitcoin-sv/arc/blob/main/doc/BIP-239.md)
- Arcade project issue discussing current storage / infra limitations: [Feature: PostGres #30](https://github.com/bsv-blockchain/arcade/issues/30)
