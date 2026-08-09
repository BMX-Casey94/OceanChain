"""
Ocechain read-only API runner (local development).

Runs only the AIS ingest client and the public query endpoints, so the frontend
can be developed against real live vessel data without Postgres, a funded BSV
wallet, or any broadcasting. Nothing is written to chain by this process.

Requires only AISSTREAM_API_KEY in backend/.env.

    python backend/read_only_api.py

Binds to 127.0.0.1 by default. Mutating routes (/engine/*, /utxo/*) are rejected,
so this process cannot alter node state even if something reaches it.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from fastapi import Request
from fastapi.responses import JSONResponse

from config import AISSTREAM_API_KEY, VPS_API_PORT
from ais_client import ais_client
from api_server import app, update_vessel_count
from logging_config import configure_quiet_loggers
from vessel_api import set_vessel_snapshot_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
configure_quiet_loggers()
logger = logging.getLogger("read_only_api")

VESSEL_COUNT_REFRESH_SECONDS = 5


@app.middleware("http")
async def enforce_read_only(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        return JSONResponse(
            {
                "status": "error",
                "message": "This node is running in read-only mode; mutating endpoints are disabled.",
            },
            status_code=405,
        )
    return await call_next(request)


async def vessel_count_loop() -> None:
    """Keep /stats/summary's active_vessels aligned with the AIS snapshot."""
    while True:
        try:
            await asyncio.sleep(VESSEL_COUNT_REFRESH_SECONDS)
            update_vessel_count(ais_client.get_vessel_count())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Vessel count loop error: %s", e, exc_info=True)


async def serve(host: str, port: int) -> None:
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    logger.info("Read-only API listening on http://%s:%s", host, port)
    await server.serve()


async def main(host: str, port: int) -> None:
    if not AISSTREAM_API_KEY:
        logger.error(
            "AISSTREAM_API_KEY is required. Add it to backend/.env "
            "(free key from https://aisstream.io) and run again."
        )
        sys.exit(1)

    set_vessel_snapshot_provider(ais_client.get_current_snapshot)
    logger.info("Ocechain read-only mode — AIS ingest + query API only, no broadcasting")

    tasks = [
        asyncio.create_task(ais_client.run(), name="ais_client"),
        asyncio.create_task(vessel_count_loop(), name="vessel_count"),
        asyncio.create_task(serve(host, port), name="api_server"),
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ocechain read-only API (local dev)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=VPS_API_PORT, help="Bind port")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
