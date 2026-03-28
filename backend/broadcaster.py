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

_ARC_STATUS_RANK = {
    "UNKNOWN": 0,
    "QUEUED": 1,
    "RECEIVED": 2,
    "STORED": 3,
    "ANNOUNCED_TO_NETWORK": 4,
    "REQUESTED_BY_NETWORK": 5,
    "SENT_TO_NETWORK": 6,
    "ACCEPTED_BY_NETWORK": 7,
    "SEEN_ON_NETWORK": 8,
    "SEEN_IN_ORPHAN_MEMPOOL": 8,
    "MINED": 9,
    "CONFIRMED": 10,
    "IMMUTABLE": 11,
}

_ARC_NETWORK_SUCCESS_STATUSES = {
    "SEEN_ON_NETWORK",
    "SEEN_IN_ORPHAN_MEMPOOL",
    "MINED",
}

_ARC_FINAL_FAILURE_STATUSES = {
    "DOUBLE_SPEND_ATTEMPTED",
    "REJECTED",
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


def _normalise_tx_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value).strip().upper().replace(" ", "_")


def _extract_arc_response(data: dict[str, Any]) -> tuple[Optional[str], Any, Optional[str]]:
    txid = data.get("txid") or data.get("txId") or data.get("hash")
    api_status = data.get("status")
    tx_status_raw = data.get("txStatus") or data.get("returnResult")
    if tx_status_raw is None and isinstance(api_status, str):
        tx_status_raw = api_status
    return txid, api_status, _normalise_tx_status(tx_status_raw)


def _target_status_reached(tx_status: str) -> bool:
    if tx_status in _ARC_NETWORK_SUCCESS_STATUSES:
        return True
    target_rank = _ARC_STATUS_RANK.get(ARC_WAIT_FOR_STATUS)
    current_rank = _ARC_STATUS_RANK.get(tx_status)
    return (
        target_rank is not None
        and current_rank is not None
        and current_rank >= target_rank
    )


def _status_url(submit_url: str, txid: str) -> str:
    return f"{submit_url.rstrip('/')}/{txid}"


def _error_kwargs(broadcaster_name: str, detail: str) -> dict[str, Optional[str]]:
    return {
        "gorilla_error": detail if broadcaster_name == "gorillapool" else None,
        "taal_error": detail if broadcaster_name == "taal" else None,
    }


def _safe_exc_text(exc: Exception) -> str:
    text = str(exc).strip()
    if text:
        return text
    return exc.__class__.__name__


def _response_snippet(response: httpx.Response, limit: int = 300) -> str:
    text = (response.text or "").strip()
    if not text:
        return "<empty>"
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _arc_http_detail(
    broadcaster_name: str,
    status_code: int,
    snippet: str,
    *,
    during_status_poll: bool = False,
) -> str:
    phase = "status poll" if during_status_poll else "submit"
    detail = f"{broadcaster_name} {phase} HTTP {status_code}: {snippet}"
    if broadcaster_name == "gorillapool" and status_code == 467:
        detail += (
            " Validator/generic rejection from Arcade; check validator logs for "
            "PreviousTx / merkle-path details. RawTx-only chained spends may need EF/BEEF."
        )
    elif broadcaster_name == "taal" and status_code == 460:
        detail += (
            " TAAL could not transform the tx to extended format; parent tx data may be "
            "missing or not yet visible."
        )
    return detail


def _raise_arc_http_error(
    response: httpx.Response,
    broadcaster_name: str,
    *,
    during_status_poll: bool = False,
) -> None:
    snippet = _response_snippet(response)
    detail = _arc_http_detail(
        broadcaster_name,
        response.status_code,
        snippet,
        during_status_poll=during_status_poll,
    )
    raise BroadcastError(
        detail,
        **_error_kwargs(
            broadcaster_name,
            f"{broadcaster_name}:http_{response.status_code}:{snippet}",
        ),
    )


