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
    GORILLA_TX_FORMAT,
    TAAL_ARC_URL,
    ARC_MAX_TIMEOUT_SECONDS,
    ARC_WAIT_FOR_STATUS,
    VERBOSE_ARC_LOGS,
)
from broadcast_stats import broadcast_stats

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
    "SEEN_MULTIPLE_NODES": 8,
    "SEEN_IN_ORPHAN_MEMPOOL": 8,
    "MINED": 9,
    "CONFIRMED": 10,
    "IMMUTABLE": 11,
}

_ARC_NETWORK_SUCCESS_STATUSES = {
    "ANNOUNCED_TO_NETWORK",
    "REQUESTED_BY_NETWORK",
    "SENT_TO_NETWORK",
    "ACCEPTED_BY_NETWORK",
    "SEEN_ON_NETWORK",
    "SEEN_MULTIPLE_NODES",
    "SEEN_IN_ORPHAN_MEMPOOL",
    "MINED",
    "CONFIRMED",
    "IMMUTABLE",
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


async def _record_arc_attempt(broadcaster_name: str, start: float, success: bool) -> None:
    """Record endpoint attempt stats; accounting must never break broadcasting."""
    try:
        await broadcast_stats.record_arc_attempt(
            broadcaster_name, success, (time.monotonic() - start) * 1000
        )
    except Exception:
        pass


class BroadcastError(Exception):
    """Exception raised when transaction broadcast fails on all endpoints."""
    
    def __init__(
        self,
        message: str,
        gorilla_error: Optional[str] = None,
        taal_error: Optional[str] = None,
        tx_was_submitted: bool = False,
    ) -> None:
        super().__init__(message)
        self.gorilla_error = gorilla_error
        self.taal_error = taal_error
        self.tx_was_submitted = tx_was_submitted


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


def _select_gorilla_tx_hex(
    raw_tx_hex: str,
    gorilla_tx_hex: Optional[str],
) -> tuple[str, str]:
    """
    Pick Gorilla payload hex according to GORILLA_TX_FORMAT.

    Returns:
        (tx_hex_to_send, format_label)
    """
    mode = GORILLA_TX_FORMAT
    if mode == "raw":
        return raw_tx_hex, "raw"
    if mode == "ef":
        if gorilla_tx_hex:
            return gorilla_tx_hex, "ef"
        raise BroadcastError(
            "GORILLA_TX_FORMAT=ef but no EF payload was supplied",
            gorilla_error="gorillapool:missing_ef_payload",
        )
    # mode == "auto" (validated in config)
    if gorilla_tx_hex:
        return gorilla_tx_hex, "ef"
    return raw_tx_hex, "raw"


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
            detail = data.get("detail") or data.get("extraInfo") or ""
            if detail:
                logger.warning(
                    "ARC terminal %s from %s during poll (txid=%s): %s",
                    tx_status,
                    broadcaster_name,
                    txid,
                    detail,
                )
            raise BroadcastError(
                f"ARC returned terminal failure txStatus={tx_status!r}: {detail}" if detail
                else f"ARC returned terminal failure txStatus={tx_status!r}",
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
        detail = data.get("detail") or data.get("extraInfo") or ""
        if detail:
            logger.warning(
                "ARC terminal %s from %s (txid=%s): %s",
                tx_status,
                broadcaster_name,
                txid,
                detail,
            )
        raise BroadcastError(
            f"ARC returned terminal failure txStatus={tx_status!r}: {detail}" if detail
            else f"ARC returned terminal failure txStatus={tx_status!r}",
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


async def submit(
    raw_tx_hex: str,
    *,
    gorilla_tx_hex: Optional[str] = None,
) -> dict[str, Any]:
    """
    Submit a transaction with primary + fallback logic.
    
    Attempts GorillaPool Arcade first, with one retry on failure.
    Falls back to TAAL ARC if GorillaPool fails twice.
    
    Args:
        raw_tx_hex: Standard raw transaction hex string (always used for TAAL path).
        gorilla_tx_hex: Optional Gorilla-specific payload hex (e.g. EF/TEF) sent
            according to GORILLA_TX_FORMAT.
        
    Returns:
        Dict with txid, broadcaster, status
        
    Raises:
        BroadcastError if all attempts fail
    """
    gorilla_error: Optional[str] = None
    taal_error: Optional[str] = None
    
    async with httpx.AsyncClient() as client:
        gorilla_submit_enabled = True
        selected_gorilla_tx_hex = raw_tx_hex
        try:
            selected_gorilla_tx_hex, gorilla_fmt = _select_gorilla_tx_hex(
                raw_tx_hex,
                gorilla_tx_hex,
            )
            _arc_detail(
                "GorillaPool submission format selected: %s (GORILLA_TX_FORMAT=%s)",
                gorilla_fmt,
                GORILLA_TX_FORMAT,
            )
        except BroadcastError as fmt_err:
            gorilla_submit_enabled = False
            gorilla_error = _safe_exc_text(fmt_err)
            _arc_detail("Skipping GorillaPool submit: %s", gorilla_error)

        tx_was_submitted = False
        gorilla_terminal = False

        if gorilla_submit_enabled:
            # Attempt 1: GorillaPool (no API key needed)
            attempt_start = time.monotonic()
            try:
                tx_was_submitted = True
                result = await _submit_to_arc(
                    client,
                    GORILLA_ARC_URL,
                    selected_gorilla_tx_hex,
                    "gorillapool",
                )
                await _record_arc_attempt("gorillapool", attempt_start, True)
                return result
            except BroadcastError as e:
                await _record_arc_attempt("gorillapool", attempt_start, False)
                gorilla_error = _safe_exc_text(e)
                if any(s in gorilla_error for s in ("terminal failure", "REJECTED", "DOUBLE_SPEND")):
                    gorilla_terminal = True
                    _arc_detail(
                        "GorillaPool attempt 1 terminal rejection, skipping retry: %s",
                        gorilla_error,
                    )
                else:
                    _arc_detail("GorillaPool attempt 1 failed: %s", gorilla_error)
            except Exception as e:
                await _record_arc_attempt("gorillapool", attempt_start, False)
                gorilla_error = _safe_exc_text(e)
                _arc_detail("GorillaPool attempt 1 failed: %s", gorilla_error)

            if not gorilla_terminal:
                await asyncio.sleep(2.0)
                # Attempt 2: GorillaPool retry (only for non-terminal failures)
                attempt_start = time.monotonic()
                try:
                    tx_was_submitted = True
                    result = await _submit_to_arc(
                        client,
                        GORILLA_ARC_URL,
                        selected_gorilla_tx_hex,
                        "gorillapool",
                    )
                    await _record_arc_attempt("gorillapool", attempt_start, True)
                    return result
                except Exception as e:
                    await _record_arc_attempt("gorillapool", attempt_start, False)
                    gorilla_error = _safe_exc_text(e)
                    _arc_detail("GorillaPool attempt 2 failed: %s", gorilla_error)

        # TAAL fallback when configured
        if TAAL_API_KEY:
            attempt_start = time.monotonic()
            try:
                tx_was_submitted = True
                result = await _submit_to_arc(
                    client, TAAL_ARC_URL, raw_tx_hex, "taal", api_key=TAAL_API_KEY
                )
                await _record_arc_attempt("taal", attempt_start, True)
                return result
            except Exception as e:
                await _record_arc_attempt("taal", attempt_start, False)
                taal_error = _safe_exc_text(e)
                _arc_detail("TAAL fallback failed: %s", taal_error)
    
    raise BroadcastError(
        "All broadcast attempts failed",
        gorilla_error=gorilla_error,
        taal_error=taal_error,
        tx_was_submitted=tx_was_submitted,
    )


def arc_status_rank(status: str) -> Optional[int]:
    """Propagation rank for a normalised ARC status, or None if unranked."""
    return _ARC_STATUS_RANK.get(status)


def is_final_failure_status(status: str) -> bool:
    """True when ARC will never accept the tx (safe to quarantine its outputs)."""
    return status in _ARC_FINAL_FAILURE_STATUSES


async def check_tx_status(txid: str) -> Optional[str]:
    """
    Single lightweight status poll for one tx — no retries, no submit.

    Used by the pending-coin reaper to learn whether an accepted tx actually
    propagated. GorillaPool first; TAAL as fallback when configured (a tx that
    went out via TAAL fallback may not be known to Gorilla yet).

    Returns the normalised txStatus string ("SEEN_ON_NETWORK", "PENDING_RETRY",
    "NOT_FOUND", …) or None on transport/HTTP errors — callers must treat None
    as "unknown, try again later", never as dead.
    """
    endpoints: list[tuple[str, str, Optional[str]]] = [("gorillapool", GORILLA_ARC_URL, None)]
    if TAAL_API_KEY:
        endpoints.append(("taal", TAAL_ARC_URL, TAAL_API_KEY))

    saw_not_found = False
    saw_transport_error = False

    async with httpx.AsyncClient() as client:
        for broadcaster_name, submit_url, api_key in endpoints:
            headers: dict[str, str] = {"Accept": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            try:
                response = await client.get(
                    _status_url(submit_url, txid),
                    headers=headers,
                    timeout=10.0,
                )
            except httpx.HTTPError as exc:
                saw_transport_error = True
                _arc_detail(
                    "Status check via %s failed for %s: %s",
                    broadcaster_name,
                    txid[:16],
                    exc,
                )
                continue

            if response.status_code == 404:
                saw_not_found = True
                continue
            if response.status_code >= 400:
                saw_transport_error = True
                _arc_detail(
                    "Status check via %s HTTP %s for %s",
                    broadcaster_name,
                    response.status_code,
                    txid[:16],
                )
                continue

            try:
                data = response.json()
            except ValueError:
                saw_transport_error = True
                continue
            _, _, tx_status = _extract_arc_response(data)
            if tx_status:
                return tx_status

    # Definitive "no endpoint knows this tx" only when nothing errored — a transport
    # failure must never be read as proof of death.
    if saw_not_found and not saw_transport_error:
        return "NOT_FOUND"
    return None


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
