"""
Shared process-wide HTTP client.

All outbound HTTP (ARC broadcasts/polls, reaper status checks, indexer sync)
goes through one httpx.AsyncClient with keep-alive pooling. Constructing a
client per transaction meant hundreds of fresh TCP+TLS handshakes per second
at broadcast rate — observed in production as TIME_WAIT buildup, Cloudflare
connect timeouts against TAAL, and multi-second GorillaPool POST latencies.
One pooled client turns that into a handful of long-lived connections per
endpoint.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import httpx

_client: Optional[httpx.AsyncClient] = None


async def get_client() -> httpx.AsyncClient:
    """
    Return the shared client, creating it on first use.

    Construction is synchronous (no awaits), so the check-and-set below is
    atomic within the event loop and needs no lock.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=1024,
                max_keepalive_connections=512,
                keepalive_expiry=30.0,
            ),
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
    return _client


@asynccontextmanager
async def pooled_client() -> AsyncIterator[httpx.AsyncClient]:
    """Drop-in for `async with httpx.AsyncClient()` that yields the shared client without closing it."""
    yield await get_client()


async def close_client() -> None:
    """Close the shared client and its connection pool (process shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
