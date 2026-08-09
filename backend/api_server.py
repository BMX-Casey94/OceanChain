"""
Ocechain API Server Module

FastAPI server providing health checks, stats endpoints, vessel queries,
and WebSocket broadcasting for real-time transaction updates.
"""

import asyncio
import logging
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, field_validator

from fastapi import FastAPI, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import (
    CORS_ALLOW_ORIGINS,
    OCEANCHAIN_ADMIN_API_KEY,
    UVICORN_ACCESS_LOG,
    VESSEL_SEARCH_RATE_LIMIT,
    VESSEL_SEARCH_RATE_WINDOW_SECONDS,
    VESSELS_LIST_DEFAULT_LIMIT,
    VESSELS_LIST_MAX_LIMIT,
    VPS_API_PORT,
)
from utxo_manager import utxo_manager
from vessel_api import get_snapshot, get_vessel, list_vessels, record_vessel_tx, search_vessels

logger = logging.getLogger(__name__)

# Application state
app = FastAPI(
    title="Ocechain API",
    description="Real-time maritime vessel tracking recorded on Bitcoin",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Simple in-memory rate limiter for public search
_search_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _rate_limit_search(request: Request) -> Optional[JSONResponse]:
    ip = _client_ip(request)
    now = time.time()
    window = float(VESSEL_SEARCH_RATE_WINDOW_SECONDS)
    hits = _search_hits[ip]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= VESSEL_SEARCH_RATE_LIMIT:
        return JSONResponse(
            {"status": "error", "message": "Rate limit exceeded. Try again shortly."},
            status_code=429,
        )
    hits.append(now)
    return None

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
    snapshot = get_snapshot()

    ais_status: dict[str, Any] = {
        "connected": False,
        "vessels": len(snapshot),
        "messages": 0,
        "rate_limited": False,
        "rate_limited_for_seconds": 0,
        "last_error": None,
    }
    try:
        from ais_client import ais_client

        ais_status = ais_client.get_status()
        ais_status["vessels"] = len(snapshot)
    except Exception:
        pass

    return JSONResponse({
        "status": "ok",
        "pool_depth": pool_metrics["spendable_depth"],
        "pool_balance_sat": pool_metrics["spendable_balance"],
        "minimum_viable_utxo_value": pool_metrics["minimum_viable_utxo_value"],
        "reserve_count": reserve_metrics["reserve_count"],
        "reserve_total_sat": reserve_metrics["reserve_total_sat"],
        "paused": state.paused,
        "uptime_seconds": round(uptime_seconds, 1),
        "ais_vessels": ais_status.get("vessels", len(snapshot)),
        "ais_connected": ais_status.get("connected"),
        "ais_messages": ais_status.get("messages"),
        "ais_frames_received": ais_status.get("frames_received"),
        "ais_rate_limited": ais_status.get("rate_limited"),
        "ais_rate_limited_for_seconds": ais_status.get("rate_limited_for_seconds"),
        "ais_last_error": ais_status.get("last_error"),
    })


@app.get("/stats/summary")
async def stats_summary() -> JSONResponse:
    """
    Get current aggregate statistics.
    
    Returns transaction counts, vessel count, sats spent, avg fee, uptime.
    """
    return JSONResponse(get_stats_snapshot())


def _parse_bbox(raw: str) -> Optional[tuple[float, float, float, float]]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        return None
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError:
        return None
    if min_lon > max_lon or min_lat > max_lat:
        return None
    return (min_lon, min_lat, max_lon, max_lat)


def _parse_near(raw: str) -> Optional[tuple[float, float]]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return (lat, lon)


@app.get("/vessels")
async def vessels_list(
    bbox: Optional[str] = Query(
        None, description="minLon,minLat,maxLon,maxLat"
    ),
    near: Optional[str] = Query(None, description="lat,lon"),
    radius_nm: float = Query(50.0, ge=0.1, le=2000.0),
    limit: int = Query(VESSELS_LIST_DEFAULT_LIMIT, ge=1, le=VESSELS_LIST_MAX_LIMIT),
) -> JSONResponse:
    """Return a compact list of vessels from the live AIS snapshot."""
    parsed_bbox = _parse_bbox(bbox) if bbox else None
    if bbox and parsed_bbox is None:
        return JSONResponse(
            {"status": "error", "message": "Invalid bbox. Use minLon,minLat,maxLon,maxLat"},
            status_code=400,
        )
    parsed_near = _parse_near(near) if near else None
    if near and parsed_near is None:
        return JSONResponse(
            {"status": "error", "message": "Invalid near. Use lat,lon"},
            status_code=400,
        )
    vessels = list_vessels(
        bbox=parsed_bbox,
        near=parsed_near,
        radius_nm=radius_nm,
        limit=limit,
    )
    return JSONResponse({"count": len(vessels), "vessels": vessels})


@app.get("/vessels/search")
async def vessels_search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(12, ge=1, le=50),
) -> JSONResponse:
    """Search vessels by MMSI, name, call sign, or IMO."""
    limited = _rate_limit_search(request)
    if limited is not None:
        return limited
    results = search_vessels(q, limit=limit)
    return JSONResponse({"query": q.strip(), "count": len(results), "results": results})


@app.get("/vessels/{mmsi}")
async def vessels_detail(mmsi: str) -> JSONResponse:
    """Return a single vessel by MMSI."""
    vessel = get_vessel(mmsi.strip())
    if vessel is None:
        return JSONResponse(
            {"status": "error", "message": "Vessel not found"},
            status_code=404,
        )
    return JSONResponse(vessel)


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


