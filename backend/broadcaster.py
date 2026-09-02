"""
OceanChain Broadcaster Module

Handles submission of raw transactions to ARC-compatible endpoints with
GorillaPool Arcade as primary and TAAL as fallback. When ARC_DUAL_BROADCAST is
enabled and a TAAL key is configured, every tx is also POSTed to TAAL as a
fire-and-forget background task the hot path never awaits: two independent
operators injecting the tx is what makes it propagate to explorers, and when
the background POST lands it flips the tx's submit_mask TAAL bit so the
pending-reaper can require quorum (both endpoints reporting SEEN_ON_NETWORK+)
before unlocking change outputs.
"""

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Optional

import httpx

from config import (
    TAAL_API_KEY,
    GORILLA_ARC_URL,
    GORILLA_TX_FORMAT,
    TAAL_ARC_URL,
    ARC_DUAL_BROADCAST,
    ARC_MAX_TIMEOUT_SECONDS,
    ARC_WAIT_FOR_STATUS,
    VERBOSE_ARC_LOGS,
)
from broadcast_stats import broadcast_stats
from http_client import pooled_client

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


# submit_mask bits: which ARC endpoints accepted the tx into their pipeline.
SUBMIT_MASK_GORILLA = 1
SUBMIT_MASK_TAAL = 2

# Fire-and-forget TAAL POSTs (dual broadcast). TAAL's parent-aware validation
# regularly exceeds 5s for zero-conf chains, so the hot path never awaits it;
# the background task gets a generous budget and flips the TAAL submit_mask bit
# via the registered updater when it lands. The in-flight cap bounds task
# accumulation if TAAL stalls at broadcast rate.
_TAAL_BG_POST_TIMEOUT_SECONDS = 20.0
_TAAL_BG_MAX_IN_FLIGHT = 256
_taal_bg_in_flight = 0
_background_tasks: set[asyncio.Task] = set()
_MASK_UPDATER: Optional[Callable[[str], Awaitable[None]]] = None


def register_mask_updater(updater: Callable[[str], Awaitable[None]]) -> None:
    """
    Register the coroutine called with a txid when a background TAAL POST lands.
    main.py wires UTXOManager.mark_taal_accepted here at startup.
    """
    global _MASK_UPDATER
    _MASK_UPDATER = updater


async def _taal_background_post(
    client: httpx.AsyncClient, raw_tx_hex: str
) -> Optional[dict[str, Any]]:
    """
    POST to TAAL off the hot path. Returns the ARC result on success, None on
    any failure. On success the registered mask updater flips the TAAL bit on
    the tx's pending UTXO rows, tightening the reaper's quorum retroactively.
    """
    start = time.monotonic()
    try:
        result = await _post_to_arc(
            client,
            TAAL_ARC_URL,
            raw_tx_hex,
            "taal",
            api_key=TAAL_API_KEY,
            timeout=_TAAL_BG_POST_TIMEOUT_SECONDS,
        )
    except Exception as e:
        await _record_arc_attempt("taal", start, False)
        _arc_detail("TAAL background POST failed: %s", _safe_exc_text(e))
        return None

    await _record_arc_attempt("taal", start, True)
    txid = str(result.get("txid") or "")
    if txid and _MASK_UPDATER is not None:
        try:
            await _MASK_UPDATER(txid)
        except Exception as e:
            logger.warning(
                "TAAL mask update failed for %s: %s", txid[:16], _safe_exc_text(e)
            )
    return result


def _launch_taal_background_post(
    client: httpx.AsyncClient, raw_tx_hex: str
) -> Optional[asyncio.Task]:
    """
    Launch the TAAL POST as a tracked background task. Returns None when the
    in-flight cap is reached (the tx simply stays GorillaPool-only, mask=1).
    """
    global _taal_bg_in_flight
    if _taal_bg_in_flight >= _TAAL_BG_MAX_IN_FLIGHT:
        _arc_detail(
            "TAAL background POST skipped: %s already in flight",
            _TAAL_BG_MAX_IN_FLIGHT,
        )
        return None
    _taal_bg_in_flight += 1

    async def _runner() -> Optional[dict[str, Any]]:
        return await _taal_background_post(client, raw_tx_hex)

    task = asyncio.create_task(_runner())
    _background_tasks.add(task)

    def _on_done(done: asyncio.Task) -> None:
        # Done callbacks fire even when a task is cancelled before its first
        # step (a finally inside _runner would not), keeping the count exact.
        global _taal_bg_in_flight
        _taal_bg_in_flight -= 1
        _background_tasks.discard(done)

    task.add_done_callback(_on_done)
    return task


async def cancel_background_posts() -> None:
    """Cancel in-flight background TAAL POSTs (process shutdown)."""
    for task in list(_background_tasks):
        task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)


