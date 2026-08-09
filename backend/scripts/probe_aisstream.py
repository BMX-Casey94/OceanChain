"""One-shot AISstream connectivity probe (local diagnostics only)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
import os
import websockets

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main() -> int:
    key = (os.getenv("AISSTREAM_API_KEY") or "").strip()
    if not key:
        print("AISSTREAM_API_KEY missing")
        return 1

    uri = "wss://stream.aisstream.io/v0/stream"
    print(f"connecting key_len={len(key)} …")
    try:
        async with websockets.connect(
            uri, ping_interval=20, ping_timeout=60, close_timeout=10
        ) as ws:
            sub = {
                "APIKey": key,
                "BoundingBoxes": [[[-90.0, -180.0], [90.0, 180.0]]],
                "FilterMessageTypes": ["PositionReport"],
            }
            await ws.send(json.dumps(sub))
            print("subscription sent; waiting up to 45s for first frames…")
            for i in range(8):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=45 if i == 0 else 15)
                except asyncio.TimeoutError:
                    print(f"timeout waiting for message #{i}")
                    return 2
                preview = raw[:500] if isinstance(raw, str) else repr(raw)[:500]
                print(f"MSG {i}: {preview}")
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and data.get("error"):
                    print("AISSTREAM ERROR:", data.get("error"))
                    return 3
                if isinstance(data, dict) and data.get("MessageType"):
                    print("ok — received", data.get("MessageType"))
                    return 0
    except Exception as e:
        print(f"connection failed: {type(e).__name__}: {e}")
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