class BulkReserveUtxoItem(BaseModel):
    """One row for admin bulk reserve import (no indexers)."""

    txid: str = Field(..., min_length=64, max_length=64)
    vout: int = Field(..., ge=0)
    value_sat: int = Field(..., ge=1)


class BulkReserveImportBody(BaseModel):
    """POST body for /utxo/reserves/bulk-import."""

    utxos: list[BulkReserveUtxoItem] = Field(
        ...,
        max_length=25000,
        description="Confirmed unspent outputs for this wallet (txid, vout, value_sat).",
    )

    @field_validator("utxos")
    @classmethod
    def _non_empty(cls, v: list[BulkReserveUtxoItem]) -> list[BulkReserveUtxoItem]:
        if not v:
            raise ValueError("utxos must not be empty")
        return v


@app.post("/utxo/reserve")
async def register_reserve_utxo(body: ReserveUtxoBody) -> JSONResponse:
    """
    Record a `reserve` UTXO in Postgres for fan-out funding.

    Use the real confirmed txid, vout, and value (satoshis) from your wallet.
    For many rows without indexers, use `POST /utxo/reserves/bulk-import` (admin key).
    Vessel broadcasts only consume `pool` rows after fan-out.
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


def _admin_key_authorised(provided: Optional[str]) -> bool:
    if not OCEANCHAIN_ADMIN_API_KEY or provided is None:
        return False
    try:
        a = provided.encode("utf-8")
        b = OCEANCHAIN_ADMIN_API_KEY.encode("utf-8")
    except Exception:
        return False
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)


@app.post("/utxo/sync-reserves-woc")
async def sync_reserves_woc(
    x_oceanchain_admin_key: Optional[str] = Header(
        default=None,
        alias="X-OceanChain-Admin-Key",
    ),
) -> JSONResponse:
    """
    Bulk-import current unspent outputs for this node's P2PKH from WhatsOnChain
    as internal `reserve` rows (one HTTP round-trip + DB upsert).

    Requires `OCEANCHAIN_ADMIN_API_KEY` in `.env` and the same value in header
    `X-OceanChain-Admin-Key`. Bind the API to localhost or protect with a firewall;
    do not expose this key over untrusted networks without TLS.
    """
    if not OCEANCHAIN_ADMIN_API_KEY:
        return JSONResponse(
            {
                "status": "error",
                "message": "Set OCEANCHAIN_ADMIN_API_KEY in .env to enable this endpoint",
            },
            status_code=503,
        )
    if not _admin_key_authorised(x_oceanchain_admin_key):
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    try:
        result = await utxo_manager.sync_reserves_from_whatsonchain()
        return JSONResponse(result)
    except httpx.HTTPStatusError as e:
        logger.error("WOC sync HTTP error: %s", e, exc_info=True)
        return JSONResponse(
            {
                "status": "error",
                "message": f"WhatsOnChain HTTP {e.response.status_code}",
            },
            status_code=502,
        )
    except httpx.RequestError as e:
        logger.error("WOC sync request failed: %s", e, exc_info=True)
        return JSONResponse(
            {"status": "error", "message": f"WhatsOnChain unreachable: {e}"},
            status_code=502,
        )
    except Exception as e:
        logger.error("sync_reserves_woc failed: %s", e, exc_info=True)
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


@app.post("/utxo/reserves/bulk-import")
async def bulk_import_reserves(
    body: BulkReserveImportBody,
    x_oceanchain_admin_key: Optional[str] = Header(
        default=None,
        alias="X-OceanChain-Admin-Key",
    ),
) -> JSONResponse:
    """
    Upsert many `reserve` rows from a JSON payload — **no WhatsOnChain**.

    Use when indexers cannot serve your address (very large tx counts). Build the
    list from any source you trust: explorer CSV export, your own full node,
    `bitcoin-sv` RPC `listunspent`, a payment you sent to yourself (one output), etc.

    Same auth as `/utxo/sync-reserves-woc` (`OCEANCHAIN_ADMIN_API_KEY`).
    """
    if not OCEANCHAIN_ADMIN_API_KEY:
        return JSONResponse(
            {
                "status": "error",
                "message": "Set OCEANCHAIN_ADMIN_API_KEY in .env to enable this endpoint",
            },
            status_code=503,
        )
    if not _admin_key_authorised(x_oceanchain_admin_key):
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    try:
        rows: list[tuple[str, int, int]] = []
        for item in body.utxos:
            txid = item.txid.strip().lower()
            if any(c not in "0123456789abcdef" for c in txid):
                return JSONResponse(
                    {"status": "error", "message": f"Invalid txid (not 64 hex): {txid[:16]}…"},
                    status_code=400,
                )
            rows.append((txid, item.vout, item.value_sat))

        n, skipped_min = await utxo_manager.bulk_register_reserve_utxos(rows)
        metrics = await utxo_manager.reserve_funding_metrics()
        return JSONResponse(
            {
                "status": "ok",
                "upserted_rows": n,
                "skipped_below_reserve_min": skipped_min,
                "reserve_count": metrics["reserve_count"],
                "reserve_total_sat": metrics["reserve_total_sat"],
            }
        )
    except Exception as e:
        logger.error("bulk_import_reserves failed: %s", e, exc_info=True)
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
            refill_error = (
                utxo_manager.last_refill_error()
                or "No internal reserve UTXO set covers fan-out; POST /utxo/reserve first"
            )
            return JSONResponse(
                {
                    "status": "error",
                    "message": refill_error,
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
    record_vessel_tx(tx_event)

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
