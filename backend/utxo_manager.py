"""
OceanChain UTXO Manager Module

Manages the UTXO pool in PostgreSQL for high-throughput transaction broadcasting.
Handles acquisition, release, consumption, and automatic fan-out refills.
"""

import asyncio
import logging
import time
from typing import Any, Optional, Tuple

import asyncpg
import httpx

from config import (
    UTXO_POOL_TARGET,
    UTXO_VALUE_EACH,
    BSV_PRIVATE_KEY_WIF,
    BSV_NETWORK,
    GORILLA_TX_FORMAT,
    FANOUT_MAX_INPUTS,
    MIN_CHANGE_OUTPUT_SAT,
    REFILL_FAILURE_COOLDOWN_SECONDS,
    RESERVE_MIN_IMPORT_SAT,
    WHATSONCHAIN_BASE_URL,
)

# Vessel broadcasts only spend `pool` rows. Fan-out funding uses `reserve` rows tracked in Postgres
# (no WhatsOnChain listing — required for high-tx-count wallets).
UTXO_ROLE_POOL = "pool"
UTXO_ROLE_RESERVE = "reserve"

logger = logging.getLogger(__name__)


class UTXOManager:
    """
    Manages a pool of pre-warmed UTXOs in PostgreSQL for transaction throughput.

    The pool is maintained with a blend of depth and value checks so the engine
    does not mistake a pile of nearly-dust outputs for a healthy broadcast pool.
    """

    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized: bool = False
        self._refill_lock = asyncio.Lock()
        # time.monotonic() deadline; skip automatic fan-out retries until then after a failure
        self._refill_cooldown_until: float = 0.0
        self._last_refill_error: Optional[str] = None

    def last_refill_error(self) -> Optional[str]:
        """Most recent fan-out refill failure message, if any."""
        return self._last_refill_error

    async def initialize(self, pool: asyncpg.Pool) -> None:
        """
        Initialize the UTXO manager with a database connection pool.
        Creates the UTXOs table if it doesn't exist.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool

        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS utxos (
                    txid TEXT NOT NULL,
                    vout INTEGER NOT NULL,
                    value_sat BIGINT NOT NULL,
                    locked BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (txid, vout)
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_utxos_unlocked
                ON utxos (created_at ASC)
                WHERE locked = FALSE
            """)

            await conn.execute("""
                ALTER TABLE utxos ADD COLUMN IF NOT EXISTS utxo_role TEXT NOT NULL DEFAULT 'pool'
            """)
            try:
                await conn.execute("""
                    ALTER TABLE utxos ADD CONSTRAINT utxos_utxo_role_check
                    CHECK (utxo_role IN ('pool', 'reserve'))
                """)
            except asyncpg.DuplicateObjectError:
                pass

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_utxos_pool_acquire
                ON utxos (created_at ASC)
                WHERE locked = FALSE AND utxo_role = 'pool'
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_utxos_reserve_funding
                ON utxos (value_sat DESC)
                WHERE locked = FALSE AND utxo_role = 'reserve'
            """)
            await conn.execute("""
                ALTER TABLE utxos ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ
            """)

        self._initialized = True
        logger.info("UTXO manager initialized")

        # A previous crashed process can leave rows locked with no broadcast in flight.
        # Unlock anything locked longer than 2 minutes, plus pre-column leftovers.
        try:
            await self.sweep_stale_locks(older_than_seconds=120)
        except Exception as e:
            logger.warning("Could not sweep stale UTXO locks on startup: %s", e)

    async def acquire_utxo(self) -> Optional[dict[str, Any]]:
        """
        Atomically lock and return one viable UTXO from the pool.

        Uses FOR UPDATE SKIP LOCKED to prevent contention when
        multiple coroutines acquire UTXOs concurrently.

        Returns:
            Dict with txid, vout, value_sat or None if no viable UTXO is available
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        from tx_builder import minimum_viable_utxo_value

        minimum_value = minimum_viable_utxo_value()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE utxos SET locked = TRUE, locked_at = NOW()
                WHERE (txid, vout) = (
                    SELECT txid, vout FROM utxos
                    WHERE locked = FALSE AND utxo_role = 'pool' AND value_sat >= $1
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING txid, vout, value_sat
                """,
                minimum_value,
            )

            if row:
                return {
                    "txid": row["txid"],
                    "vout": row["vout"],
                    "value_sat": row["value_sat"],
                }

            return None

    async def release_utxo(self, txid: str, vout: int) -> None:
        """
        Release a locked UTXO back to the pool (on broadcast failure).

        Args:
            txid: Transaction ID
            vout: Output index
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE utxos SET locked = FALSE, locked_at = NULL "
                "WHERE txid = $1 AND vout = $2 AND utxo_role = 'pool'",
                txid,
                vout,
            )

        logger.debug(f"Released UTXO {txid}:{vout} back to pool")

    async def consume_utxo(self, txid: str, vout: int) -> None:
        """
        Remove a UTXO from the pool (after successful broadcast).

        Args:
            txid: Transaction ID
            vout: Output index
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM utxos WHERE txid = $1 AND vout = $2",
                txid, vout
            )

        logger.debug(f"Consumed UTXO {txid}:{vout}")

    async def sweep_stale_locks(self, older_than_seconds: int = 300) -> int:
        """
        Unlock pool rows that have been locked longer than the cutoff.

        A crashed or restarted process can leave rows locked even though no
        broadcast is in flight. Only call this when the engine is known to be
        idle (startup) or from the monitor loop with a generous cutoff.

        Returns:
            Number of rows unlocked.
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE utxos
                SET locked = FALSE, locked_at = NULL
                WHERE utxo_role = 'pool'
                  AND locked = TRUE
                  AND (
                    locked_at IS NULL
                    OR locked_at < NOW() - ($1 * INTERVAL '1 second')
                  )
                """,
                older_than_seconds,
            )

        # asyncpg returns e.g. "UPDATE 123"
        try:
            count = int(str(result).split()[-1])
        except (ValueError, IndexError):
            count = 0
        if count:
            logger.warning("Unlocked %s stale pool UTXO(s) older than %ss", count, older_than_seconds)
        return count

    async def add_utxo(
        self,
        txid: str,
        vout: int,
        value_sat: int,
        utxo_role: str = UTXO_ROLE_POOL,
    ) -> None:
        """
        Add a tracked UTXO. Default role `pool` (vessel spends). Use `reserve` for fan-out funding.

        Args:
            txid: Transaction ID (hex)
            vout: Output index
            value_sat: Value in satoshis
            utxo_role: `pool` or `reserve`
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")
        if utxo_role not in (UTXO_ROLE_POOL, UTXO_ROLE_RESERVE):
            raise ValueError(f"Invalid utxo_role: {utxo_role}")

        if utxo_role == UTXO_ROLE_POOL:
            from tx_builder import minimum_viable_utxo_value

            floor = minimum_viable_utxo_value()
            if value_sat < floor:
                logger.info(
                    "Not tracking dust change %s:%s (%s sat < %s sat floor)",
                    txid[:16],
                    vout,
                    value_sat,
                    floor,
                )
                return

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO utxos (txid, vout, value_sat, utxo_role, locked)
                VALUES ($1, $2, $3, $4, FALSE)
                ON CONFLICT (txid, vout) DO NOTHING
                """,
                txid,
                vout,
                value_sat,
                utxo_role,
            )

        logger.debug("Added UTXO %s:%s (%s sat) role=%s", txid, vout, value_sat, utxo_role)

    async def register_reserve_utxo(self, txid: str, vout: int, value_sat: int) -> None:
        """
        Register a wallet funding UTXO for internal fan-out (no WhatsOnChain).

        Returns True if a row was inserted or updated.
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")
        txid = txid.strip().lower()
        if len(txid) != 64 or any(c not in "0123456789abcdef" for c in txid):
            raise ValueError("txid must be 64 hex characters")
        if vout < 0 or value_sat < 1:
            raise ValueError("Invalid vout or value_sat")

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO utxos (txid, vout, value_sat, utxo_role, locked)
                VALUES ($1, $2, $3, 'reserve', FALSE)
                ON CONFLICT (txid, vout) DO UPDATE SET
                    value_sat = EXCLUDED.value_sat,
                    utxo_role = 'reserve',
                    locked = FALSE
                """,
                txid,
                vout,
                value_sat,
            )
        logger.info(
            "Registered reserve UTXO %s:%s (%s sat) for internal fan-out",
            txid[:16],
            vout,
            value_sat,
        )

    async def bulk_register_reserve_utxos(
        self,
        rows: list[tuple[str, int, int]],
    ) -> tuple[int, int]:
        """
        Upsert many `reserve` rows in one transaction (for indexer bootstrap).

        Each tuple is (txid_hex, vout, value_sat). Invalid txids are skipped.

        Returns:
            (upserted_row_count, skipped_below_reserve_min_count)
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        cleaned: list[tuple[str, int, int]] = []
        skipped_below_min = 0
        min_sat = RESERVE_MIN_IMPORT_SAT
        for txid, vout, value_sat in rows:
            t = txid.strip().lower()
            if len(t) != 64 or any(c not in "0123456789abcdef" for c in t):
                continue
            if vout < 0 or value_sat < 1:
                continue
            if min_sat > 0 and value_sat < min_sat:
                skipped_below_min += 1
                continue
            cleaned.append((t, vout, value_sat))

        if not cleaned:
            return 0, skipped_below_min

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO utxos (txid, vout, value_sat, utxo_role, locked)
                    VALUES ($1, $2, $3, 'reserve', FALSE)
                    ON CONFLICT (txid, vout) DO UPDATE SET
                        value_sat = EXCLUDED.value_sat,
                        utxo_role = 'reserve',
                        locked = FALSE
                    """,
                    cleaned,
                )

        if skipped_below_min:
            logger.info(
                "Bulk registered %s reserve UTXO row(s); skipped %s below RESERVE_MIN_IMPORT_SAT=%s",
                len(cleaned),
                skipped_below_min,
                min_sat,
            )
        else:
            logger.info("Bulk registered %s reserve UTXO row(s)", len(cleaned))
        return len(cleaned), skipped_below_min

    async def sync_reserves_from_whatsonchain(
        self,
        *,
        timeout_seconds: float = 300.0,
        max_utxos: int = 20000,
    ) -> dict[str, Any]:
        """
        Fetch current unspent outputs for this wallet's P2PKH from WhatsOnChain and
        upsert them as internal `reserve` rows.

        This uses the **address unspent** endpoint (UTXO set), not full transaction
        history — it often succeeds where paginated history would not.

        Fan-out still spends only rows you track; false positives (stale indexer
        data) fail safely at broadcast time.
        """
        from tx_builder import get_change_address

        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        address = get_change_address()
        net = "main" if BSV_NETWORK.lower() in ("main", "mainnet", "livenet") else "test"
        base = WHATSONCHAIN_BASE_URL.rstrip("/")
        url = f"{base}/{net}/address/{address}/unspent"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout_seconds)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, list):
            raise ValueError("WhatsOnChain unspent response was not a JSON array")

        parsed: list[tuple[str, int, int]] = []
        skipped_small = 0
        min_sat = RESERVE_MIN_IMPORT_SAT
        for item in payload:
            if not isinstance(item, dict):
                continue
            txid = item.get("tx_hash") or item.get("txid")
            pos = item.get("tx_pos")
            if pos is None:
                pos = item.get("vout")
            val = item.get("value")
            if txid is None or pos is None or val is None:
                continue
            try:
                v_int = int(val)
            except (TypeError, ValueError):
                continue
            if min_sat > 0 and v_int < min_sat:
                skipped_small += 1
                continue
            try:
                parsed.append((str(txid), int(pos), v_int))
            except (TypeError, ValueError):
                continue

        parsed.sort(key=lambda x: -x[2])
        if len(parsed) > max_utxos:
            logger.warning(
                "Capping WOC unspent import at %s of %s outputs",
                max_utxos,
                len(parsed),
            )
            parsed = parsed[:max_utxos]

        n_reg, skipped_bulk_min = await self.bulk_register_reserve_utxos(parsed)
        metrics = await self.reserve_funding_metrics()
        return {
            "status": "ok",
            "address": address,
            "woc_url": url,
            "fetched_unspent": len(payload),
            "skipped_below_reserve_min": skipped_small + skipped_bulk_min,
            "reserve_min_import_sat": min_sat,
            "parsed_valid": len(parsed),
            "upserted_rows": n_reg,
            "reserve_count": metrics["reserve_count"],
            "reserve_total_sat": metrics["reserve_total_sat"],
        }

    async def pool_metrics(self) -> dict[str, int]:
        """
        Return health metrics for the currently tracked pool.

        `spendable_*` metrics only count UTXOs that are large enough to build
        a valid OP_RETURN transaction without creating dust change.
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        from tx_builder import minimum_viable_utxo_value

        minimum_value = minimum_viable_utxo_value()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE locked = FALSE) AS unlocked_depth,
                    COALESCE(SUM(value_sat) FILTER (WHERE locked = FALSE), 0) AS unlocked_balance,
                    COUNT(*) FILTER (
                        WHERE locked = FALSE AND value_sat >= $1
                    ) AS spendable_depth,
                    COALESCE(SUM(value_sat) FILTER (
                        WHERE locked = FALSE AND value_sat >= $1
                    ), 0) AS spendable_balance
                FROM utxos
                WHERE utxo_role = 'pool'
                """,
                minimum_value,
            )

        return {
            "minimum_viable_utxo_value": minimum_value,
            "unlocked_depth": int(row["unlocked_depth"] or 0),
            "unlocked_balance": int(row["unlocked_balance"] or 0),
            "spendable_depth": int(row["spendable_depth"] or 0),
            "spendable_balance": int(row["spendable_balance"] or 0),
        }

    async def reserve_funding_metrics(self) -> dict[str, int]:
        """Internal `reserve` UTXOs available to fund fan-out (WhatsOnChain-free)."""
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE locked = FALSE) AS n,
                    COALESCE(SUM(value_sat) FILTER (WHERE locked = FALSE), 0) AS total_sat
                FROM utxos
                WHERE utxo_role = 'reserve'
                """
            )

        return {
            "reserve_count": int(row["n"] or 0),
            "reserve_total_sat": int(row["total_sat"] or 0),
        }

    async def pool_depth(self) -> int:
        """Return the count of unlocked, viable UTXOs in the pool."""
        metrics = await self.pool_metrics()
        return metrics["spendable_depth"]

    async def _collect_internal_reserve_candidates(self) -> list[dict[str, Any]]:
        """
        Funding UTXOs for fan-out: `reserve` role rows only (no external indexers).
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT txid, vout, value_sat
                FROM utxos
                WHERE utxo_role = 'reserve' AND locked = FALSE
                ORDER BY value_sat DESC
                """
            )

        return [
            {
                "txid": str(r["txid"]),
                "vout": int(r["vout"]),
                "value_sat": int(r["value_sat"]),
            }
            for r in rows
        ]

    def _pick_fanout_funding_inputs(
        self,
        candidates: list[dict[str, Any]],
        total_pool_output_sat: int,
    ) -> Optional[Tuple[list[dict[str, Any]], int, int, bool]]:
        """
        Greedily pick one or more wallet UTXOs until pool outputs + fee are covered.

        Returns:
            (selected_utxos, fee_sat, change_sat, add_change_output) or None.
        """
        from tx_builder import calculate_fee

        def est_vbytes(n_in: int, n_outputs: int) -> int:
            # Rough signed size: header + P2PKH inputs + P2PKH outputs
            return 10 + n_in * 148 + n_outputs * 34

        if not candidates:
            return None

        selected: list[dict[str, Any]] = []
        for utxo in candidates:
            selected.append(utxo)
            n_in = len(selected)
            sum_in = sum(u["value_sat"] for u in selected)

            # Prefer an explicit change output when above dust/min threshold
            fee_with_change = calculate_fee(est_vbytes(n_in, UTXO_POOL_TARGET + 1))
            change_w = sum_in - total_pool_output_sat - fee_with_change
            if change_w >= MIN_CHANGE_OUTPUT_SAT:
                return selected, fee_with_change, change_w, True

            fee_no_change = calculate_fee(est_vbytes(n_in, UTXO_POOL_TARGET))
            if sum_in >= total_pool_output_sat + fee_no_change:
                change_nc = sum_in - total_pool_output_sat - fee_no_change
                return selected, fee_no_change, change_nc, False

        return None

    async def fan_out_refill(self) -> Optional[str]:
        """
        Create a fan-out transaction to refill the UTXO pool.

        Constructs a single transaction with UTXO_POOL_TARGET outputs,
        each containing UTXO_VALUE_EACH satoshis. Broadcasts via ARC:
        GorillaPool Arcade first, then TAAL ARC if ``TAAL_API_KEY`` is set
        (same path as vessel txs).

        Returns:
            Transaction ID of the fan-out TX, or None on failure
        """
        from tx_builder import get_change_address, calculate_fee, to_extended_format_hex
        from broadcaster import submit, BroadcastError
        from bitcoinx import (
            PrivateKey,
            TxInput,
            TxOutput,
            Tx,
            Script,
            P2PKH_Address,
            Bitcoin,
            SigHash,
            pack_byte,
        )

        async with self._refill_lock:
            self._last_refill_error = None
            logger.info(f"Starting fan-out refill for {UTXO_POOL_TARGET} outputs")

            private_key = PrivateKey.from_WIF(BSV_PRIVATE_KEY_WIF)
            public_key = private_key.public_key
            address = get_change_address()
            p2pkh_script = P2PKH_Address.from_string(address, Bitcoin).to_script()

            total_output_value = UTXO_POOL_TARGET * UTXO_VALUE_EACH

            candidates = await self._collect_internal_reserve_candidates()
            picked = self._pick_fanout_funding_inputs(candidates, total_output_value)
            if not picked:
                total_avail = sum(c["value_sat"] for c in candidates)
                largest = candidates[0]["value_sat"] if candidates else 0
                n_c = len(candidates)

                def _est_vbytes(n_in: int, n_out: int) -> int:
                    return 10 + n_in * 148 + n_out * 34

                fee_if_all_inputs = (
                    calculate_fee(_est_vbytes(n_c, UTXO_POOL_TARGET + 1))
                    if n_c > 0
                    else 0
                )
                approx_total_need = total_output_value + fee_if_all_inputs
                self._last_refill_error = (
                    "Cannot fund fan-out: need about "
                    f"{approx_total_need} sat (outputs {UTXO_POOL_TARGET}x{UTXO_VALUE_EACH}="
                    f"{total_output_value} + about {fee_if_all_inputs} fee with {n_c} inputs); "
                    f"internal reserve total {total_avail} sat, largest {largest} sat. "
                    "POST /utxo/reserve with {txid,vout,value_sat} for larger funding UTXOs, "
                    "or lower UTXO_POOL_TARGET / UTXO_VALUE_EACH."
                )
                logger.error(self._last_refill_error)
                return None

            funding_utxos, fee_sat, change_value, add_change_output = picked
            sum_in = sum(u["value_sat"] for u in funding_utxos)
            est_outputs = UTXO_POOL_TARGET + (1 if add_change_output else 0)
            est_bytes = 10 + len(funding_utxos) * 148 + est_outputs * 34
            if FANOUT_MAX_INPUTS > 0 and len(funding_utxos) > FANOUT_MAX_INPUTS:
                self._last_refill_error = (
                    f"Refusing fan-out requiring {len(funding_utxos)} inputs "
                    f"(about {est_bytes} bytes) because FANOUT_MAX_INPUTS={FANOUT_MAX_INPUTS}. "
                    "Import larger reserve UTXOs, raise RESERVE_MIN_IMPORT_SAT / BITAILS_IMPORT_MIN_SAT "
                    "for future imports, or lower UTXO_POOL_TARGET / UTXO_VALUE_EACH."
                )
                logger.error(self._last_refill_error)
                return None
            logger.info(
                "Fan-out funding: %s input(s), %s sat in, fee ~%s sat, change output=%s, est_bytes~%s",
                len(funding_utxos),
                sum_in,
                fee_sat,
                add_change_output,
                est_bytes,
            )

            outputs = [TxOutput(UTXO_VALUE_EACH, p2pkh_script) for _ in range(UTXO_POOL_TARGET)]
            if add_change_output and change_value >= MIN_CHANGE_OUTPUT_SAT:
                # Keep change outside the numbered pool vouts so it remains a funding UTXO.
                outputs.append(TxOutput(change_value, p2pkh_script))

            tx_inputs = [
                TxInput(bytes.fromhex(u["txid"])[::-1], u["vout"], Script(), 0xFFFFFFFF)
                for u in funding_utxos
            ]
            tx = Tx(version=1, inputs=tx_inputs, outputs=outputs, locktime=0)

            prev_output_script = public_key.P2PKH_script()
            pub_key_bytes = public_key.to_bytes()
            for idx, utxo in enumerate(funding_utxos):
                sighash_type = SigHash(0x41)  # ALL | FORKID (BSV)
                sig_hash = tx.signature_hash(
                    input_index=idx,
                    value=utxo["value_sat"],
                    script_code=prev_output_script,
                    sighash=sighash_type,
                )
                signature = private_key.sign(sig_hash, hasher=None)
                signature_bytes = signature + pack_byte(0x41)
                script_sig = (
                    pack_byte(len(signature_bytes)) + signature_bytes +
                    pack_byte(len(pub_key_bytes)) + pub_key_bytes
                )
                tx.inputs[idx].script_sig = Script(script_sig)

            raw_tx_hex = tx.to_bytes().hex()
            gorilla_tx_hex: Optional[str] = None
            if GORILLA_TX_FORMAT != "raw":
                prev_locking_script_hex = prev_output_script.to_bytes().hex()
                prevouts = [
                    {
                        "value_sat": int(u["value_sat"]),
                        "locking_script_hex": prev_locking_script_hex,
                    }
                    for u in funding_utxos
                ]
                try:
                    gorilla_tx_hex = to_extended_format_hex(raw_tx_hex, prevouts)
                except Exception as ef_err:
                    if GORILLA_TX_FORMAT == "ef":
                        self._last_refill_error = (
                            f"Could not build EF payload for Gorilla fan-out submit: {ef_err}"
                        )
                        logger.error(self._last_refill_error)
                        return None
                    logger.warning(
                        "Could not build EF payload for Gorilla fan-out (%s); continuing with raw",
                        ef_err,
                    )
            txid_canon = tx.hex_hash()
            if txid_canon:
                txid_canon = txid_canon.lower()
            try:
                broadcast = await submit(raw_tx_hex, gorilla_tx_hex=gorilla_tx_hex)
            except BroadcastError as e:
                self._last_refill_error = (
                    f"Fan-out broadcast failed (all ARC endpoints): {e} | "
                    f"gorilla={e.gorilla_error or '<none>'} | taal={e.taal_error or '<none>'}"
                )
                logger.error(self._last_refill_error)
                return None
            except Exception as e:
                self._last_refill_error = f"Fan-out broadcast failed: {type(e).__name__}: {e}"
                logger.error(self._last_refill_error, exc_info=True)
                return None

            txid_arc = broadcast.get("txid")
            txid = txid_canon or (str(txid_arc).lower() if txid_arc else None)
            if not txid:
                logger.error("Fan-out broadcast returned no txid: %s", broadcast)
                return None
            if (
                txid_canon
                and txid_arc
                and str(txid_arc).lower() != txid_canon
            ):
                logger.debug(
                    "ARC txid %s != local hex_hash %s; using canonical for DB",
                    txid_arc,
                    txid_canon,
                )
            logger.info(
                "Fan-out broadcast via %s (status=%s)",
                broadcast.get("broadcaster"),
                broadcast.get("status"),
            )

            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    for u in funding_utxos:
                        await conn.execute(
                            """
                            DELETE FROM utxos
                            WHERE txid = $1 AND vout = $2 AND utxo_role = 'reserve'
                            """,
                            u["txid"],
                            u["vout"],
                        )
                    for vout in range(UTXO_POOL_TARGET):
                        await conn.execute(
                            """
                            INSERT INTO utxos (txid, vout, value_sat, utxo_role, locked)
                            VALUES ($1, $2, $3, 'pool', FALSE)
                            """,
                            txid,
                            vout,
                            UTXO_VALUE_EACH,
                        )
                    if add_change_output and change_value >= MIN_CHANGE_OUTPUT_SAT:
                        await conn.execute(
                            """
                            INSERT INTO utxos (txid, vout, value_sat, utxo_role, locked)
                            VALUES ($1, $2, $3, 'reserve', FALSE)
                            """,
                            txid,
                            UTXO_POOL_TARGET,
                            change_value,
                        )

            if add_change_output and change_value >= MIN_CHANGE_OUTPUT_SAT:
                logger.info(
                    "Fan-out change %s sat recorded as internal reserve (vout %s)",
                    change_value,
                    UTXO_POOL_TARGET,
                )

            logger.info(f"Fan-out complete: {txid} with {UTXO_POOL_TARGET} outputs")
            self._last_refill_error = None
            self._refill_cooldown_until = 0.0
            return txid

    async def monitor_loop(self) -> None:
        """
        Background loop that monitors pool depth and spendable value.

        The count threshold catches pool exhaustion. The value threshold catches
        gradual decay where the pool row count stays high but the UTXOs become
        too small to be useful for sustained broadcasting.
        """
        while True:
            try:
                await asyncio.sleep(60)

                try:
                    await self.sweep_stale_locks(older_than_seconds=120)
                except Exception as sweep_err:
                    logger.warning("Stale lock sweep failed: %s", sweep_err)

                metrics = await self.pool_metrics()
                depth_threshold = max(1, UTXO_POOL_TARGET // 2)
                value_threshold = max(
                    metrics["minimum_viable_utxo_value"],
                    (UTXO_POOL_TARGET * UTXO_VALUE_EACH) // 2,
                )

                logger.info(
                    "UTXO pool metrics: spendable_depth=%s unlocked_depth=%s "
                    "spendable_balance=%s threshold_depth=%s threshold_value=%s",
                    metrics["spendable_depth"],
                    metrics["unlocked_depth"],
                    metrics["spendable_balance"],
                    depth_threshold,
                    value_threshold,
                )

                if (
                    metrics["spendable_depth"] < depth_threshold
                    or metrics["spendable_balance"] < value_threshold
                ):
                    now = time.monotonic()
                    if (
                        REFILL_FAILURE_COOLDOWN_SECONDS > 0
                        and now < self._refill_cooldown_until
                    ):
                        logger.debug(
                            "Pool below threshold; fan-out cooldown %ss remaining — skipping refill",
                            int(self._refill_cooldown_until - now),
                        )
                    else:
                        logger.warning(
                            "Pool health below threshold, triggering fan-out refill"
                        )
                        result = await self.fan_out_refill()
                        if (
                            result is None
                            and REFILL_FAILURE_COOLDOWN_SECONDS > 0
                        ):
                            self._refill_cooldown_until = (
                                time.monotonic() + REFILL_FAILURE_COOLDOWN_SECONDS
                            )
                            logger.warning(
                                "Fan-out failed; next automatic attempt in %ss "
                                "(set REFILL_FAILURE_COOLDOWN_SECONDS=0 to disable backoff)",
                                REFILL_FAILURE_COOLDOWN_SECONDS,
                            )

            except asyncio.CancelledError:
                logger.info("UTXO monitor loop shutdown")
                raise

            except Exception as e:
                logger.error(f"Error in UTXO monitor loop: {e}", exc_info=True)


# Global singleton instance
utxo_manager = UTXOManager()
