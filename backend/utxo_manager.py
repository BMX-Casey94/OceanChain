"""
OceanChain UTXO Manager Module

Manages the UTXO pool in PostgreSQL for high-throughput transaction broadcasting.
Handles acquisition, release, consumption, and automatic fan-out refills.
"""

import asyncio
import logging
from typing import Any, Optional, Tuple

import asyncpg
import httpx

from config import (
    UTXO_POOL_TARGET,
    UTXO_VALUE_EACH,
    BSV_PRIVATE_KEY_WIF,
    BSV_NETWORK,
    WHATSONCHAIN_BASE_URL,
    MIN_CHANGE_OUTPUT_SAT,
)

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

        self._initialized = True
        logger.info("UTXO manager initialized")

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
                UPDATE utxos SET locked = TRUE
                WHERE (txid, vout) = (
                    SELECT txid, vout FROM utxos
                    WHERE locked = FALSE AND value_sat >= $1
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
                "UPDATE utxos SET locked = FALSE WHERE txid = $1 AND vout = $2",
                txid, vout
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

    async def add_utxo(self, txid: str, vout: int, value_sat: int) -> None:
        """
        Add a new UTXO to the pool (change output from a broadcast TX).

        Args:
            txid: Transaction ID
            vout: Output index
            value_sat: Value in satoshis
        """
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO utxos (txid, vout, value_sat)
                VALUES ($1, $2, $3)
                ON CONFLICT (txid, vout) DO NOTHING
                """,
                txid, vout, value_sat
            )

        logger.debug(f"Added UTXO {txid}:{vout} ({value_sat} sat)")

    async def _known_utxo_keys(self) -> set[tuple[str, int]]:
        """Return every UTXO currently tracked in the local pool."""
        if not self._pool:
            raise RuntimeError("UTXO manager not initialized")

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT txid, vout FROM utxos")

        return {(str(row["txid"]), int(row["vout"])) for row in rows}

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

    async def pool_depth(self) -> int:
        """Return the count of unlocked, viable UTXOs in the pool."""
        metrics = await self.pool_metrics()
        return metrics["spendable_depth"]

    async def _fetch_wallet_utxos(self, endpoint: str) -> list[dict[str, Any]]:
        """
        Fetch wallet UTXOs from WhatsOnChain for the configured key address.

        Args:
            endpoint: One of `confirmed/unspent` or `unspent/all`
        """
        from tx_builder import get_change_address

        address = get_change_address()
        url = f"{WHATSONCHAIN_BASE_URL}/{BSV_NETWORK}/address/{address}/{endpoint}"
        token: Optional[str] = None
        results: list[dict[str, Any]] = []

        async with httpx.AsyncClient() as client:
            while True:
                params: dict[str, Any] = {"limit": 1000}
                if token:
                    params["token"] = token

                response = await client.get(url, params=params, timeout=20.0)
                response.raise_for_status()
                data = response.json()

                if data.get("error"):
                    raise RuntimeError(f"WhatsOnChain error: {data['error']}")

                batch = data.get("result") or []
                results.extend(batch)

                token = response.headers.get("next-page") or response.headers.get("x-next-page")
                if not token or not batch:
                    break

        return results

    async def _collect_wallet_utxo_candidates(self) -> list[dict[str, Any]]:
        """
        All spendable wallet UTXOs from WhatsOnChain (deduped), excluding rows
        already tracked in the Postgres pool. Confirmed entries are ingested
        before mempool so behaviour stays predictable when both endpoints overlap.
        """
        known_utxos = await self._known_utxo_keys()
        seen: set[tuple[str, int]] = set()
        collected: list[dict[str, Any]] = []

        for endpoint in ("confirmed/unspent", "unspent/all"):
            for item in await self._fetch_wallet_utxos(endpoint):
                txid = str(item.get("tx_hash", ""))
                vout = int(item.get("tx_pos", -1))
                key = (txid, vout)
                if key in seen:
                    continue
                value_sat = int(item.get("value", 0))
                if not txid or vout < 0:
                    continue
                if item.get("isSpentInMempoolTx"):
                    continue
                if key in known_utxos:
                    continue

                seen.add(key)
                collected.append({
                    "txid": txid,
                    "vout": vout,
                    "value_sat": value_sat,
                    "status": str(item.get("status", "unknown")),
                })

        collected.sort(key=lambda row: row["value_sat"], reverse=True)
        return collected

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
        each containing UTXO_VALUE_EACH satoshis. Broadcasts via
        GorillaPool ARC (no fallback - fan-out failure should halt).

        Returns:
            Transaction ID of the fan-out TX, or None on failure
        """
        from tx_builder import get_change_address, calculate_fee
        from broadcaster import submit_raw
        from bitcoinx import (
            PrivateKey,
            TxInput,
            TxOutput,
            Tx,
            Script,
            P2PKH_Address,
            Bitcoin,
            pack_byte,
        )

        async with self._refill_lock:
            logger.info(f"Starting fan-out refill for {UTXO_POOL_TARGET} outputs")

            private_key = PrivateKey.from_WIF(BSV_PRIVATE_KEY_WIF)
            public_key = private_key.public_key
            address = get_change_address()
            p2pkh_script = P2PKH_Address.from_string(address, Bitcoin).to_script()

            total_output_value = UTXO_POOL_TARGET * UTXO_VALUE_EACH

            candidates = await self._collect_wallet_utxo_candidates()
            picked = self._pick_fanout_funding_inputs(candidates, total_output_value)
            if not picked:
                total_avail = sum(c["value_sat"] for c in candidates)
                largest = candidates[0]["value_sat"] if candidates else 0
                min_single = total_output_value + calculate_fee(
                    10 + 148 + UTXO_POOL_TARGET * 34
                )
                logger.error(
                    "Cannot fund fan-out: largest single UTXO %s sat; "
                    "%s spendable wallet UTXO(s) totalling %s sat (outside pool). "
                    "Pool outputs need %s sat plus fee (~%s sat for one P2PKH input). "
                    "Consolidate to one larger UTXO or lower UTXO_POOL_TARGET.",
                    largest,
                    len(candidates),
                    total_avail,
                    total_output_value,
                    min_single,
                )
                return None

            funding_utxos, fee_sat, change_value, add_change_output = picked
            sum_in = sum(u["value_sat"] for u in funding_utxos)
            logger.info(
                "Fan-out funding: %s input(s), %s sat in, fee ~%s sat, change output=%s",
                len(funding_utxos),
                sum_in,
                fee_sat,
                add_change_output,
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
                sig_hash = tx.signature_hash(
                    input_index=idx,
                    value=utxo["value_sat"],
                    script=prev_output_script,
                    sighash=0x41,
                )
                signature = private_key.sign(sig_hash, hasher=None)
                signature_bytes = signature + pack_byte(0x41)
                script_sig = (
                    pack_byte(len(signature_bytes)) + signature_bytes +
                    pack_byte(len(pub_key_bytes)) + pub_key_bytes
                )
                tx.inputs[idx].script = Script(script_sig)

            raw_tx_hex = tx.to_bytes().hex()
            txid = await submit_raw(raw_tx_hex)

            for vout in range(UTXO_POOL_TARGET):
                await self.add_utxo(txid, vout, UTXO_VALUE_EACH)

            if add_change_output and change_value >= MIN_CHANGE_OUTPUT_SAT:
                logger.info(
                    "Fan-out preserved %s sat as an external wallet funding UTXO",
                    change_value,
                )

            logger.info(f"Fan-out complete: {txid} with {UTXO_POOL_TARGET} outputs")
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
                    logger.warning("Pool health below threshold, triggering fan-out refill")
                    await self.fan_out_refill()

            except asyncio.CancelledError:
                logger.info("UTXO monitor loop shutdown")
                raise

            except Exception as e:
                logger.error(f"Error in UTXO monitor loop: {e}", exc_info=True)


# Global singleton instance
utxo_manager = UTXOManager()
