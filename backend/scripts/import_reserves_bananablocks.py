#!/usr/bin/env python3
"""
Import the largest unspent outputs for the wallet into OceanChain reserve rows.

Pages BananaBlocks `GET /api/v1/address/{address}/utxos?sort=value:desc` and POSTs
batches to `POST /utxo/reserves/bulk-import` (admin key). Because the listing is
sorted by value, paging stops at the first output below --min-sat, so a wallet
with over a million dust outputs costs a few dozen requests instead of a full scan.

Only confirmed outputs are returned by this endpoint, which is what the reserve
table must hold (unconfirmed change is tracked separately as pending).

Run on the VPS from `backend/` with the API listening locally. The admin key is
read from OCEANCHAIN_ADMIN_API_KEY and is never printed.

    python scripts/import_reserves_bananablocks.py --address 1YourP2PKH --dry-run
    python scripts/import_reserves_bananablocks.py --address 1YourP2PKH

Optional: BANANABLOCKS_API_KEY raises the rate limit (sent as X-API-Key).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any
from urllib.parse import quote

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BANANABLOCKS_BASE_DEFAULT = "https://bananablocks.com/api/v1"
BULK_IMPORT_MAX = 25_000
USER_AGENT = "OceanChain-reserve-import-bananablocks/1.0"
MAX_RATE_LIMIT_RETRIES = 5
# Base58 P2PKH address charset (no 0, O, I, l). Rejects anything that could alter the URL path.
_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{25,35}$")


def _row_from_item(item: dict[str, Any]) -> tuple[str, int, int] | None:
    # Reserve rows must be confirmed (unconfirmed change would bypass the pending gate).
    # The listing is documented as confirmed-only; require a real block height as well so
    # that a shape change on the service side fails closed instead of importing mempool rows.
    try:
        if int(item.get("block_height") or 0) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    txid = item.get("txid")
    vout = item.get("vout")
    sat = item.get("value")
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


def _get_page(
    client: httpx.Client,
    base: str,
    address: str,
    headers: dict[str, str],
    page_size: int,
    cursor: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"sort": "value:desc", "limit": page_size}
    if cursor:
        params["cursor"] = cursor
    url = f"{base}/address/{quote(address, safe='')}/utxos"
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        r = client.get(url, params=params, headers=headers, timeout=120.0)
        if r.status_code == 429:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                raise RuntimeError("BananaBlocks rate limit persisted after retries")
            print("rate limited (429); waiting 65s", file=sys.stderr)
            time.sleep(65)
            continue
        r.raise_for_status()
        body = r.json()
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            raise RuntimeError("Unexpected BananaBlocks response shape (no 'items' list)")
        return body
    raise RuntimeError("unreachable")


def _post_batch(
    client: httpx.Client,
    api_base: str,
    admin_key: str,
    utxos: list[dict[str, Any]],
) -> dict[str, Any]:
    r = client.post(
        f"{api_base.rstrip('/')}/utxo/reserves/bulk-import",
        headers={
            "X-OceanChain-Admin-Key": admin_key,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        content=json.dumps({"utxos": utxos}),
        timeout=300.0,
    )
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:500]}
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {body}")
    return body if isinstance(body, dict) else {"body": body}


def main() -> int:
    p = argparse.ArgumentParser(
        description="Import the largest wallet UTXOs into OceanChain reserve (BananaBlocks).",
    )
    p.add_argument("--address", default=os.environ.get("OCEANCHAIN_FUNDING_ADDRESS", "").strip() or None)
    p.add_argument(
        "--api-base",
        default=os.environ.get("OCEANCHAIN_API_BASE", "http://127.0.0.1:8000").rstrip("/"),
    )
    p.add_argument("--admin-key", default=os.environ.get("OCEANCHAIN_ADMIN_API_KEY", "").strip() or None)
    p.add_argument(
        "--bananablocks-base",
        default=os.environ.get("BANANABLOCKS_API_BASE", BANANABLOCKS_BASE_DEFAULT).rstrip("/"),
    )
    p.add_argument("--bananablocks-api-key", default=os.environ.get("BANANABLOCKS_API_KEY", "").strip() or None)
    p.add_argument("--page-size", type=int, default=1000, help="Per page (service max 1000).")
    p.add_argument("--batch-size", type=int, default=5000, help=f"UTXOs per POST (max {BULK_IMPORT_MAX}).")
    p.add_argument("--min-sat", type=int, default=1000, help="Stop at the first output below this value.")
    p.add_argument("--max-pages", type=int, default=200, help="Safety cap on pages fetched.")
    p.add_argument("--dry-run", action="store_true", help="Fetch and report only; POST nothing.")
    args = p.parse_args()

    if not args.address:
        print("error: --address or OCEANCHAIN_FUNDING_ADDRESS is required", file=sys.stderr)
        return 2
    if not _ADDRESS_RE.match(args.address):
        print("error: --address is not a valid base58 P2PKH address", file=sys.stderr)
        return 2
    if not args.dry_run and not args.admin_key:
        print("error: OCEANCHAIN_ADMIN_API_KEY (or --admin-key) is required unless --dry-run", file=sys.stderr)
        return 2
    if not 1 <= args.batch_size <= BULK_IMPORT_MAX:
        print(f"error: --batch-size must be 1..{BULK_IMPORT_MAX}", file=sys.stderr)
        return 2
    if not 1 <= args.page_size <= 1000:
        print("error: --page-size must be 1..1000", file=sys.stderr)
        return 2
    if args.min_sat < 1:
        print("error: --min-sat must be >= 1", file=sys.stderr)
        return 2

    headers: dict[str, str] = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if args.bananablocks_api_key:
        headers["X-API-Key"] = args.bananablocks_api_key

    seen: set[tuple[str, int]] = set()
    batch: list[dict[str, Any]] = []
    total_rows = 0
    total_sat = 0
    pages = 0
    cursor: str | None = None
    previous_value: int | None = None
    reached_floor = False
    posted = 0
    inserted_total = 0

    with httpx.Client() as client:

        def flush() -> None:
            nonlocal batch, posted, inserted_total
            if not batch:
                return
            if args.dry_run:
                print(f"dry-run: would POST batch of {len(batch)}")
            else:
                result = _post_batch(client, args.api_base, args.admin_key, batch)
                posted += len(batch)
                inserted_total += int(result.get("inserted_rows") or 0)
                print(
                    f"posted {len(batch)} (cumulative {posted}); "
                    f"inserted={result.get('inserted_rows')} "
                    f"already_tracked={result.get('already_tracked')} "
                    f"reserve_count={result.get('reserve_count')} "
                    f"reserve_total_sat={result.get('reserve_total_sat')}"
                )
            batch = []

        while pages < args.max_pages and not reached_floor:
            body = _get_page(client, args.bananablocks_base, args.address, headers, args.page_size, cursor)
            pages += 1
            for item in body["items"]:
                row = _row_from_item(item) if isinstance(item, dict) else None
                if row is None:
                    continue
                txid, vout, sat = row
                # Fail safe: the stop condition below is only valid on a descending sort.
                if previous_value is not None and sat > previous_value:
                    print(
                        "error: listing is not sorted by value descending; aborting before "
                        "importing anything further",
                        file=sys.stderr,
                    )
                    return 3
                previous_value = sat
                if sat < args.min_sat:
                    reached_floor = True
                    break
                if (txid, vout) in seen:
                    continue
                seen.add((txid, vout))
                batch.append({"txid": txid, "vout": vout, "value_sat": sat})
                total_rows += 1
                total_sat += sat
                if len(batch) >= args.batch_size:
                    flush()

            cursor = body.get("cursor")
            if not body.get("hasMore") or not cursor:
                break
            time.sleep(0.3)

        flush()

    if args.dry_run:
        print(
            f"dry-run: eligible_outputs={total_rows} total_sat={total_sat} "
            f"(~{total_sat / 1e8:.4f} BSV) pages_fetched={pages} floor={args.min_sat} sat "
            f"reached_floor={reached_floor}"
        )
    else:
        print(
            f"done: eligible_outputs={total_rows} (~{total_sat / 1e8:.4f} BSV) "
            f"posted={posted} newly_inserted={inserted_total} "
            f"already_tracked={posted - inserted_total} pages_fetched={pages} "
            f"floor={args.min_sat} sat reached_floor={reached_floor}"
        )
    if pages >= args.max_pages and not reached_floor:
        print("warning: stopped at --max-pages before reaching the floor; raise it and rerun", file=sys.stderr)
        return 4
    if not args.dry_run:
        print("next: consolidate, then POST /utxo/refill and check /health")
    return 0


if __name__ == "__main__":
    sys.exit(main())
