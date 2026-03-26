"""
OceanChain Broadcaster Module

Handles submission of raw transactions to ARC-compatible endpoints with
GorillaPool Arcade as primary and TAAL as fallback.
"""

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

from config import (
    TAAL_API_KEY,
    GORILLA_ARC_URL,
    TAAL_ARC_URL,
    ARC_MAX_TIMEOUT_SECONDS,
    ARC_WAIT_FOR_STATUS,
    VERBOSE_ARC_LOGS,
)

logger = logging.getLogger(__name__)

_ARC_NETWORK_SUCCESS_STATUSES = {
    "SEEN_ON_NETWORK",
    "SEEN_IN_ORPHAN_MEMPOOL",
    "MINED",
}


def _arc_detail(msg: str, *args: Any) -> None:
    if VERBOSE_ARC_LOGS:
        logger.info(msg, *args)
    else:
        logger.debug(msg, *args)


class BroadcastError(Exception):
    """Exception raised when transaction broadcast fails on all endpoints."""
    
    def __init__(
        self,
        message: str,
        gorilla_error: Optional[str] = None,
        taal_error: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.gorilla_error = gorilla_error
        self.taal_error = taal_error


async def _submit_to_arc(
    client: httpx.AsyncClient,
    url: str,
    raw_tx_hex: str,
    broadcaster_name: str,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    Submit a transaction to an ARC endpoint.
    GorillaPool Arcade requires no API key. TAAL requires Bearer token.
    """
    start_time = time.monotonic()

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-WaitFor": ARC_WAIT_FOR_STATUS,
        "X-MaxTimeout": str(ARC_MAX_TIMEOUT_SECONDS),
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {"rawTx": raw_tx_hex}
    
    response = await client.post(
        url,
        headers=headers,
        json=payload,
        timeout=10.0,
    )
    
    latency_ms = (time.monotonic() - start_time) * 1000

    _arc_detail(
        "ARC submission to %s: http=%s latency=%.1fms wait_for=%s timeout=%ss",
        broadcaster_name,
        response.status_code,
        latency_ms,
        ARC_WAIT_FOR_STATUS,
        ARC_MAX_TIMEOUT_SECONDS,
    )

    if response.status_code >= 400:
        snippet = (response.text or "")[:2048]
        if VERBOSE_ARC_LOGS:
            logger.warning(
                "ARC error body from %s (status %s): %s",
                broadcaster_name,
                response.status_code,
                snippet or "<empty>",
            )
        else:
            logger.debug(
                "ARC error body from %s (status %s): %s",
                broadcaster_name,
                response.status_code,
                snippet or "<empty>",
            )

    response.raise_for_status()

    data = response.json()
    txid = data.get("txid") or data.get("txId") or data.get("hash")
    # Arcade returns txStatus (enum string); classic ARC uses status / returnResult.
    status = (
        data.get("status")
        or data.get("returnResult")
        or data.get("txStatus")
        or "unknown"
    )

    _arc_detail(
        "ARC response via %s: txid=%s txStatus=%s",
        broadcaster_name,
        txid,
        status,
    )

    if status not in _ARC_NETWORK_SUCCESS_STATUSES:
        raise BroadcastError(
            f"ARC returned txStatus={status!r}, not a network-seen success",
            gorilla_error=(
                f"{broadcaster_name}:{status}"
                if broadcaster_name == "gorillapool"
                else None
            ),
            taal_error=(
                f"{broadcaster_name}:{status}"
                if broadcaster_name == "taal"
                else None
            ),
        )
    
    return {
        "txid": txid,
        "broadcaster": broadcaster_name,
        "status": status,
    }


async def submit(raw_tx_hex: str) -> dict[str, Any]:
    """
    Submit a transaction with primary + fallback logic.
    
    Attempts GorillaPool Arcade first, with one retry on failure.
    Falls back to TAAL ARC if GorillaPool fails twice.
    
    Args:
        raw_tx_hex: Raw transaction hex string
        
    Returns:
        Dict with txid, broadcaster, status
        
    Raises:
        BroadcastError if all attempts fail
    """
    gorilla_error: Optional[str] = None
    taal_error: Optional[str] = None
    
    async with httpx.AsyncClient() as client:
        # Attempt 1: GorillaPool (no API key needed)
        try:
            return await _submit_to_arc(
                client, GORILLA_ARC_URL, raw_tx_hex, "gorillapool"
            )
        except Exception as e:
            gorilla_error = str(e)
            _arc_detail("GorillaPool attempt 1 failed: %s", e)
        
        # Wait before retry
        await asyncio.sleep(2.0)
        
        # Attempt 2: GorillaPool retry
        try:
            return await _submit_to_arc(
                client, GORILLA_ARC_URL, raw_tx_hex, "gorillapool"
            )
        except Exception as e:
            gorilla_error = str(e)
            _arc_detail("GorillaPool attempt 2 failed: %s", e)
        
        # Attempt 3: TAAL fallback when configured
        if TAAL_API_KEY:
            try:
                return await _submit_to_arc(
                    client, TAAL_ARC_URL, raw_tx_hex, "taal", api_key=TAAL_API_KEY
                )
            except Exception as e:
                taal_error = str(e)
                _arc_detail("TAAL fallback failed: %s", e)
    
    # All attempts failed
    raise BroadcastError(
        f"All broadcast attempts failed",
        gorilla_error=gorilla_error,
        taal_error=taal_error,
    )


async def submit_raw(raw_tx_hex: str) -> str:
    """
    Thin wrapper for fan-out transactions - GorillaPool Arcade only, no fallback.
    
    Fan-out failure should halt and alert, so we don't use fallback
    to avoid confusion about which outputs were created.
    
    Args:
        raw_tx_hex: Raw transaction hex string
        
    Returns:
        Transaction ID string
        
    Raises:
        Exception on failure (no fallback)
    """
    async with httpx.AsyncClient() as client:
        result = await _submit_to_arc(
            client, GORILLA_ARC_URL, raw_tx_hex, "gorillapool"
        )
        return result["txid"]
