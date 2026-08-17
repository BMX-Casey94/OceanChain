"""
Ocechain public vessel query helpers.

Serialises the in-memory AIS snapshot for HTTP consumers (map + search).
"""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

SnapshotProvider = Callable[[], dict[str, dict[str, Any]]]

_snapshot_provider: Optional[SnapshotProvider] = None
_last_tx_by_mmsi: dict[str, dict[str, Any]] = {}
# Recent broadcast positions per MMSI for the route tracker (newest last).
_trail_by_mmsi: dict[str, list[dict[str, Any]]] = {}


def set_vessel_snapshot_provider(provider: SnapshotProvider) -> None:
    global _snapshot_provider
    _snapshot_provider = provider


def record_vessel_tx(tx_event: dict[str, Any]) -> None:
    mmsi = str(tx_event.get("mmsi") or "").strip()
    if not mmsi:
        return
    _last_tx_by_mmsi[mmsi] = {
        "txid": tx_event.get("txid"),
        "fee_sat": tx_event.get("fee_sat"),
        "timestamp": tx_event.get("timestamp"),
        "broadcaster": tx_event.get("broadcaster"),
    }
    try:
        lat = float(tx_event.get("lat"))
        lon = float(tx_event.get("lon"))
    except (TypeError, ValueError):
        return
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return
    from config import VESSEL_TRAIL_MAX_POINTS

    trail = _trail_by_mmsi.setdefault(mmsi, [])
    trail.append(
        {
            "lat": lat,
            "lon": lon,
            "timestamp": int(tx_event.get("timestamp") or 0),
            "txid": tx_event.get("txid"),
        }
    )
    if len(trail) > VESSEL_TRAIL_MAX_POINTS:
        del trail[: len(trail) - VESSEL_TRAIL_MAX_POINTS]


def get_vessel_trail(mmsi: str) -> list[dict[str, Any]]:
    """Oldest → newest broadcast positions for this MMSI (process memory only)."""
    return list(_trail_by_mmsi.get(mmsi, []))


def get_last_tx(mmsi: str) -> Optional[dict[str, Any]]:
    return _last_tx_by_mmsi.get(mmsi)


def _heading_public(raw: Any) -> Optional[int]:
    try:
        h = int(raw)
    except (TypeError, ValueError):
        return None
    if h == 0xFFFF or h < 0 or h > 359:
        return None
    return h


def serialise_vessel(mmsi: str, position: dict[str, Any]) -> dict[str, Any]:
    last = _last_tx_by_mmsi.get(mmsi) or {}
    return {
        "mmsi": mmsi,
        "name": (position.get("ship_name") or "").strip(),
        "call_sign": (position.get("call_sign") or "").strip(),
        "destination": (position.get("destination") or "").strip(),
        "imo": "" if str(position.get("imo") or "").strip() in {"", "0"} else str(position.get("imo")).strip(),
        "ship_type": position.get("ship_type"),
        "lat": float(position.get("latitude") or 0.0),
        "lon": float(position.get("longitude") or 0.0),
        "speed": float(position.get("speed") or 0.0),
        "heading": _heading_public(position.get("heading")),
        "timestamp": int(position.get("timestamp") or 0),
        "last_txid": last.get("txid"),
        "fee_sat": last.get("fee_sat"),
    }


def get_snapshot() -> dict[str, dict[str, Any]]:
    if _snapshot_provider is None:
        return {}
    return _snapshot_provider()


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_nm = 3440.065  # Earth radius in nautical miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r_nm * math.asin(min(1.0, math.sqrt(a)))


def list_vessels(
    *,
    bbox: Optional[tuple[float, float, float, float]] = None,
    near: Optional[tuple[float, float]] = None,
    radius_nm: float = 50.0,
    limit: int = 8000,
) -> list[dict[str, Any]]:
    snapshot = get_snapshot()
    out: list[dict[str, Any]] = []
    for mmsi, pos in snapshot.items():
        try:
            lat = float(pos.get("latitude") or 0.0)
            lon = float(pos.get("longitude") or 0.0)
        except (TypeError, ValueError):
            continue
        if abs(lat) < 1e-9 and abs(lon) < 1e-9:
            continue
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            if lon < min_lon or lon > max_lon or lat < min_lat or lat > max_lat:
                continue
        if near is not None:
            if haversine_nm(near[0], near[1], lat, lon) > radius_nm:
                continue
        out.append(serialise_vessel(mmsi, pos))
        if len(out) >= limit:
            break
    return out


def get_vessel(mmsi: str) -> Optional[dict[str, Any]]:
    snapshot = get_snapshot()
    pos = snapshot.get(mmsi)
    if pos is None:
        # try case-insensitive / digit normalisation
        for key, value in snapshot.items():
            if key == mmsi or key.lstrip("0") == mmsi.lstrip("0"):
                return serialise_vessel(key, value)
        return None
    return serialise_vessel(mmsi, pos)


def search_vessels(q: str, limit: int = 12) -> list[dict[str, Any]]:
    query = q.strip().lower()
    if not query:
        return []
    snapshot = get_snapshot()
    scored: list[tuple[int, dict[str, Any]]] = []
    for mmsi, pos in snapshot.items():
        name = (pos.get("ship_name") or "").strip().lower()
        call = (pos.get("call_sign") or "").strip().lower()
        imo = (pos.get("imo") or "").strip().lower()
        mmsi_l = mmsi.lower()
        score = 0
        if mmsi_l == query or mmsi_l.lstrip("0") == query.lstrip("0"):
            score = 100
        elif mmsi_l.startswith(query):
            score = 90
        elif query in mmsi_l:
            score = 70
        elif name and name == query:
            score = 95
        elif name and name.startswith(query):
            score = 85
        elif name and query in name:
            score = 60
        elif call and (call == query or call.startswith(query)):
            score = 80
        elif imo and (imo == query or query in imo):
            score = 75
        if score:
            scored.append((score, serialise_vessel(mmsi, pos)))
    scored.sort(key=lambda x: (-x[0], x[1].get("name") or x[1]["mmsi"]))
    return [item for _, item in scored[:limit]]
