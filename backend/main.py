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
import signal
import sys
from typing import Any, Optional

import asyncpg

from config import (
    DATABASE_URL,
    BATCH_INTERVAL_SECONDS,
    VPS_API_PORT,
    UTXO_AUTO_REFILL_ON_START,
    validate_config,
    get_config_summary,
)
from ais_client import ais_client
from tx_builder import build_op_return_tx, get_change_address, calculate_fee
from utxo_manager import utxo_manager
from broadcaster import submit, BroadcastError
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
logger = logging.getLogger(__name__)

# Global database pool
db_pool: Optional[asyncpg.Pool] = None


async def process_vessel(
    semaphore: asyncio.Semaphore,
    mmsi: str,
    position: dict[str, Any],
    change_address: str,
) -> bool:
    """
    Process a single vessel position: acquire UTXO, build TX, submit, update pool.
    
    Args:
        semaphore: Concurrency limiter
        mmsi: Vessel MMSI
        position: Position data dict
        change_address: Address for change output
        
    Returns:
        True if successful, False otherwise
    """
    async with semaphore:
        # Acquire UTXO
        utxo = await utxo_manager.acquire_utxo()
        if not utxo:
            logger.debug("No UTXO available for vessel %s", mmsi)
            return False
        
        try:
            # Build transaction
            raw_tx_hex, change_value = build_op_return_tx(
                utxo=utxo,
                position=position,
                change_address=change_address,
            )
            
            # Calculate fee for stats
            fee_sat = utxo["value_sat"] - change_value
            
            # Submit transaction
            result = await submit(raw_tx_hex)
            txid = result["txid"]
            broadcaster = result["broadcaster"]
            
            # Success: consume UTXO, add change output
            await utxo_manager.consume_utxo(utxo["txid"], utxo["vout"])
            await utxo_manager.add_utxo(txid, 1, change_value)  # Change is output index 1
            
            # Update stats
            record_tx(fee_sat)
            
            # Broadcast WebSocket event
            await broadcast_tx_event({
                "txid": txid,
                "mmsi": mmsi,
                "vessel_name": position.get("ship_name", "Unknown"),
                "lat": position.get("latitude", 0),
                "lon": position.get("longitude", 0),
                "speed": position.get("speed", 0),
                "heading": position.get("heading"),
                "timestamp": position.get("timestamp", 0),
                "fee_sat": fee_sat,
                "broadcaster": broadcaster,
            })
            
            logger.debug(f"TX {txid} for vessel {mmsi} via {broadcaster}")
            return True
        
        except BroadcastError as e:
            logger.error(f"Broadcast failed for {mmsi}: {e}")
            await utxo_manager.release_utxo(utxo["txid"], utxo["vout"])
            return False
        
        except Exception as e:
            logger.error(f"Error processing {mmsi}: {e}", exc_info=True)
            await utxo_manager.release_utxo(utxo["txid"], utxo["vout"])
            return False


async def broadcasting_loop() -> None:
    """
    Main broadcasting loop.
    
    Every BATCH_INTERVAL_SECONDS:
    1. Get current vessel snapshot from AIS client
    2. Process all vessels concurrently (capped at 50 in-flight)
    3. Log batch statistics
    """
    logger.info(f"Broadcasting loop starting, interval: {BATCH_INTERVAL_SECONDS}s")
    
    change_address = get_change_address()
    logger.info(f"Change address: {change_address}")
    
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
                logger.info("No vessels in snapshot, skipping batch")
                continue
            
            pool_ready = await utxo_manager.pool_depth()
            if pool_ready == 0:
                logger.warning(
                    "UTXO pool is empty (%s vessels in AIS snapshot). "
                    "Fund the wallet and run: curl -s -X POST http://127.0.0.1:%s/utxo/refill "
                    "Or set UTXO_AUTO_REFILL_ON_START=1 in .env for a one-shot fan-out at startup.",
                    vessel_count,
                    VPS_API_PORT,
                )
                continue

            logger.info(f"Starting batch: {vessel_count} vessels (spendable pool depth: {pool_ready})")
            update_vessel_count(vessel_count)
            
            # Process vessels concurrently with semaphore
            semaphore = asyncio.Semaphore(50)
            
            tasks = [
                process_vessel(semaphore, mmsi, position, change_address)
                for mmsi, position in snapshot.items()
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successes
            successes = sum(1 for r in results if r is True)
            failures = vessel_count - successes
            
            logger.info(
                f"Batch complete: {successes}/{vessel_count} successful, "
                f"{failures} failures"
            )
        
        except asyncio.CancelledError:
            logger.info("Broadcasting loop shutdown")
            raise
        
        except Exception as e:
            logger.error(f"Error in broadcasting loop: {e}", exc_info=True)
            await asyncio.sleep(10)  # Brief pause before retry


async def init_database() -> asyncpg.Pool:
    """
    Initialize the asyncpg connection pool.
    
    Returns:
        Connection pool
    """
    logger.info("Connecting to database...")
    
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=20,
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
            "UTXO pool is empty — no on-chain broadcasts will occur until the pool is filled. "
            "Typical: curl -s -X POST http://127.0.0.1:%s/utxo/refill (wallet needs one large UTXO).",
            VPS_API_PORT,
        )
        if UTXO_AUTO_REFILL_ON_START:
            logger.info("UTXO_AUTO_REFILL_ON_START=1: attempting fan-out refill from wallet…")
            txid = await utxo_manager.fan_out_refill()
            if txid:
                depth = await utxo_manager.pool_depth()
                logger.info("Fan-out tx %s recorded; spendable pool depth now: %s", txid, depth)
            else:
                logger.error(
                    "Automatic fan-out failed (no suitable wallet UTXO or broadcast error). "
                    "Ensure one confirmed UTXO covers roughly UTXO_POOL_TARGET × UTXO_VALUE_EACH plus fees."
                )

    # Create tasks
    tasks = [
        asyncio.create_task(ais_client.run(), name="ais_client"),
        asyncio.create_task(broadcasting_loop(), name="broadcasting_loop"),
        asyncio.create_task(utxo_manager.monitor_loop(), name="utxo_monitor"),
        asyncio.create_task(run_api_server(), name="api_server"),
    ]
    
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
