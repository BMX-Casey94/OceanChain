#!/usr/bin/env python3
"""
Reconcile the Postgres `reserve` rows with the chain, for a quiet (stopped) service.

Why: the importer is insert-only and the app deletes a coin's row when it spends it. If the
importer runs while a spend is still unconfirmed it re-adds the already-spent coin, and the
reaper can quarantine coins whose transactions later mine. This script repairs both
directions from the confirmed chain state:

  * MISSING: confirmed unspent outputs of this wallet (BananaBlocks, value-descending,
    down to --min-sat) that no `utxos` row tracks under any role are inserted as reserve.
  * STALE:   `reserve` rows (not pending, value >= the floor, older than --quiet-minutes)
    that are NOT in that confirmed unspent set are copied to `quarantined_utxos` and then
    deleted in one transaction, never silently dropped. Pool rows are never touched.

The confirmed set only equals the truth when nothing is still unconfirmed, so the script
refuses to run unless ALL of these hold:
  1. --address is this wallet's own address.
  2. The OceanChain API is confirmed down (connection refused). A timeout or any HTTP
     response counts as "maybe running" and refuses. Checked again just before writing.
  3. No `utxos` row is pending.
  4. The newest row in `utxos` is at least --quiet-minutes old (the service has been
     stopped long enough for everything it broadcast to be mined), and the 25 newest
     transactions it created are confirmed on WhatsOnChain.
  5. The BananaBlocks listing is complete and well-formed (any malformed item, missing
     cursor, or max-pages hit aborts before anything is written).
  6. The confirmed set is not empty while reserve rows exist.
Dry run by default; add --execute to write.

Run from the backend directory with the venv python:
  python scripts/reconcile_reserves.py                 # dry run
  python scripts/reconcile_reserves.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

BANANABLOCKS_BASE = os.environ.get("BANANABLOCKS_API_BASE", "https://bananablocks.com/api/v1").rstrip("/")
WOC_BASE = "https://api.whatsonchain.com/v1/bsv/main"
USER_AGENT = "OceanChain-reconcile-reserves/1.0"
_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{25,35}$")
_TXID_RE = re.compile(r"^[0-9a-f]{64}$")
RECENT_TXIDS_TO_VERIFY = 25


def _service_state(api_base: str) -> str:
    """'stopped' only on a refused connection; anything else is 'running' or 'unknown'."""
    try:
        httpx.get(f"{api_base}/health", timeout=5.0)
        return "running"
    except httpx.ConnectError:
        return "stopped"
    except httpx.HTTPError:
        return "unknown"


def _get(client: httpx.Client, url: str, headers: dict, params: dict | None = None):
    for _ in range(6):
        r = client.get(url, params=params, headers=headers, timeout=120.0)
        if r.status_code == 429:
            print("rate limited (429); waiting 65s", file=sys.stderr)
            time.sleep(65)
            continue
        return r
    raise RuntimeError("rate limit persisted after retries")


def _fetch_confirmed_unspent(address: str, floor: int, page_size: int, max_pages: int) -> dict[tuple[str, int], int]:
    """
    Complete confirmed unspent set >= floor, or raise. Never returns a partial set.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    key = os.environ.get("BANANABLOCKS_API_KEY", "").strip()
    if key:
        headers["X-API-Key"] = key
    found: dict[tuple[str, int], int] = {}
    previous: int | None = None
    cursor = None
    pages = 0
    with httpx.Client() as client:
        while pages < max_pages:
            params = {"sort": "value:desc", "limit": page_size}
            if cursor:
                params["cursor"] = cursor
            r = _get(client, f"{BANANABLOCKS_BASE}/address/{quote(address, safe='')}/utxos", headers, params)
            r.raise_for_status()
            body = r.json()
            pages += 1
            items = body.get("items")
            if not isinstance(items, list) or "hasMore" not in body:
                raise RuntimeError("unexpected BananaBlocks response shape; refusing")
            floor_hit = False
            for it in items:
                try:
                    value = int(it["value"])
                    txid = str(it["txid"]).strip().lower()
                    vout = int(it["vout"])
                    height = int(it.get("block_height") or 0)
                except (KeyError, TypeError, ValueError) as e:
                    raise RuntimeError(f"malformed listing item {it!r}: {e}") from e
                if previous is not None and value > previous:
                    raise RuntimeError("BananaBlocks listing is not value-descending; refusing")
                previous = value
                if value < floor:
                    floor_hit = True  # keep scanning this page for ordering violations
                    continue
                if height <= 0 or not _TXID_RE.match(txid) or vout < 0 or value < 1:
                    raise RuntimeError(f"unconfirmed or malformed item in confirmed listing: {it!r}")
                found[(txid, vout)] = value
            if floor_hit:
                return found
            more = body.get("hasMore")
            cursor = body.get("cursor")
            if not more:
                return found
            if not cursor:
                raise RuntimeError("hasMore is true but no cursor was returned; refusing")
            time.sleep(0.3)
    raise RuntimeError(f"stopped at --max-pages={max_pages} before reaching the floor; raise it")


