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
        # Per-ARC-endpoint accounting: attempts, successes, cumulative latency.
        # Answers "is Gorilla actually succeeding, and how long does each path take?"
        self.arc_attempts: dict[str, int] = {}
        self.arc_success: dict[str, int] = {}
        self.arc_latency_ms: dict[str, float] = {}

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

    async def record_arc_attempt(
        self, broadcaster: str, success: bool, latency_ms: float
    ) -> None:
        """Record one finished ARC endpoint attempt (submit + any status polling)."""
        async with self._lock:
            self.arc_attempts[broadcaster] = self.arc_attempts.get(broadcaster, 0) + 1
            if success:
                self.arc_success[broadcaster] = self.arc_success.get(broadcaster, 0) + 1
            self.arc_latency_ms[broadcaster] = (
                self.arc_latency_ms.get(broadcaster, 0.0) + latency_ms
            )

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
                "arc_attempts": dict(self.arc_attempts),
                "arc_success": dict(self.arc_success),
                "arc_latency_ms": dict(self.arc_latency_ms),
            }
            self.ok = 0
            self.fail_broadcast = 0
            self.skip_no_utxo = 0
            self.fail_other = 0
            self.fees_sat_window = 0
            self._ok_samples.clear()
            self._fail_samples.clear()
            self.arc_attempts.clear()
            self.arc_success.clear()
            self.arc_latency_ms.clear()
            return snap


broadcast_stats = BroadcastStats()