async def _poll_arc_status(
    client: httpx.AsyncClient,
    submit_url: str,
    txid: str,
    broadcaster_name: str,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    status_url = _status_url(submit_url, txid)
    deadline = time.monotonic() + ARC_MAX_TIMEOUT_SECONDS
    delay_seconds = 0.5
    poll_attempt = 0
    last_status: Optional[str] = None

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        await asyncio.sleep(min(delay_seconds, remaining))
        poll_attempt += 1

        try:
            response = await client.get(
                status_url,
                headers=headers,
                timeout=min(10.0, max(1.0, remaining)),
            )
        except httpx.HTTPError as exc:
            last_status = f"status_check_error:{exc}"
            _arc_detail(
                "ARC status poll via %s failed: attempt=%s txid=%s error=%s",
                broadcaster_name,
                poll_attempt,
                txid,
                exc,
            )
            delay_seconds = min(delay_seconds * 1.5, 2.0)
            continue

        _arc_detail(
            "ARC status poll via %s: attempt=%s http=%s txid=%s",
            broadcaster_name,
            poll_attempt,
            response.status_code,
            txid,
        )

        if response.status_code == 404:
            last_status = "NOT_FOUND"
            delay_seconds = min(delay_seconds * 1.5, 2.0)
            continue

        if response.status_code >= 400:
            snippet = _response_snippet(response, limit=2048)
            if VERBOSE_ARC_LOGS:
                logger.warning(
                    "ARC status error body from %s (status %s): %s",
                    broadcaster_name,
                    response.status_code,
                    snippet,
                )
            else:
                logger.debug(
                    "ARC status error body from %s (status %s): %s",
                    broadcaster_name,
                    response.status_code,
                    snippet,
                )
            _raise_arc_http_error(
                response,
                broadcaster_name,
                during_status_poll=True,
            )

        data = response.json()
        _, api_status, tx_status = _extract_arc_response(data)

        _arc_detail(
            "ARC status via %s: txid=%s txStatus=%s apiStatus=%s",
            broadcaster_name,
            txid,
            tx_status,
            api_status,
        )

        if not tx_status:
            raise BroadcastError(
                f"ARC status response missing txStatus for {txid} (api status={api_status!r})",
                **_error_kwargs(
                    broadcaster_name,
                    f"{broadcaster_name}:missing_txStatus:{api_status}",
                ),
            )

        if tx_status in _ARC_FINAL_FAILURE_STATUSES:
            raise BroadcastError(
                f"ARC returned terminal failure txStatus={tx_status!r}",
                **_error_kwargs(broadcaster_name, f"{broadcaster_name}:{tx_status}"),
            )

        if _target_status_reached(tx_status):
            return {
                "txid": txid,
                "broadcaster": broadcaster_name,
                "status": tx_status,
            }

        last_status = tx_status
        delay_seconds = min(delay_seconds * 1.5, 2.0)

    if last_status == "RECEIVED":
        timeout_message = (
            f"{broadcaster_name} kept the tx at RECEIVED for {ARC_MAX_TIMEOUT_SECONDS}s "
            f"without reaching {ARC_WAIT_FOR_STATUS}; local acceptance did not turn into "
            "network propagation"
        )
    else:
        timeout_message = (
            f"ARC did not reach {ARC_WAIT_FOR_STATUS!r} within {ARC_MAX_TIMEOUT_SECONDS}s "
            f"(last status={last_status!r})"
        )
    raise BroadcastError(
        timeout_message,
        **_error_kwargs(
            broadcaster_name,
            f"{broadcaster_name}:timeout_waiting_for:{ARC_WAIT_FOR_STATUS}:{last_status}",
        ),
    )


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
        "Accept": "application/json",
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
        "ARC submission to %s: http=%s latency=%.1fms target_status=%s timeout=%ss",
        broadcaster_name,
        response.status_code,
        latency_ms,
        ARC_WAIT_FOR_STATUS,
        ARC_MAX_TIMEOUT_SECONDS,
    )

    if response.status_code >= 400:
        snippet = _response_snippet(response, limit=2048)
        if VERBOSE_ARC_LOGS:
            logger.warning(
                "ARC error body from %s (status %s): %s",
                broadcaster_name,
                response.status_code,
                snippet,
            )
        else:
            logger.debug(
                "ARC error body from %s (status %s): %s",
                broadcaster_name,
                response.status_code,
                snippet,
            )
        _raise_arc_http_error(response, broadcaster_name)

    data = response.json()
    txid, api_status, tx_status = _extract_arc_response(data)

    _arc_detail(
        "ARC response via %s: txid=%s txStatus=%s apiStatus=%s",
        broadcaster_name,
        txid,
        tx_status,
        api_status,
    )

    if not tx_status:
        raise BroadcastError(
            f"ARC response missing txStatus (api status={api_status!r})",
            **_error_kwargs(
                broadcaster_name,
                f"{broadcaster_name}:missing_txStatus:{api_status}",
            ),
        )

    if not txid:
        raise BroadcastError(
            "ARC response missing txid",
            **_error_kwargs(broadcaster_name, f"{broadcaster_name}:missing_txid"),
        )

    if tx_status in _ARC_FINAL_FAILURE_STATUSES:
        raise BroadcastError(
            f"ARC returned terminal failure txStatus={tx_status!r}",
            **_error_kwargs(broadcaster_name, f"{broadcaster_name}:{tx_status}"),
        )

    if _target_status_reached(tx_status):
        return {
            "txid": txid,
            "broadcaster": broadcaster_name,
            "status": tx_status,
        }

    return await _poll_arc_status(
        client,
        url,
        str(txid),
        broadcaster_name,
        api_key=api_key,
    )


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
            gorilla_error = _safe_exc_text(e)
            _arc_detail("GorillaPool attempt 1 failed: %s", gorilla_error)
        
        # Wait before retry
        await asyncio.sleep(2.0)
        
        # Attempt 2: GorillaPool retry
        try:
            return await _submit_to_arc(
                client, GORILLA_ARC_URL, raw_tx_hex, "gorillapool"
            )
        except Exception as e:
            gorilla_error = _safe_exc_text(e)
            _arc_detail("GorillaPool attempt 2 failed: %s", gorilla_error)
        
        # Attempt 3: TAAL fallback when configured
        if TAAL_API_KEY:
            try:
                return await _submit_to_arc(
                    client, TAAL_ARC_URL, raw_tx_hex, "taal", api_key=TAAL_API_KEY
                )
            except Exception as e:
                taal_error = _safe_exc_text(e)
                _arc_detail("TAAL fallback failed: %s", taal_error)
    
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