def _unconfirmed_among(txids: list[str]) -> list[str]:
    """Txids that are not confirmed (or cannot be checked): fail closed."""
    bad: list[str] = []
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with httpx.Client() as client:
        for t in txids:
            try:
                r = _get(client, f"{WOC_BASE}/tx/hash/{t}", headers)
                ok = r.status_code == 200 and int(r.json().get("confirmations") or 0) >= 1
            except Exception:  # noqa: BLE001
                ok = False
            if not ok:
                bad.append(t)
            time.sleep(0.4)  # WhatsOnChain public limit is ~3 requests/second
    return bad


async def _run(args) -> int:
    import asyncpg
    from config import DATABASE_URL
    from tx_builder import get_change_address

    own = get_change_address()
    address = args.address or own
    if address != own or not _ADDRESS_RE.match(address):
        print(f"error: --address must be this wallet's own address ({own})", file=sys.stderr)
        return 2
    if _service_state(args.api_base) != "stopped":
        print(f"OceanChain API on {args.api_base} is running or not confirmed down. Run: systemctl stop oceanchain",
              file=sys.stderr)
        return 4

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        if await conn.fetchval("SELECT EXISTS (SELECT 1 FROM utxos WHERE pending = TRUE)"):
            print("Pending rows exist: transactions are still unpromoted. Start the service, "
                  "let the reaper clear them, stop it, wait, and rerun.", file=sys.stderr)
            return 5
        quiet_ok = await conn.fetchval(
            "SELECT COALESCE(MAX(created_at) < NOW() - make_interval(mins => $1), TRUE) FROM utxos",
            args.quiet_minutes,
        )
        if not quiet_ok:
            print(f"The newest utxos row is under {args.quiet_minutes} minutes old. "
                  "Keep the service stopped until then so everything it broadcast is mined.", file=sys.stderr)
            return 5

        recent = await conn.fetch(
            "SELECT txid FROM utxos GROUP BY txid ORDER BY MAX(created_at) DESC LIMIT $1",
            RECENT_TXIDS_TO_VERIFY,
        )
        recent_txids = [str(r["txid"]) for r in recent]
        print(f"verifying the {len(recent_txids)} newest app transactions are confirmed...")
        bad = _unconfirmed_among(recent_txids)
        if bad:
            print(f"{len(bad)} recent transaction(s) not confirmed (e.g. {bad[0]}). "
                  "Wait for the next block and rerun.", file=sys.stderr)
            return 5

        print("fetching confirmed unspent outputs (largest first)...")
        chain = _fetch_confirmed_unspent(address, args.min_sat, args.page_size, args.max_pages)
        print(f"chain: {len(chain)} confirmed outputs >= {args.min_sat} sat, {sum(chain.values())} sat")

        tracked = {
            (str(r["txid"]), int(r["vout"]))
            for r in await conn.fetch("SELECT txid, vout FROM utxos")
        }
        reserve_rows = await conn.fetch(
            """
            SELECT txid, vout, value_sat FROM utxos
            WHERE utxo_role = 'reserve' AND pending = FALSE AND value_sat >= $1
              AND created_at < NOW() - make_interval(mins => $2)
            """,
            args.min_sat,
            args.quiet_minutes,
        )
        if not chain and reserve_rows:
            print("The confirmed set is empty but reserve rows exist; refusing to quarantine them all.",
                  file=sys.stderr)
            return 6

        missing = [(k, v) for k, v in chain.items() if k not in tracked]
        stale = [
            (str(r["txid"]), int(r["vout"]), int(r["value_sat"]))
            for r in reserve_rows
            if (str(r["txid"]), int(r["vout"])) not in chain
        ]
        print(
            f"MISSING (on chain, untracked): {len(missing)} outputs, {sum(v for _, v in missing)} sat\n"
            f"STALE   (tracked reserve, not on chain): {len(stale)} rows, {sum(s[2] for s in stale)} sat"
        )
        if not args.execute:
            print("DRY RUN: nothing changed. Add --execute to apply.")
            return 0

        # The listing can take minutes: confirm the service is still down immediately before writing.
        if _service_state(args.api_base) != "stopped":
            print("The service is running again; aborting before any write.", file=sys.stderr)
            return 4

        async with conn.transaction():
            if stale:
                st = [s[0] for s in stale]
                sv = [s[1] for s in stale]
                await conn.execute(
                    """
                    INSERT INTO quarantined_utxos
                        (txid, vout, value_sat, utxo_role, submit_mask, created_at)
                    SELECT x.txid, x.vout, x.value_sat, x.utxo_role, x.submit_mask, x.created_at
                    FROM utxos x
                    JOIN unnest($1::text[], $2::int[]) AS u(t, v) ON x.txid = u.t AND x.vout = u.v
                    WHERE x.utxo_role = 'reserve' AND x.pending = FALSE
                    ON CONFLICT (txid, vout) DO NOTHING
                    """,
                    st, sv,
                )
                await conn.execute(
                    """
                    DELETE FROM utxos x USING unnest($1::text[], $2::int[]) AS u(t, v)
                    WHERE x.txid = u.t AND x.vout = u.v
                      AND x.utxo_role = 'reserve' AND x.pending = FALSE
                    """,
                    st, sv,
                )
            if missing:
                await conn.execute(
                    """
                    INSERT INTO utxos (txid, vout, value_sat, utxo_role, locked)
                    SELECT u.t, u.v, u.s, 'reserve', FALSE
                    FROM unnest($1::text[], $2::int[], $3::bigint[]) AS u(t, v, s)
                    ON CONFLICT (txid, vout) DO NOTHING
                    """,
                    [k[0] for k, _ in missing],
                    [k[1] for k, _ in missing],
                    [v for _, v in missing],
                )
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS n, COALESCE(SUM(value_sat),0) AS s FROM utxos WHERE utxo_role='reserve'"
        )
        print(f"DONE. reserve rows now: {row['n']} totalling {row['s']} sat")
        return 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--address", default="", help="Must equal this wallet's address (default).")
    p.add_argument("--api-base", default=os.environ.get("OCEANCHAIN_API_BASE", "http://127.0.0.1:8000").rstrip("/"))
    p.add_argument("--min-sat", type=int, default=1000)
    p.add_argument("--page-size", type=int, default=1000)
    p.add_argument("--max-pages", type=int, default=200)
    p.add_argument("--quiet-minutes", type=int, default=30)
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    if not 1 <= args.page_size <= 1000 or args.min_sat < 1 or args.quiet_minutes < 10:
        print("error: --page-size 1..1000, --min-sat >= 1, --quiet-minutes >= 10", file=sys.stderr)
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
