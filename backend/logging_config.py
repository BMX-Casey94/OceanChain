"""
Third-party logger levels and shared helpers for quieter production logs.
"""

from __future__ import annotations

import logging


def vessel_log_label(position: dict) -> str:
    """Compact label for summaries: ShipName|MMSI (sanitised)."""
    raw_name = (position.get("ship_name") or "").strip().replace("|", "/")
    name = raw_name[:42] if raw_name else ""
    mmsi = str(position.get("mmsi") or "?")
    if name:
        return f"{name}|{mmsi}"
    return mmsi


def configure_quiet_loggers() -> None:
    """Demote noisy HTTP client libraries (every ARC POST was flooding INFO)."""
    for name in ("httpx", "httpcore", "h11"):
        logging.getLogger(name).setLevel(logging.WARNING)
