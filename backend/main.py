"""
OceanChain Main Orchestrator

Runs all services concurrently:
- AIS WebSocket client (vessel position ingestion)
- Broadcasting loop (TX construction and submission)
- UTXO monitor loop (pool maintenance)
- API server (HTTP + WebSocket)
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Any, Optional

import asyncpg

from config import (
    DATABASE_URL,
    BATCH_INTERVAL_SECONDS,
    BROADCAST_CONCURRENCY,
    VPS_API_PORT,
    GORILLA_TX_FORMAT,
    UTXO_AUTO_REFILL_ON_START,
    LOG_SUMMARY_INTERVAL_SECONDS,
    LOG_SAMPLE_RAW_TX_PATH,
    validate_config,
    get_config_summary,
)
from ais_client import ais_client
from tx_builder import (
    build_op_return_tx,
    get_change_address,
    get_wallet_prevout_locking_script_hex,
    canonical_txid_from_raw_hex,
    to_extended_format_hex,
)
from utxo_manager import utxo_manager
from broadcaster import submit, BroadcastError
from broadcast_stats import broadcast_stats
from logging_config import configure_quiet_loggers, vessel_log_label
from api_server import (
    run_api_server,
    state as app_state,
    record_tx,
    update_vessel_count,
    broadcast_tx_event,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
configure_quiet_loggers()
logger = logging.getLogger(__name__)

# Global database pool
db_pool: Optional[asyncpg.Pool] = None


async def process_vessel(
    semaphore: asyncio.Semaphore,
    mmsi: str,
    position: dict[str, Any],
    change_address: str,
    gorilla_prevout_locking_script_hex: str,
) -> bool:
    """
    Process a single vessel position: acquire UTXO, build TX, submit, update pool.
    
    Args:
        semaphore: Concurrency limiter
        mmsi: Vessel MMSI
        position: Position data dict
        change_address: Address for change output
        gorilla_prevout_locking_script_hex: Wallet input script for EF payloads
        
    Returns:
        True if successful, False otherwise
    """
    label = vessel_log_label(position)

    async with semaphore:
        # Acquire UTXO
        utxo = await utxo_manager.acquire_utxo()
        if not utxo:
            await broadcast_stats.record_skip_no_utxo(label)
            logger.debug("No UTXO available for vessel %s", label)
            return False

        try:
            # Build transaction
            raw_tx_hex, change_value = build_op_return_tx(
                utxo=utxo,
                position=position,
                change_address=change_address,
            )
            gorilla_tx_hex: Optional[str] = None
            if GORILLA_TX_FORMAT != "raw":
                try:
                    gorilla_tx_hex = to_extended_format_hex(
                        raw_tx_hex,
                        [
                            {
                                "value_sat": int(utxo["value_sat"]),
                                "locking_script_hex": gorilla_prevout_locking_script_hex,
                            }
                        ],
                    )
                except Exception as ef_err:
                    if GORILLA_TX_FORMAT == "ef":
                        raise RuntimeError(
                            f"Could not build EF payload for Gorilla submit: {ef_err}"
                        ) from ef_err
                    logger.warning(
                        "Could not build EF payload for Gorilla (%s); continuing with raw for %s",
                        ef_err,
                        label,
                    )
            
            # Calculate fee for stats
            fee_sat = utxo["value_sat"] - change_value
            
            # Submit transaction (store explorer-canonical txid; ARC may differ)
            result = await submit(raw_tx_hex, gorilla_tx_hex=gorilla_tx_hex)
            txid_canon = canonical_txid_from_raw_hex(raw_tx_hex)
            txid_arc = result.get("txid")
            txid = txid_canon or (str(txid_arc).lower() if txid_arc else None)
            if not txid:
                raise RuntimeError("No txid from ARC and could not derive from raw tx")
            if (
                txid_canon
                and txid_arc
                and str(txid_arc).lower() != txid_canon
            ):
                logger.debug(
                    "ARC txid %s != canonical hex_hash %s; using canonical for DB",
                    txid_arc,
                    txid_canon,
                )
            broadcaster = result["broadcaster"]

            if LOG_SAMPLE_RAW_TX_PATH and not os.path.exists(LOG_SAMPLE_RAW_TX_PATH):
                try:
                    with open(LOG_SAMPLE_RAW_TX_PATH, "w", encoding="ascii") as sf:
                        sf.write(raw_tx_hex.strip())
                    logger.info(
                        "Diagnostic: wrote one sample raw tx to %s — run scripts/woc_decode_sample.sh",
                        LOG_SAMPLE_RAW_TX_PATH,
                    )
                except OSError as werr:
                    logger.warning("Could not write LOG_SAMPLE_RAW_TX_PATH: %s", werr)
            
            # Success: consume UTXO, add change output
            await utxo_manager.consume_utxo(utxo["txid"], utxo["vout"])
            await utxo_manager.add_utxo(txid, 1, change_value)  # Change is output index 1
            
            # Update stats
            record_tx(fee_sat)
            
            # Broadcast WebSocket event
            tx_payload: dict[str, Any] = {
                "txid": txid,
                "mmsi": mmsi,
                "vessel_name": position.get("ship_name") or "",
                "call_sign": position.get("call_sign") or "",
                "destination": position.get("destination") or "",
                "imo": position.get("imo") or "",
                "ship_type": position.get("ship_type"),
                "lat": position.get("latitude", 0),
                "lon": position.get("longitude", 0),
                "speed": position.get("speed", 0),
                "heading": position.get("heading"),
                "timestamp": position.get("timestamp", 0),
                "fee_sat": fee_sat,
                "broadcaster": broadcaster,
            }
            await broadcast_tx_event(tx_payload)

            sample = f"{label} tx={txid[:14]}... fee={fee_sat}"
            await broadcast_stats.record_ok(sample, fee_sat)
            logger.debug("TX %s for %s via %s", txid[:16], label, broadcaster)
            return True

        except BroadcastError as e:
            await broadcast_stats.record_fail_broadcast(label, str(e))
            logger.debug("Broadcast failed for %s: %s", label, e)
            if e.tx_was_submitted:
                await utxo_manager.consume_utxo(utxo["txid"], utxo["vout"])
                logger.debug(
                    "Consumed UTXO %s:%s after failed broadcast (tx was submitted, "
                    "releasing would risk double-spend)",
                    utxo["txid"][:16],
                    utxo["vout"],
                )
            else:
                await utxo_manager.release_utxo(utxo["txid"], utxo["vout"])
            return False

        except Exception as e:
            await broadcast_stats.record_fail_other(label, str(e))
            logger.error("Error processing %s: %s", label, e, exc_info=True)
            await utxo_manager.release_utxo(utxo["txid"], utxo["vout"])
            return False


async def broadcasting_loop() -> None:
    """
    Main broadcasting loop.
    
    Every BATCH_INTERVAL_SECONDS:
    1. Get current vessel snapshot from AIS client
    2. Process all vessels concurrently (capped at BROADCAST_CONCURRENCY in-flight)
    3. Log batch statistics
    """
    logger.info(
        "Broadcasting loop starting, interval: %ss, concurrency: %s",
        BATCH_INTERVAL_SECONDS,
        BROADCAST_CONCURRENCY,
    )
    
    change_address = get_change_address()
    logger.info(f"Change address: {change_address}")
    gorilla_prevout_locking_script_hex = get_wallet_prevout_locking_script_hex()
    logger.info(
        "Gorilla tx format mode: %s",
        GORILLA_TX_FORMAT,
    )
    
    while True:
        try:
            # Wait for pause to clear
            await app_state.pause_event.wait()
            
            # Sleep until next batch
            await asyncio.sleep(BATCH_INTERVAL_SECONDS)
            
            # Check pause again after sleep
            if app_state.paused:
                continue
            
            # Get current snapshot
            snapshot = ais_client.get_current_snapshot()
            vessel_count = len(snapshot)
            
            if vessel_count == 0:
                logger.debug("No vessels in snapshot, skipping batch")
                continue

            pool_ready = await utxo_manager.pool_depth()
            if pool_ready == 0:
                logger.warning(
                    "UTXO pool is empty (%s vessels in AIS snapshot). "
                    "Register funding: curl -s -X POST http://127.0.0.1:%s/utxo/reserve "
                    "-H 'Content-Type: application/json' "
                    "-d '{\"txid\":\"...\",\"vout\":0,\"value_sat\":...}' then POST /utxo/refill.",
                    vessel_count,
                    VPS_API_PORT,
                )
                continue

            logger.debug(
                "Starting batch: %s vessels (pool depth %s)",
                vessel_count,
                pool_ready,
            )
            update_vessel_count(vessel_count)
            
            # Process vessels concurrently with semaphore
            semaphore = asyncio.Semaphore(BROADCAST_CONCURRENCY)
            
            tasks = [
                process_vessel(
                    semaphore,
                    mmsi,
                    position,
                    change_address,
                    gorilla_prevout_locking_script_hex,
                )
                for mmsi, position in snapshot.items()
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successes = sum(1 for r in results if r is True)
            failures = vessel_count - successes
            task_errors = [r for r in results if isinstance(r, BaseException)]
            for err in task_errors:
                if isinstance(err, asyncio.CancelledError):
                    raise err
                await broadcast_stats.record_fail_other("task", repr(err))
                logger.error("Batch task exception: %s", err, exc_info=err)

            logger.debug(
                "Batch complete: %s/%s ok, %s failed",
                successes,
                vessel_count,
                failures,
            )
        
        except asyncio.CancelledError:
            logger.info("Broadcasting loop shutdown")
            raise
        
        except Exception as e:
            logger.error(f"Error in broadcasting loop: {e}", exc_info=True)
            await asyncio.sleep(10)  # Brief pause before retry


async def log_summary_loop() -> None:
    """
    Periodic INFO summary: broadcast totals, pool depth, AIS snapshot size, small samples.
    """
    while True:
        try:
            await asyncio.sleep(LOG_SUMMARY_INTERVAL_SECONDS)
            snap = await broadcast_stats.drain_window()
            pool = await utxo_manager.pool_depth()
            vessels = ais_client.get_vessel_count()
            msgs = ais_client.get_message_count()
            total_fail = (
                snap["fail_broadcast"] + snap["skip_no_utxo"] + snap["fail_other"]
            )
            avg_fee = (
                snap["fees_sat"] / snap["ok"] if snap["ok"] else 0.0
            )
            logger.info(
                "Summary (%ss): broadcasts ok=%s fail=%s "
                "(arc=%s no_utxo=%s other=%s) avg_fee_sat=%.2f "
                "pool_depth=%s ais_vessels=%s ais_msgs_total=%s",
                LOG_SUMMARY_INTERVAL_SECONDS,
                snap["ok"],
                total_fail,
                snap["fail_broadcast"],
                snap["skip_no_utxo"],
                snap["fail_other"],
                avg_fee,
                pool,
                vessels,
                msgs,
            )
            if snap["ok_samples"]:
                logger.info("Sample ok: %s", " · ".join(snap["ok_samples"]))
            if snap["fail_samples"]:
                logger.warning("Sample fail: %s", " · ".join(snap["fail_samples"]))
        except asyncio.CancelledError:
            logger.info("Summary loop shutdown")
            raise
        except Exception as e:
            logger.error("Summary loop error: %s", e, exc_info=True)


async def init_database() -> asyncpg.Pool:
    """
    Initialize the asyncpg connection pool.
    
    Returns:
        Connection pool
    """
    logger.info("Connecting to database...")
    
    from config import DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=DB_POOL_MIN_SIZE,
        max_size=DB_POOL_MAX_SIZE,
        command_timeout=60,
    )
    
    logger.info("Database connection pool created")
    return pool


async def shutdown(pool: asyncpg.Pool, tasks: list[asyncio.Task]) -> None:
    """
    Graceful shutdown handler.
    
    Cancels all running tasks and closes the database pool.
    """
    logger.info("Shutting down...")
    
    # Cancel all tasks
    for task in tasks:
        task.cancel()
    
    # Wait for tasks to complete
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Close database pool
    await pool.close()
    logger.info("Database pool closed")


async def main() -> None:
    """
    Main entry point.
    
    Initializes all services and runs them concurrently.
    """
    global db_pool
    
    # Validate configuration
    config_errors = validate_config()
    if config_errors:
        logger.error("Configuration errors:")
        for error in config_errors:
            logger.error(f"  - {error}")
        sys.exit(1)
    
    logger.info("OceanChain starting...")
    logger.info(f"Config: {get_config_summary()}")
    
    # Initialize database
    db_pool = await init_database()
    
    # Initialize UTXO manager
    await utxo_manager.initialize(db_pool)
    
    # Check initial pool depth
    depth = await utxo_manager.pool_depth()
    logger.info(f"Initial UTXO pool depth: {depth}")
    if depth == 0:
        logger.warning(
            "UTXO pool is empty — register internal reserve UTXO(s) then fan-out. "
            "POST http://127.0.0.1:%s/utxo/reserve JSON {txid,vout,value_sat}, then POST /utxo/refill.",
            VPS_API_PORT,
        )
        if UTXO_AUTO_REFILL_ON_START:
            logger.info("UTXO_AUTO_REFILL_ON_START=1: attempting fan-out refill from wallet…")
            try:
                txid = await utxo_manager.fan_out_refill()
            except Exception as e:
                logger.error(
                    "Automatic fan-out failed (%s). "
                    "Ensure POST /utxo/reserve has funding rows, or set UTXO_AUTO_REFILL_ON_START=0 "
                    "and run POST /utxo/refill after registering reserve UTXOs. Error: %s",
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                txid = None
            if txid:
                depth = await utxo_manager.pool_depth()
                logger.info("Fan-out tx %s recorded; spendable pool depth now: %s", txid, depth)
            elif UTXO_AUTO_REFILL_ON_START:
                refill_error = utxo_manager.last_refill_error()
                if refill_error:
                    logger.error("Automatic fan-out did not complete: %s", refill_error)
                else:
                    logger.error(
                        "Automatic fan-out did not complete. "
                        "Register internal reserve UTXO(s) via POST /utxo/reserve (sum must cover "
                        "UTXO_POOL_TARGET × UTXO_VALUE_EACH plus fees), then POST /utxo/refill."
                    )

    # Create tasks
    tasks = [
        asyncio.create_task(ais_client.run(), name="ais_client"),
        asyncio.create_task(broadcasting_loop(), name="broadcasting_loop"),
        asyncio.create_task(utxo_manager.monitor_loop(), name="utxo_monitor"),
        asyncio.create_task(run_api_server(), name="api_server"),
    ]
    if LOG_SUMMARY_INTERVAL_SECONDS > 0:
        tasks.append(asyncio.create_task(log_summary_loop(), name="log_summary"))
    else:
        logger.info(
            "Periodic log summary disabled (LOG_SUMMARY_INTERVAL_SECONDS=0)"
        )
    
    # Setup signal handlers
    loop = asyncio.get_running_loop()
    
    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        for task in tasks:
            task.cancel()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    # Run all tasks
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        await shutdown(db_pool, tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
