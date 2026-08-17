"""
Ocechain AIS Client Module

Persistent async WebSocket client that connects to AISstream.io
and maintains a live snapshot of vessel positions.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from config import (
    AISSTREAM_API_KEY,
    AISSTREAM_FILTER_MESSAGE_TYPES,
    AISSTREAM_WS_URL,
    SUPPORTED_AIS_STATIC_MESSAGE_TYPES,
)

logger = logging.getLogger(__name__)

# When timestamps tie, prefer higher-detail sources (see merge rules).
SOURCE_DETAIL_RANK: dict[str, int] = {
    "PositionReport": 40,
    "ExtendedClassBPositionReport": 30,
    "StandardClassBPositionReport": 25,
    "LongRangeAisBroadcastMessage": 10,
}


def _meta_str(meta: dict[str, Any], *keys: str, max_len: int = 0) -> str:
    for k in keys:
        v = meta.get(k)
        if v is None or v == "":
            continue
        s = str(v).strip()
        if not s:
            continue
        if max_len and len(s) > max_len:
            return s[: max_len - 1] + "…"
        return s
    return ""


def _mmsi_from_body(body: dict[str, Any], metadata: dict[str, Any]) -> str:
    uid = body.get("UserID")
    if uid is not None:
        return str(uid)
    return str(metadata.get("MMSI", "")).strip()


def _timestamp_from_metadata(metadata: dict[str, Any]) -> int:
    time_utc_str = metadata.get("time_utc", "")
    try:
        timestamp_dt = datetime.fromisoformat(time_utc_str.replace("Z", "+00:00"))
        return int(timestamp_dt.timestamp())
    except (ValueError, AttributeError, TypeError):
        return int(datetime.utcnow().timestamp())


def _heading_from_raw(raw: Any) -> int:
    if raw is None or raw == 511:
        return 0xFFFF
    try:
        return int(raw) & 0xFFFF
    except (TypeError, ValueError):
        return 0xFFFF


def _sog_knots(body: dict[str, Any]) -> float:
    """AISstream Class A PositionReport uses Sog (knots). 102.3 = not available."""
    raw = body.get("Sog", body.get("SpeedOverGround", body.get("SOG")))
    try:
        sog = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if sog >= 102.2:
        return 0.0
    return max(0.0, sog)


def _metadata_strings(metadata: dict[str, Any]) -> dict[str, Any]:
    ship_name = _meta_str(metadata, "ShipName", "shipName", max_len=48)
    call_sign = _meta_str(metadata, "CallSign", "Callsign", "callSign", max_len=12)
    destination = _meta_str(metadata, "Destination", "destination", max_len=42)
    imo = _meta_str(metadata, "ImoNumber", "IMO", "imo", max_len=12)
    ship_type_raw = metadata.get("ShipType") or metadata.get("shipType")
    ship_type: Optional[int] = None
    if ship_type_raw is not None:
        try:
            ship_type = int(ship_type_raw)
        except (TypeError, ValueError):
            ship_type = None
    return {
        "ship_name": ship_name,
        "call_sign": call_sign,
        "destination": destination,
        "imo": imo,
        "ship_type": ship_type,
    }


def _message_metadata(message: dict[str, Any]) -> dict[str, Any]:
    """AISstream uses MetaData; accept Metadata as a defensive alias."""
    meta = message.get("MetaData")
    if isinstance(meta, dict):
        return meta
    meta = message.get("Metadata")
    return meta if isinstance(meta, dict) else {}


def _int_or_none(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def parse_ship_static(message: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    ShipStaticData / StaticDataReport → identity fields only (no lat/lon).

    AIS type (Type) is the reliable source for silhouettes; PositionReport MetaData
    often omits ShipType, which is why every vessel previously looked the same.
    """
    message_type = message.get("MessageType", "")
    metadata = _message_metadata(message)
    envelope = message.get("Message") if isinstance(message.get("Message"), dict) else {}
    body: dict[str, Any] = {}
    if message_type == "ShipStaticData":
        raw = envelope.get("ShipStaticData")
        if isinstance(raw, dict):
            body = raw
    elif message_type == "StaticDataReport":
        raw = envelope.get("StaticDataReport")
        if isinstance(raw, dict):
            body = raw
            # Class B part B often nests Type under ReportB / PartB
            for nest_key in ("ReportB", "PartB", "partB"):
                nested = body.get(nest_key)
                if isinstance(nested, dict):
                    body = {**body, **nested}
                    break
    else:
        return None

    mmsi = _mmsi_from_body(body, metadata)
    if not mmsi:
        return None

    name = _meta_str(body, "Name", "ShipName") or _meta_str(
        metadata, "ShipName", "shipName", max_len=48
    )
    if name and len(name) > 48:
        name = name[:47] + "…"
    call_sign = _meta_str(body, "CallSign", "Callsign") or _meta_str(
        metadata, "CallSign", "Callsign", "callSign", max_len=12
    )
    destination = _meta_str(body, "Destination") or _meta_str(
        metadata, "Destination", "destination", max_len=42
    )
    imo_raw = body.get("ImoNumber", body.get("IMO", metadata.get("ImoNumber")))
    imo = ""
    if imo_raw not in (None, "", 0, "0"):
        imo = str(imo_raw).strip()[:12]

    ship_type = _int_or_none(body.get("Type", body.get("ShipType", metadata.get("ShipType"))))
    if ship_type is not None and (ship_type < 0 or ship_type > 99):
        ship_type = None

    return {
        "mmsi": mmsi,
        "ship_name": name,
        "call_sign": call_sign,
        "destination": destination,
        "imo": imo,
        "ship_type": ship_type,
    }


