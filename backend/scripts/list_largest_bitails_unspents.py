#!/usr/bin/env python3
"""
Find the largest **current unspent outputs** for a P2PKH address via Bitails.

This does **not** walk transaction history (millions of txs). It only calls the
same unspent list used for reserve import — typically tens or hundreds of
thousands of rows, not millions.

Use the printed txid/vout/value_sat with POST /utxo/reserve, or confirm what
to aim for before consolidation.

Example (from backend/ with venv active):

  python scripts/list_largest_bitails_unspents.py --address 1YourP2PKH --top 30

If OceanChain already imported reserves, you can also query Postgres:

  SELECT txid, vout, value_sat FROM utxos
  WHERE utxo_role = 'reserve' AND locked = FALSE
  ORDER BY value_sat DESC LIMIT 30;
"""
from __future__ import annotations

import argparse
import heapq
import json
import os
import sys
from typing import Any

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BITAILS_BASE_DEFAULT = "https://api.bitails.io"
USER_AGENT = "OceanChain-bitails-top-unspents/1.0"


def _extract_unspent(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("unspent")
    if raw is None:
        raw = payload.get("utxos")
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _row_from_item(item: dict[str, Any]) -> tuple[str, int, int] | None:
    txid = item.get("txid") or item.get("tx_id")
    vout = item.get("vout")
    sat = item.get("satoshis")
    if sat is None:
        sat = item.get("value_sat") or item.get("value")
    if txid is None or vout is None or sat is None:
        return None
    try:
        t = str(txid).strip().lower()
        v = int(vout)
        s = int(sat)
    except (ValueError, TypeError):
        return None
    if len(t) != 64 or any(c not in "0123456789abcdef" for c in t):
        return None
    if v < 0 or s < 1:
        return None
    return (t, v, s)


def main() -> int:
    p = argparse.ArgumentParser(
        description="List largest Bitails unspents for an address (current UTXO set only).",
    )
    p.add_argument(
        "--address",
        default=os.environ.get("OCEANCHAIN_FUNDING_ADDRESS", "").strip() or None,
        help="P2PKH address (or OCEANCHAIN_FUNDING_ADDRESS).",
    )
    p.add_argument(
        "--bitails-base",
        default=os.environ.get("BITAILS_API_BASE", BITAILS_BASE_DEFAULT).rstrip("/"),
        help=f"Bitails API root (default: {BITAILS_BASE_DEFAULT}).",
    )
    p.add_argument(
        "--bitails-api-key",
        default=os.environ.get("BITAILS_API_KEY", "").strip() or None,
        help="Optional Bitails apikey header (or BITAILS_API_KEY).",
    )
    p.add_argument(
        "--page-size",
        type=int,
        default=int(os.environ.get("BITAILS_PAGE_SIZE", "500")),
        help="Unspent page size (default 500).",
    )
    p.add_argument(
        "--top",
        type=int,
        default=25,
        help="How many largest outputs to print (default 25).",
    )
    p.add_argument(
        "--min-sat",
        type=int,
        default=0,
        help="Ignore outputs below this value (satoshis).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print JSON array instead of a table.",
    )
    args = p.parse_args()

    if not args.address:
        print("error: --address or OCEANCHAIN_FUNDING_ADDRESS is required", file=sys.stderr)
        return 2
    if args.top < 1:
        print("error: --top must be >= 1", file=sys.stderr)
        return 2
    if args.page_size < 1:
        print("error: --page-size must be >= 1", file=sys.stderr)
        return 2

    headers: dict[str, str] = {"User-Agent": USER_AGENT}
    if args.bitails_api_key:
        headers["apikey"] = args.bitails_api_key

    # Min-heap of (sat, txid, vout) — keep k largest by sat
    heap: list[tuple[int, str, int]] = []
    seen_pages = 0
    parsed = 0
    skipped_min = 0
    offset = 0

    with httpx.Client() as client:
        while True:
            url = f"{args.bitails_base}/address/{args.address}/unspent"
            r = client.get(
                url,
                params={"from": offset, "limit": args.page_size},
                headers=headers,
                timeout=120.0,
            )
            r.raise_for_status()
            page = _extract_unspent(r.json())
            if not page:
                break
            seen_pages += 1

            for item in page:
                row = _row_from_item(item)
                if row is None:
                    continue
                parsed += 1
                txid, vout, sat = row
                if args.min_sat > 0 and sat < args.min_sat:
                    skipped_min += 1
                    continue
                if len(heap) < args.top:
                    heapq.heappush(heap, (sat, txid, vout))
                elif sat > heap[0][0]:
                    heapq.heapreplace(heap, (sat, txid, vout))

            if len(page) < args.page_size:
                break
            offset += args.page_size

    ranked = sorted(heap, key=lambda x: -x[0])
    total_unspent_sat = sum(s for s, _, _ in ranked)

    if args.json:
        out = [
            {"txid": t, "vout": v, "value_sat": s}
            for s, t, v in ranked
        ]
        print(json.dumps({"top": out, "stats": {
            "pages_fetched": seen_pages,
            "utxos_parsed": parsed,
            "skipped_below_min_sat": skipped_min,
            "top_n_sum_sat": total_unspent_sat,
        }}, indent=2))
        return 0

    print(
        f"# Bitails unspent scan: address={args.address} "
        f"pages={seen_pages} parsed={parsed} skipped_min_sat={skipped_min} "
        f"(showing top {len(ranked)} by value)\n"
    )
    print(f"{'value_sat':>12}  {'vout':>6}  txid")
    for sat, txid, vout in ranked:
        print(f"{sat:12d}  {vout:6d}  {txid}")
    if ranked:
        print(f"\n# Sum of printed outputs only: {total_unspent_sat} sat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
