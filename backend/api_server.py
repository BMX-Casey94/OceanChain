"""
OceanChain API Server Module

FastAPI server providing health checks, stats endpoints, and WebSocket
broadcasting for real-time transaction updates.
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from config import VPS_API_PORT, UVICORN_ACCESS_LOG
from utxo_manager import utxo_manager

logger = logging.getLogger(__name__)

# Application state
app = FastAPI(
    title="OceanChain API",
    description="Real-time maritime vessel tracking on BSV blockchain",
    version="1.0.0",
)

# Shared state
class AppState:
    def __init__(self) -> None:
        self.start_time: float = time.time()
        self.paused: bool = False
        self.pause_event: asyncio.Event = asyncio.Event()
        self.pause_event.set()  # Not paused by default
        
        # Stats counters
        self.txs_today: int = 0
        self.active_vessels: int = 0
        self.bsv_spent_today: int = 0  # satoshis
        self.total_fees: int = 0
        self.tx_count: int = 0
        
        # Timeseries data (last 60 minutes)
        self.timeseries: deque[dict[str, Any]] = deque(maxlen=60)
        self._current_minute: str = ""
        self._current_minute_count: int = 0
        
        # WebSocket connections
        self.ws_connections: set[WebSocket] = set()


state = AppState()


def get_current_minute() -> str:
    """Get current minute as ISO string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")


def get_stats_snapshot() -> dict[str, Any]:
    """Get current stats as a dict."""
    avg_fee = state.total_fees / state.tx_count if state.tx_count > 0 else 22
    uptime_seconds = time.time() - state.start_time
    
    return {
        "txs_today": state.txs_today,
        "active_vessels": state.active_vessels,
        "bsv_spent_today": state.bsv_spent_today,
        "avg_fee_sat": round(avg_fee, 1),
        "uptime_seconds": round(uptime_seconds, 1),
        "uptime_pct": 100.0,  # We don't track downtime in this simple implementation
    }


def record_tx(fee_sat: int = 22) -> None:
    """Record a successful transaction in stats."""
    state.txs_today += 1
    state.tx_count += 1
    state.total_fees += fee_sat
    state.bsv_spent_today += fee_sat
    
    # Update timeseries
    current_minute = get_current_minute()
    if current_minute != state._current_minute:
        # New minute, push previous to deque if exists
        if state._current_minute:
            state.timeseries.append({
                "minute": state._current_minute,
                "tx_count": state._current_minute_count,
            })
        state._current_minute = current_minute
        state._current_minute_count = 0
    
    state._current_minute_count += 1


def update_vessel_count(count: int) -> None:
    """Update the active vessel count."""
    state.active_vessels = count


# HTTP Endpoints