def _overlay_static(target: dict[str, Any], static: dict[str, Any]) -> dict[str, Any]:
    """Fill blank identity fields from static AIS data; never overwrite a real value."""
    out = dict(target)
    if out.get("ship_type") is None and static.get("ship_type") is not None:
        out["ship_type"] = static["ship_type"]
    for key in ("ship_name", "call_sign", "destination", "imo"):
        if not out.get(key) and static.get(key):
            out[key] = static[key]
    return out


def _parse_position_report(message: dict[str, Any]) -> Optional[dict[str, Any]]:
    """AIS MessageType PositionReport → unified position dict."""
    try:
        metadata = _message_metadata(message)
        position_report = message.get("Message", {}).get("PositionReport", {})
        if not position_report:
            return None
        mmsi = _mmsi_from_body(position_report, metadata)
        if not mmsi:
            return None
        meta = _metadata_strings(metadata)
        return {
            "mmsi": mmsi,
            **meta,
            "latitude": float(position_report.get("Latitude", 0.0)),
            "longitude": float(position_report.get("Longitude", 0.0)),
            "speed": _sog_knots(position_report),
            "heading": _heading_from_raw(position_report.get("TrueHeading", 511)),
            "timestamp": _timestamp_from_metadata(metadata),
        }
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Failed to parse PositionReport: %s", e)
        return None


def _parse_standard_class_b(message: dict[str, Any]) -> Optional[dict[str, Any]]:
    """AIS Class B standard position (message 18-style JSON)."""
    try:
        metadata = _message_metadata(message)
        body = message.get("Message", {}).get("StandardClassBPositionReport")
        if not body:
            return None
        mmsi = _mmsi_from_body(body, metadata)
        if not mmsi:
            return None
        meta = _metadata_strings(metadata)
        return {
            "mmsi": mmsi,
            **meta,
            "latitude": float(body.get("Latitude", 0.0)),
            "longitude": float(body.get("Longitude", 0.0)),
            "speed": _sog_knots(body),
            "heading": _heading_from_raw(body.get("TrueHeading", 511)),
            "timestamp": _timestamp_from_metadata(metadata),
        }
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Failed to parse StandardClassBPositionReport: %s", e)
        return None


