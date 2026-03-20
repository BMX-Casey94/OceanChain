"""
Rolling broadcast counters for periodic VPS log summaries (reduces per-tx noise).
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Deque


class BroadcastStats:
    """Thread-safe (asyncio lock) windowed counters and small sample buffers."""

    def __init__(self, max_samples: int = 6) -> None:
        self._lock = asyncio.Lock()
        self.max_samples = max_samples
        self.ok = 0
        self.fail_broadcast = 0
        self.skip_no_utxo = 0
        self.fail_other = 0
        self.fees_sat_window = 0
        self._ok_samples: Deque[str] = deque(maxlen=max_samples)
        self._fail_samples: Deque[str] = deque(maxlen=max_samples)

    async def record_ok(self, label: str, fee_sat: int) -> None:
        async with self._lock:
            self.ok += 1
            self.fees_sat_window += fee_sat
            self._ok_samples.append(label)

    async def record_fail_broadcast(self, label: str, reason: str) -> None:
        async with self._lock:
            self.fail_broadcast += 1
            r = (reason or "")[:120].replace("\n", " ")
            self._fail_samples.append(f"{label} | {r}")

    async def record_skip_no_utxo(self, label: str) -> None:
        async with self._lock:
            self.skip_no_utxo += 1

    async def record_fail_other(self, label: str, reason: str) -> None:
        async with self._lock:
            self.fail_other += 1
            r = (reason or "")[:100].replace("\n", " ")
            self._fail_samples.append(f"{label} | {r}")

    async def drain_window(self) -> dict[str, Any]:
        async with self._lock:
            snap = {
                "ok": self.ok,
                "fail_broadcast": self.fail_broadcast,
                "skip_no_utxo": self.skip_no_utxo,
                "fail_other": self.fail_other,
                "fees_sat": self.fees_sat_window,
                "ok_samples": list(self._ok_samples),
                "fail_samples": list(self._fail_samples),
            }
            self.ok = 0
            self.fail_broadcast = 0
            self.skip_no_utxo = 0
            self.fail_other = 0
            self.fees_sat_window = 0
            self._ok_samples.clear()
            self._fail_samples.clear()
            return snap


broadcast_stats = BroadcastStats()