class BroadcastError(Exception):
    """Exception raised when transaction broadcast fails on all endpoints."""

    def __init__(
        self,
        message: str,
        gorilla_error: Optional[str] = None,
        taal_error: Optional[str] = None,
        tx_was_submitted: bool = False,
        posted: bool = False,
        submit_mask: int = 0,
    ) -> None:
        super().__init__(message)
        self.gorilla_error = gorilla_error
        self.taal_error = taal_error
        self.tx_was_submitted = tx_was_submitted
        # posted=True: this endpoint returned 2xx for the POST (it has the tx) and the
        # failure happened during status polling. posted=False: nothing suggests the
        # endpoint ever saw the tx.
        self.posted = posted
        # Endpoints confirmed to hold the tx (2xx POST, non-terminal status).
        self.submit_mask = submit_mask


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
        posted=during_status_poll,
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
            last_status = f"status_check_error:{_safe_exc_text(exc)}"
            _arc_detail(
                "ARC status poll via %s failed: attempt=%s txid=%s error=%s",
                broadcaster_name,
                poll_attempt,
                txid,
                _safe_exc_text(exc),
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
                posted=True,
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
        posted=True,
        **_error_kwargs(
            broadcaster_name,
            f"{broadcaster_name}:timeout_waiting_for:{ARC_WAIT_FOR_STATUS}:{last_status}",
        ),
    )