def _parse_extended_class_b(message: dict[str, Any]) -> Optional[dict[str, Any]]:
    """AIS extended Class B position; may carry Name / Type in body."""
    try:
        metadata = _message_metadata(message)
        body = message.get("Message", {}).get("ExtendedClassBPositionReport")
        if not body:
            return None
        mmsi = _mmsi_from_body(body, metadata)
        if not mmsi:
            return None
        meta = _metadata_strings(metadata)
        if not meta["ship_name"]:
            raw_name = (body.get("Name") or "").strip()
            if raw_name:
                meta = {**meta, "ship_name": raw_name[:47] + "…" if len(raw_name) > 48 else raw_name}
        st_body = body.get("Type")
        if st_body is not None and meta.get("ship_type") is None:
            try:
                meta = {**meta, "ship_type": int(st_body)}
            except (TypeError, ValueError):
                pass
        return {
            "mmsi": mmsi,
            **meta,
            "latitude": float(body.get("Latitude", 0.0)),
            "longitude": float(body.get("Longitude", 0.0)),
            "speed": _sog_knots(body),
            "heading": _heading_from_raw(body.get("TrueHeading", 511)),
            "timestamp": _timestamp_from_metadata(metadata),
        }
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Failed to parse ExtendedClassBPositionReport: %s", e)
        return None


def _parse_long_range(message: dict[str, Any]) -> Optional[dict[str, Any]]:
    """AIS long-range broadcast (coarser position)."""
    try:
        metadata = _message_metadata(message)
        body = message.get("Message", {}).get("LongRangeAisBroadcastMessage")
        if not body:
            return None
        mmsi = _mmsi_from_body(body, metadata)
        if not mmsi:
            return None
        meta = _metadata_strings(metadata)
        cog = float(body.get("Cog", 0.0))
        # Long-range messages may not include TrueHeading; approximate heading from COG when valid.
        heading = _heading_from_raw(body.get("TrueHeading", 511))
        if heading == 0xFFFF and 0 <= cog <= 360:
            heading = int(round(cog)) & 0xFFFF
        return {
            "mmsi": mmsi,
            **meta,
            "latitude": float(body.get("Latitude", 0.0)),
            "longitude": float(body.get("Longitude", 0.0)),
            "speed": _sog_knots(body),
            "heading": heading,
            "timestamp": _timestamp_from_metadata(metadata),
        }
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Failed to parse LongRangeAisBroadcastMessage: %s", e)
        return None


_PARSERS: dict[str, Any] = {
    "PositionReport": _parse_position_report,
    "StandardClassBPositionReport": _parse_standard_class_b,
    "ExtendedClassBPositionReport": _parse_extended_class_b,
    "LongRangeAisBroadcastMessage": _parse_long_range,
}


