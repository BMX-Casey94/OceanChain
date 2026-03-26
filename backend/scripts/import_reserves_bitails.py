#!/usr/bin/env python3
"""
Page Bitails `GET /address/{address}/unspent` and POST batches to OceanChain
`POST /utxo/reserves/bulk-import` (admin key).

Run on the VPS with the API listening on localhost (or set --api-base). Do not
log or commit the admin key.

Example (from `backend/` with venv active):

  python scripts/import_reserves_bitails.py \\
    --address 1YourP2PKHAddress \\
    --min-sat 1000

Then trigger fan-out:

  curl -sS -X POST http://127.0.0.1:8000/utxo/refill

To locate the largest unspents without scanning tx history, see
`scripts/list_largest_bitails_unspents.py`.
"""
from __future__ import annotations

import argparse
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
BULK_IMPORT_MAX = 25_000
USER_AGENT = "OceanChain-reserve-import/1.0"


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


def _post_batch(
    client: httpx.Client,
    api_base: str,
    admin_key: str,
    utxos: list[dict[str, Any]],
) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}/utxo/reserves/bulk-import"
    r = client.post(
        url,
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
        description="Import reserve UTXOs from Bitails into OceanChain bulk-import.",
    )
    p.add_argument(
        "--address",
        default=os.environ.get("OCEANCHAIN_FUNDING_ADDRESS", "").strip() or None,
        help="P2PKH address (or set OCEANCHAIN_FUNDING_ADDRESS).",
    )
    p.add_argument(
        "--api-base",
        default=os.environ.get("OCEANCHAIN_API_BASE", "http://127.0.0.1:8000").rstrip(
            "/"
        ),
        help="OceanChain HTTP root (default: http://127.0.0.1:8000 or OCEANCHAIN_API_BASE).",
    )
    p.add_argument(
        "--admin-key",
        default=os.environ.get("OCEANCHAIN_ADMIN_API_KEY", "").strip() or None,
        help="Admin API key (default: OCEANCHAIN_ADMIN_API_KEY env).",
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
        help="Bitails unspent page size (default 500).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("BULK_IMPORT_BATCH_SIZE", "5000")),
        help=f"UTXOs per POST (max {BULK_IMPORT_MAX}, default 5000).",
    )
    p.add_argument(
        "--min-sat",
        type=int,
        default=int(os.environ.get("BITAILS_IMPORT_MIN_SAT", "0")),
        help="Skip outputs below this value (satoshis). 0 = no client-side floor.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and filter only; do not POST to OceanChain.",
    )
    args = p.parse_args()

    if not args.address:
        print("error: --address or OCEANCHAIN_FUNDING_ADDRESS is required", file=sys.stderr)
        return 2
    if not args.admin_key and not args.dry_run:
        print(
            "error: --admin-key or OCEANCHAIN_ADMIN_API_KEY is required (unless --dry-run)",
            file=sys.stderr,
        )
        return 2
    if args.batch_size < 1 or args.batch_size > BULK_IMPORT_MAX:
        print(
            f"error: --batch-size must be 1..{BULK_IMPORT_MAX}",
            file=sys.stderr,
        )
        return 2
    if args.page_size < 1:
        print("error: --page-size must be >= 1", file=sys.stderr)
        return 2

    bitails_headers: dict[str, str] = {"User-Agent": USER_AGENT}
    if args.bitails_api_key:
        bitails_headers["apikey"] = args.bitails_api_key

    pending: list[dict[str, Any]] = []
    total_seen = 0
    total_skipped_min = 0
    total_posted = 0
    dry_would_import = 0
    offset = 0

    with httpx.Client() as client:

        def flush_pending() -> None:
            nonlocal pending, total_posted, dry_would_import
            if not pending:
                return
            if args.dry_run:
                dry_would_import += len(pending)
                print(f"dry-run: would POST batch of {len(pending)} UTXOs")
                pending = []
                return
            _post_batch(client, args.api_base, args.admin_key, pending)
            total_posted += len(pending)
            print(f"posted batch: {len(pending)} (cumulative {total_posted})")
            pending = []

        while True:
            url = f"{args.bitails_base}/address/{args.address}/unspent"
            br = client.get(
                url,
                params={"from": offset, "limit": args.page_size},
                headers=bitails_headers,
                timeout=120.0,
            )
            br.raise_for_status()
            data = br.json()
            page = _extract_unspent(data)
            if not page:
                break

            for item in page:
                row = _row_from_item(item)
                if row is None:
                    continue
                total_seen += 1
                txid, vout, sat = row
                if args.min_sat > 0 and sat < args.min_sat:
                    total_skipped_min += 1
                    continue
                pending.append(
                    {"txid": txid, "vout": vout, "value_sat": sat},
                )

                if len(pending) >= args.batch_size:
                    flush_pending()

            if len(page) < args.page_size:
                break
            offset += args.page_size

        flush_pending()

    if args.dry_run:
        print(
            f"dry-run: bitails_outputs_seen={total_seen} client_skipped_min_sat={total_skipped_min} "
            f"would_import_total={dry_would_import}"
        )
        return 0

    print(
        f"done: bitails_outputs_seen={total_seen} client_skipped_min_sat={total_skipped_min} "
        f"utxos_posted={total_posted}"
    )
    print("next: POST /utxo/refill then check /health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