async def _post_to_arc(
    client: httpx.AsyncClient,
    url: str,
    raw_tx_hex: str,
    broadcaster_name: str,
    api_key: Optional[str] = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """
    POST a transaction to an ARC endpoint (no status polling).

    Returns once the endpoint has answered the POST; a 2xx with a non-terminal
    txStatus means the tx is in that operator's pipeline, which is all the
    dual-broadcast secondary path and the submit_mask need.

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
        timeout=timeout,
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

    # 2xx with an unusable body: the endpoint did receive the tx, so failures
    # here must read as posted=True for the conservative pending-change path.
    if not tx_status:
        raise BroadcastError(
            f"ARC response missing txStatus (api status={api_status!r})",
            posted=True,
            **_error_kwargs(
                broadcaster_name,
                f"{broadcaster_name}:missing_txStatus:{api_status}",
            ),
        )

    if not txid:
        raise BroadcastError(
            "ARC response missing txid",
            posted=True,
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

    return {
        "txid": txid,
        "broadcaster": broadcaster_name,
        "status": tx_status,
    }


async def _submit_to_arc(
    client: httpx.AsyncClient,
    url: str,
    raw_tx_hex: str,
    broadcaster_name: str,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    Submit a transaction to an ARC endpoint and poll until ARC_WAIT_FOR_STATUS.
    GorillaPool Arcade requires no API key. TAAL requires Bearer token.
    """
    result = await _post_to_arc(
        client, url, raw_tx_hex, broadcaster_name, api_key=api_key
    )

    if _target_status_reached(result["status"]):
        return result

    return await _poll_arc_status(
        client,
        url,
        str(result["txid"]),
        broadcaster_name,
        api_key=api_key,
    )


async def submit(
    raw_tx_hex: str,
    *,
    gorilla_tx_hex: Optional[str] = None,
) -> dict[str, Any]:
    """
    Submit a transaction: dual broadcast when configured, else primary + fallback.

    Dual mode (ARC_DUAL_BROADCAST=1 and TAAL_API_KEY set): POST to GorillaPool and
    TAAL concurrently, then poll the primary to ARC_WAIT_FOR_STATUS. Two independent
    operators holding the tx is what makes it reach explorers; the reaper quorum-
    checks both endpoints off the hot path. A TAAL failure never fails the broadcast
    while GorillaPool succeeds.

    Single mode: GorillaPool Arcade first, one retry on non-terminal failure, then
    TAAL ARC fallback when configured.
    
    Args:
        raw_tx_hex: Standard raw transaction hex string (always used for TAAL path).
        gorilla_tx_hex: Optional Gorilla-specific payload hex (e.g. EF/TEF) sent
            according to GORILLA_TX_FORMAT.
        
    Returns:
        Dict with txid, broadcaster, status, submit_mask (bit0=gorillapool,
        bit1=taal: endpoints confirmed to hold the tx — the reaper's quorum input)
        
    Raises:
        BroadcastError if all attempts fail
    """
    if ARC_DUAL_BROADCAST and TAAL_API_KEY:
        return await _submit_dual(raw_tx_hex, gorilla_tx_hex=gorilla_tx_hex)
    return await _submit_sequential(raw_tx_hex, gorilla_tx_hex=gorilla_tx_hex)


def _is_terminal_error_text(text: str) -> bool:
    return any(s in text for s in ("terminal failure", "REJECTED", "DOUBLE_SPEND"))


async def _submit_sequential(
    raw_tx_hex: str,
    *,
    gorilla_tx_hex: Optional[str] = None,
) -> dict[str, Any]:
    """
    Primary + fallback logic: GorillaPool Arcade first with one retry on
    non-terminal failure, then TAAL ARC fallback when configured.
    """
    gorilla_error: Optional[str] = None
    taal_error: Optional[str] = None
    submit_mask = 0
    
    async with pooled_client() as client:
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
                result["submit_mask"] = SUBMIT_MASK_GORILLA
                return result
            except BroadcastError as e:
                await _record_arc_attempt("gorillapool", attempt_start, False)
                gorilla_error = _safe_exc_text(e)
                if _is_terminal_error_text(gorilla_error):
                    gorilla_terminal = True
                    _arc_detail(
                        "GorillaPool attempt 1 terminal rejection, skipping retry: %s",
                        gorilla_error,
                    )
                else:
                    if e.posted:
                        # POST landed but polling failed: GorillaPool holds the tx.
                        submit_mask |= SUBMIT_MASK_GORILLA
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
                    result["submit_mask"] = SUBMIT_MASK_GORILLA
                    return result
                except Exception as e:
                    await _record_arc_attempt("gorillapool", attempt_start, False)
                    gorilla_error = _safe_exc_text(e)
                    if (
                        isinstance(e, BroadcastError)
                        and e.posted
                        and not _is_terminal_error_text(gorilla_error)
                    ):
                        submit_mask |= SUBMIT_MASK_GORILLA
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
                result["submit_mask"] = submit_mask | SUBMIT_MASK_TAAL
                return result
            except Exception as e:
                await _record_arc_attempt("taal", attempt_start, False)
                taal_error = _safe_exc_text(e)
                if (
                    isinstance(e, BroadcastError)
                    and e.posted
                    and not _is_terminal_error_text(taal_error)
                ):
                    submit_mask |= SUBMIT_MASK_TAAL
                _arc_detail("TAAL fallback failed: %s", taal_error)

    raise BroadcastError(
        "All broadcast attempts failed",
        gorilla_error=gorilla_error,
        taal_error=taal_error,
        tx_was_submitted=tx_was_submitted,
        submit_mask=submit_mask,
    )


async def _submit_dual(
    raw_tx_hex: str,
    *,
    gorilla_tx_hex: Optional[str] = None,
) -> dict[str, Any]:
    """
    Dual broadcast: GorillaPool is the synchronous hot path (POST + poll to
    ARC_WAIT_FOR_STATUS). The TAAL POST runs as a background task the success
    path never awaits — TAAL's parent-aware validation of zero-conf chains
    regularly exceeds 5s, and awaiting it taxed every tx with a ~5s floor for
    little acceptance. When a background POST lands, the registered mask
    updater flips the TAAL bit on the tx's pending UTXO rows so the reaper's
    quorum tightens retroactively. On the GorillaPool failure path the
    in-flight TAAL task is awaited: async in the success path, synchronous
    exactly when it is the safety net.
    """
    gorilla_error: Optional[str] = None
    taal_error: Optional[str] = None

    async with pooled_client() as client:
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

        # Launched before the GorillaPool POST so TAAL's slow validation
        # overlaps the hot path instead of extending it.
        taal_task = _launch_taal_background_post(client, raw_tx_hex)

        post_start = time.monotonic()
        g_res: Any = None
        if gorilla_submit_enabled:
            try:
                g_res = await _post_to_arc(
                    client, GORILLA_ARC_URL, selected_gorilla_tx_hex, "gorillapool"
                )
            except Exception as e:
                g_res = e

        submit_mask = 0
        if isinstance(g_res, dict):
            submit_mask |= SUBMIT_MASK_GORILLA

        if isinstance(g_res, dict):
            try:
                if _target_status_reached(g_res["status"]):
                    result = g_res
                else:
                    result = await _poll_arc_status(
                        client, GORILLA_ARC_URL, str(g_res["txid"]), "gorillapool"
                    )
                await _record_arc_attempt("gorillapool", post_start, True)
                result["submit_mask"] = submit_mask
                return result
            except Exception as e:
                await _record_arc_attempt("gorillapool", post_start, False)
                gorilla_error = _safe_exc_text(e)
                if _is_terminal_error_text(gorilla_error):
                    # GorillaPool definitively dropped it; only TAAL can vouch now.
                    submit_mask &= ~SUBMIT_MASK_GORILLA
                _arc_detail(
                    "GorillaPool dual-broadcast poll failed: %s", gorilla_error
                )
        elif gorilla_submit_enabled:
            if isinstance(g_res, Exception):
                gorilla_error = _safe_exc_text(g_res)
            await _record_arc_attempt("gorillapool", post_start, False)
            if gorilla_error and not _is_terminal_error_text(gorilla_error):
                await asyncio.sleep(2.0)
                retry_start = time.monotonic()
                try:
                    result = await _submit_to_arc(
                        client,
                        GORILLA_ARC_URL,
                        selected_gorilla_tx_hex,
                        "gorillapool",
                    )
                    await _record_arc_attempt("gorillapool", retry_start, True)
                    submit_mask |= SUBMIT_MASK_GORILLA
                    result["submit_mask"] = submit_mask
                    return result
                except Exception as e:
                    await _record_arc_attempt("gorillapool", retry_start, False)
                    gorilla_error = _safe_exc_text(e)
                    if (
                        isinstance(e, BroadcastError)
                        and e.posted
                        and not _is_terminal_error_text(gorilla_error)
                    ):
                        submit_mask |= SUBMIT_MASK_GORILLA
                    _arc_detail(
                        "GorillaPool dual-broadcast retry failed: %s", gorilla_error
                    )

        # GorillaPool could not complete; TAAL is the safety net. The background
        # POST was launched at submit start, so this await usually returns at
        # once. Ride TAAL to the target status if its POST landed.
        t_res: Any = None
        if taal_task is not None:
            try:
                t_res = await taal_task
            except asyncio.CancelledError:
                raise
            except Exception:
                t_res = None
        if isinstance(t_res, dict):
            submit_mask |= SUBMIT_MASK_TAAL
            try:
                if _target_status_reached(t_res["status"]):
                    result = dict(t_res)
                else:
                    result = await _poll_arc_status(
                        client,
                        TAAL_ARC_URL,
                        str(t_res["txid"]),
                        "taal",
                        api_key=TAAL_API_KEY,
                    )
                result["broadcaster"] = "taal"
                result["submit_mask"] = submit_mask
                return result
            except Exception as e:
                taal_error = _safe_exc_text(e)
                _arc_detail(
                    "TAAL completion after GorillaPool failure failed: %s", taal_error
                )
        elif taal_task is None:
            taal_error = "background POST skipped (in-flight cap reached)"
        else:
            taal_error = "background POST failed (see earlier TAAL log lines)"

    raise BroadcastError(
        "All broadcast attempts failed",
        gorilla_error=gorilla_error,
        taal_error=taal_error,
        tx_was_submitted=True,
        submit_mask=submit_mask,
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

    async with pooled_client() as client:
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
                    _safe_exc_text(exc),
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


async def _get_status_one(
    client: httpx.AsyncClient,
    broadcaster_name: str,
    submit_url: str,
    api_key: Optional[str],
    txid: str,
) -> Optional[str]:
    """
    One lightweight GET /tx/{txid} against one ARC endpoint.

    Returns the normalised txStatus, "NOT_FOUND" on a clean 404, or None on
    transport/HTTP errors — None must read as "unknown", never as dead.
    """
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
        _arc_detail(
            "Status check via %s failed for %s: %s",
            broadcaster_name,
            txid[:16],
            _safe_exc_text(exc),
        )
        return None

    if response.status_code == 404:
        return "NOT_FOUND"
    if response.status_code >= 400:
        _arc_detail(
            "Status check via %s HTTP %s for %s",
            broadcaster_name,
            response.status_code,
            txid[:16],
        )
        return None

    try:
        data = response.json()
    except ValueError:
        return None
    _, _, tx_status = _extract_arc_response(data)
    return tx_status or None


async def check_tx_status_all(txid: str) -> dict[str, Optional[str]]:
    """
    Poll every configured ARC endpoint concurrently; return per-endpoint status.

    Values: normalised txStatus, "NOT_FOUND" (clean 404), or None (transport/HTTP
    error — unknown, never dead). "gorillapool" is always present; "taal" appears
    when TAAL_API_KEY is configured. Used by the pending-coin reaper for
    quorum-gated promotion.
    """
    endpoints: list[tuple[str, str, Optional[str]]] = [
        ("gorillapool", GORILLA_ARC_URL, None)
    ]
    if TAAL_API_KEY:
        endpoints.append(("taal", TAAL_ARC_URL, TAAL_API_KEY))

    async with pooled_client() as client:
        results = await asyncio.gather(
            *(
                _get_status_one(client, name, url, key, txid)
                for name, url, key in endpoints
            )
        )
    return {name: status for (name, _, _), status in zip(endpoints, results)}


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
    async with pooled_client() as client:
        result = await _submit_to_arc(
            client, GORILLA_ARC_URL, raw_tx_hex, "gorillapool"
        )
        return result["txid"]