def parse_ais_position_message(message: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Parse a subscribed AISStream message into the unified vessel dict used by OceanChain.

    Returns:
        Position dict or None if unknown / unsupported / failed for this MessageType.
    """
    message_type = message.get("MessageType", "")
    parser = _PARSERS.get(message_type)
    if parser is None:
        return None
    return parser(message)


class AISClient:
    """
    Persistent WebSocket client for AISstream.io.

    Maintains a live snapshot of vessel positions keyed by MMSI. Multiple AIS
    position-class message types can update the same MMSI; fresher timestamps
    win, with a detail tie-break when timestamps match.
    """

    def __init__(self) -> None:
        self._snapshot: dict[str, dict[str, Any]] = {}
        self._static: dict[str, dict[str, Any]] = {}
        self._connected: bool = False
        self._reconnect_delay: float = 5.0
        self._message_count: int = 0
        self._frames_received: int = 0
        self._last_message_time: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._rate_limited_until: float = 0.0
        self._rate_limit_hits: int = 0

    def get_current_snapshot(self) -> dict[str, dict[str, Any]]:
        """Shallow copy of MMSI → position data (values may still be mutated — treat as read-only)."""
        return self._snapshot.copy()

    def get_vessel_count(self) -> int:
        return len(self._snapshot)

    def get_message_count(self) -> int:
        return self._message_count

    def is_connected(self) -> bool:
        return self._connected

    def get_status(self) -> dict[str, Any]:
        now = time.monotonic()
        rate_limited = now < self._rate_limited_until
        return {
            "connected": self._connected,
            "vessels": len(self._snapshot),
            "messages": self._message_count,
            "frames_received": self._frames_received,
            "rate_limited": rate_limited,
            "rate_limited_for_seconds": (
                max(0, int(self._rate_limited_until - now)) if rate_limited else 0
            ),
            "last_error": self._last_error,
        }

    def _mark_rate_limited(self, reason: str) -> float:
        self._rate_limit_hits += 1
        # Exponential backoff: 3m, 6m, 12m… capped at 30m. Connection attempts
        # (not message volume) are what AISstream throttles on the free tier.
        backoff = min(1800.0, 180.0 * (2 ** min(self._rate_limit_hits - 1, 4)))
        self._rate_limited_until = time.monotonic() + backoff
        self._last_error = reason
        return backoff

    def _merge_into_snapshot(self, position: dict[str, Any], message_type: str) -> None:
        """
        Store position unless existing snapshot row is strictly newer / higher rank.

        Internal key ``_ais_message_type`` records last winning AIS message type (stripped
        before OP_RETURN in tx_builder today — unknown keys are ignored in binary mode).
        """
        mmsi = position["mmsi"]
        ts_new = int(position["timestamp"])
        rank_new = SOURCE_DETAIL_RANK.get(message_type, 0)
        existing = self._snapshot.get(mmsi)
        if existing is not None:
            ts_old = int(existing.get("timestamp", 0))
            prev_type = str(existing.get("_ais_message_type", "PositionReport"))
            rank_old = SOURCE_DETAIL_RANK.get(prev_type, 0)
            if ts_new < ts_old:
                return
            if ts_new == ts_old and rank_new < rank_old:
                return
        out = {**position, "_ais_message_type": message_type}
        if existing is not None:
            out = _overlay_static(out, existing)
        cached = self._static.get(mmsi)
        if cached:
            out = _overlay_static(out, cached)
        self._snapshot[mmsi] = out

    def _ingest_static(self, message: dict[str, Any]) -> bool:
        parsed = parse_ship_static(message)
        if not parsed:
            return False
        mmsi = parsed["mmsi"]
        prev = self._static.get(mmsi, {})
        merged = _overlay_static(dict(prev), parsed)
        merged["mmsi"] = mmsi
        if parsed.get("ship_type") is not None:
            merged["ship_type"] = parsed["ship_type"]
        self._static[mmsi] = merged
        existing = self._snapshot.get(mmsi)
        if existing is not None:
            self._snapshot[mmsi] = _overlay_static(existing, merged)
        return True

    async def _handle_message(self, raw_message: str) -> None:
        try:
            self._frames_received += 1
            if self._frames_received <= 5:
                preview = raw_message if isinstance(raw_message, str) else repr(raw_message)
                logger.info(
                    "AIS frame #%s (%s bytes): %s",
                    self._frames_received,
                    len(preview),
                    preview[:400],
                )

            message = json.loads(raw_message)

            # AISstream auth / subscription failures arrive as plain error objects
            if isinstance(message, dict) and "error" in message and "MessageType" not in message:
                logger.error("AISstream error: %s", message.get("error"))
                self._last_error = str(message.get("error"))
                return

            message_type = message.get("MessageType", "")

            if message_type not in AISSTREAM_FILTER_MESSAGE_TYPES:
                if self._frames_received <= 20:
                    logger.info(
                        "Ignoring AIS message type %r (filter=%s)",
                        message_type or "(empty)",
                        list(AISSTREAM_FILTER_MESSAGE_TYPES),
                    )
                return

            if message_type in SUPPORTED_AIS_STATIC_MESSAGE_TYPES:
                if self._ingest_static(message):
                    self._message_count += 1
                    self._last_message_time = datetime.utcnow()
                elif self._frames_received <= 20:
                    logger.warning(
                        "Failed to parse %s frame #%s",
                        message_type,
                        self._frames_received,
                    )
                return

            position = parse_ais_position_message(message)
            if not position:
                if self._frames_received <= 20:
                    logger.warning(
                        "Failed to parse %s frame #%s",
                        message_type,
                        self._frames_received,
                    )
                return

            self._merge_into_snapshot(position, message_type)
            self._message_count += 1
            self._last_message_time = datetime.utcnow()

            if self._message_count == 1:
                logger.info(
                    "First AIS position received (MMSI %s) — snapshot live",
                    position.get("mmsi"),
                )
            elif self._message_count % 50000 == 0:
                logger.debug(
                    "AIS processed %s messages, %s vessels in snapshot",
                    self._message_count,
                    len(self._snapshot),
                )

        except json.JSONDecodeError as e:
            logger.warning("Failed to decode JSON message: %s", e)

    async def _connect_and_subscribe(self) -> websockets.WebSocketClientProtocol:
        logger.info("Connecting to AISstream at %s", AISSTREAM_WS_URL)

        # AISstream can stay quiet for several seconds after subscribe; keep ping
        # generous so a busy/slow feed is not mistaken for a dead socket.
        websocket = await websockets.connect(
            AISSTREAM_WS_URL,
            ping_interval=20,
            ping_timeout=60,
            close_timeout=10,
            max_queue=1024,
        )

        subscription = {
            "APIKey": AISSTREAM_API_KEY.strip(),
            "BoundingBoxes": [[[-90, -180], [90, 180]]],
            "FilterMessageTypes": list(AISSTREAM_FILTER_MESSAGE_TYPES),
        }

        await websocket.send(json.dumps(subscription))
        logger.info(
            "AISstream subscription sent (FilterMessageTypes=%s, key_len=%s)",
            AISSTREAM_FILTER_MESSAGE_TYPES,
            len(AISSTREAM_API_KEY.strip()),
        )

        self._connected = True
        self._last_error = None
        self._rate_limit_hits = 0
        self._rate_limited_until = 0.0
        self._frames_received = 0
        return websocket

    async def run(self) -> None:
        """
        Connect, subscribe, and process messages until cancelled.

        Reconnects with backoff on errors. Free-tier AISstream throttles
        *connection attempts* (HTTP 429), not messages on an open socket.
        """
        while True:
            try:
                websocket = await self._connect_and_subscribe()

                async for raw_message in websocket:
                    await self._handle_message(raw_message)

            except ConnectionClosed as e:
                logger.warning("WebSocket connection closed: %s", e)
                self._connected = False
                self._last_error = f"connection closed: {e}"

            except WebSocketException as e:
                logger.error("WebSocket error: %s", e)
                self._connected = False
                if "429" in str(e):
                    backoff = self._mark_rate_limited(str(e))
                    logger.warning(
                        "AISstream rate-limited (HTTP 429). Backing off %.0fs before retry. "
                        "Avoid opening multiple clients with the same key.",
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                self._last_error = str(e)

            except asyncio.CancelledError:
                logger.info("AIS client shutdown requested")
                self._connected = False
                raise

            except Exception as e:
                logger.error("Unexpected error in AIS client: %s", e, exc_info=True)
                self._connected = False
                if "429" in str(e):
                    backoff = self._mark_rate_limited(str(e))
                    logger.warning(
                        "AISstream rate-limited (HTTP 429). Backing off %.0fs before retry.",
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                self._last_error = str(e)

            logger.info("Reconnecting in %s seconds...", self._reconnect_delay)
            await asyncio.sleep(self._reconnect_delay)


# Global singleton instance
ais_client = AISClient()