@app.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint.
    
    Returns status, pool depth, pause state, and uptime.
    """
    try:
        pool_metrics = await utxo_manager.pool_metrics()
        reserve_metrics = await utxo_manager.reserve_funding_metrics()
    except Exception:
        pool_metrics = {
            "spendable_depth": -1,
            "spendable_balance": -1,
            "minimum_viable_utxo_value": -1,
        }
        reserve_metrics = {"reserve_count": -1, "reserve_total_sat": -1}

    uptime_seconds = time.time() - state.start_time

    return JSONResponse({
        "status": "ok",
        "pool_depth": pool_metrics["spendable_depth"],
        "pool_balance_sat": pool_metrics["spendable_balance"],
        "minimum_viable_utxo_value": pool_metrics["minimum_viable_utxo_value"],
        "reserve_count": reserve_metrics["reserve_count"],
        "reserve_total_sat": reserve_metrics["reserve_total_sat"],
        "paused": state.paused,
        "uptime_seconds": round(uptime_seconds, 1),
    })


@app.get("/stats/summary")
async def stats_summary() -> JSONResponse:
    """
    Get current aggregate statistics.
    
    Returns transaction counts, vessel count, BSV spent, avg fee, uptime.
    """
    return JSONResponse(get_stats_snapshot())


@app.get("/stats/timeseries")
async def stats_timeseries() -> JSONResponse:
    """
    Get transaction counts per minute for the last 60 minutes.
    
    Returns list of { minute: ISO string, tx_count: int }.
    """
    # Include current minute in progress
    result = list(state.timeseries)
    if state._current_minute:
        result.append({
            "minute": state._current_minute,
            "tx_count": state._current_minute_count,
        })
    
    return JSONResponse(result)


@app.post("/engine/pause")
async def pause_engine() -> JSONResponse:
    """
    Pause the broadcasting loop.
    
    Sets the paused flag and clears the pause event, causing
    the broadcasting loop to wait.
    """
    state.paused = True
    state.pause_event.clear()
    logger.info("Broadcasting engine paused")
    return JSONResponse({"status": "paused"})


@app.post("/engine/resume")
async def resume_engine() -> JSONResponse:
    """
    Resume the broadcasting loop.
    
    Clears the paused flag and sets the pause event, allowing
    the broadcasting loop to continue.
    """
    state.paused = False
    state.pause_event.set()
    logger.info("Broadcasting engine resumed")
    return JSONResponse({"status": "resumed"})


class ReserveUtxoBody(BaseModel):
    """Register a funding UTXO for internal fan-out (no WhatsOnChain)."""

    txid: str = Field(..., min_length=64, max_length=64)
    vout: int = Field(..., ge=0)
    value_sat: int = Field(..., ge=1)


@app.post("/utxo/reserve")
async def register_reserve_utxo(body: ReserveUtxoBody) -> JSONResponse:
    """
    Record a `reserve` UTXO in Postgres for fan-out funding.

    Use the real confirmed txid, vout, and value (satoshis) from your wallet.
    Vessel broadcasts only consume `pool` rows created after a successful fan-out.
    """
    try:
        txid = body.txid.strip().lower()
        if any(c not in "0123456789abcdef" for c in txid):
            return JSONResponse(
                {"status": "error", "message": "txid must be 64 hex characters"},
                status_code=400,
            )
        await utxo_manager.register_reserve_utxo(txid, body.vout, body.value_sat)
        metrics = await utxo_manager.reserve_funding_metrics()
        return JSONResponse(
            {
                "status": "success",
                "reserve_count": metrics["reserve_count"],
                "reserve_total_sat": metrics["reserve_total_sat"],
            }
        )
    except ValueError as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    except Exception as e:
        logger.error("register_reserve_utxo failed: %s", e, exc_info=True)
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


@app.post("/utxo/refill")
async def trigger_refill() -> JSONResponse:
    """
    Manually trigger a UTXO pool fan-out refill.

    Funds the fan-out from internal `reserve` rows only (see POST /utxo/reserve).
    """
    try:
        txid = await utxo_manager.fan_out_refill()
        if txid:
            return JSONResponse({"status": "success", "txid": txid})
        else:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "No internal reserve UTXO set covers fan-out; POST /utxo/reserve first",
                },
                status_code=500,
            )
    except Exception as e:
        logger.error(f"Manual refill failed: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


# WebSocket Endpoint

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time updates.
    
    On connect:
        - Sends initial stats snapshot
    
    Periodic messages:
        - Every 10s: stats update
        - Every 30s: UTXO pool depth
        - On each TX: transaction event
    """
    await websocket.accept()
    state.ws_connections.add(websocket)
    
    logger.debug(
        "WebSocket client connected (%s total)", len(state.ws_connections)
    )
    
    try:
        # Send initial stats
        await websocket.send_json({
            "type": "stats",
            "data": get_stats_snapshot(),
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # We don't expect client messages, but need to keep connection alive
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                # Send ping
                await websocket.send_json({"type": "ping"})
    
    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        state.ws_connections.discard(websocket)


async def broadcast_tx_event(tx_event: dict[str, Any]) -> None:
    """
    Broadcast a transaction event to all connected WebSocket clients.
    
    Called by the main broadcasting loop after each successful TX.
    
    Args:
        tx_event: Dict with txid, mmsi, vessel_name, lat, lon, speed, heading, timestamp, fee_sat, broadcaster
    """
    if not state.ws_connections:
        return
    
    message = {
        "type": "tx",
        "data": tx_event,
    }
    
    # Broadcast to all connections
    disconnected: set[WebSocket] = set()
    
    for ws in state.ws_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)
    
    # Remove disconnected clients
    state.ws_connections -= disconnected


async def broadcast_stats_event() -> None:
    """Broadcast current stats to all connected WebSocket clients."""
    if not state.ws_connections:
        return
    
    message = {
        "type": "stats",
        "data": get_stats_snapshot(),
    }
    
    disconnected: set[WebSocket] = set()
    
    for ws in state.ws_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)
    
    state.ws_connections -= disconnected


async def broadcast_utxo_event() -> None:
    """Broadcast UTXO pool depth to all connected WebSocket clients."""
    if not state.ws_connections:
        return
    
    try:
        metrics = await utxo_manager.pool_metrics()
        reserve = await utxo_manager.reserve_funding_metrics()
    except Exception:
        metrics = {
            "spendable_depth": -1,
            "spendable_balance": -1,
            "minimum_viable_utxo_value": -1,
        }
        reserve = {"reserve_count": -1, "reserve_total_sat": -1}

    message = {
        "type": "utxo",
        "data": {
            "depth": metrics["spendable_depth"],
            "balance_sat": metrics["spendable_balance"],
            "minimum_viable_utxo_value": metrics["minimum_viable_utxo_value"],
            "reserve_count": reserve["reserve_count"],
            "reserve_total_sat": reserve["reserve_total_sat"],
        },
    }
    
    disconnected: set[WebSocket] = set()
    
    for ws in state.ws_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)
    
    state.ws_connections -= disconnected


async def ws_broadcast_loop() -> None:
    """
    Background loop for periodic WebSocket broadcasts.
    
    - Every 10 seconds: stats update
    - Every 30 seconds: UTXO depth update
    """
    stats_counter = 0
    
    while True:
        try:
            await asyncio.sleep(10)
            stats_counter += 1
            
            # Stats every 10 seconds
            await broadcast_stats_event()
            
            # UTXO every 30 seconds (3 iterations)
            if stats_counter % 3 == 0:
                await broadcast_utxo_event()
        
        except asyncio.CancelledError:
            logger.info("WebSocket broadcast loop shutdown")
            raise
        except Exception as e:
            logger.error(f"Error in WS broadcast loop: {e}")


async def run_api_server() -> None:
    """
    Start the FastAPI server with uvicorn.
    
    This should be called as an asyncio task from main.py.
    """
    import uvicorn
    
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=VPS_API_PORT,
        log_level="info",
        access_log=UVICORN_ACCESS_LOG,
    )
    server = uvicorn.Server(config)
    logger.info("API and WebSocket server listening on port %s", VPS_API_PORT)
    
    # Start the broadcast loop in the background
    broadcast_task = asyncio.create_task(ws_broadcast_loop())
    
    try:
        await server.serve()
    finally:
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass
