#!/usr/bin/env python3
"""
One-off outbound payment from the OceanChain wallet (no API endpoint on purpose).

A permanent "send funds" HTTP endpoint would let a leaked admin key drain the
wallet, so this is a local command that needs shell access to the VPS and the
wallet key in .env.

Safety properties:
  * Dry run by default. Nothing is signed or broadcast without --execute.
  * --execute also needs --confirm-address, typed out and equal to --to.
  * Hard cap (MAX_SEND_SAT). Destination is checksum-validated as mainnet P2PKH.
  * Inputs come from BananaBlocks' confirmed-only listing of this wallet's own
    address, largest first, so unconfirmed (sweep) outputs are never spent.
  * Refuses to run while the OceanChain API answers on --api-base: a running
    service could pick the same coins for a fan-out. Stop it first.
  * Writes a marker file before updating Postgres; a second run is refused
    until the marker is removed by hand, so a retry cannot pay twice.
  * After broadcast, the spent input rows are removed from `utxos` and the change
    is recorded as pending reserve (the reaper promotes it), exactly as
    consolidation does. The private key is never printed.

Run from the backend directory with the venv python:
  python scripts/send_once.py --to 12rQ... --amount-sat 10000                 # dry run
  python scripts/send_once.py --to 12rQ... --amount-sat 10000 \\
      --execute --confirm-address 12rQ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

MAX_SEND_SAT = 100_000_000  # 1 BSV hard ceiling for this tool
MAX_INPUTS = 50
INPUT_VBYTES = 150  # worst-case signed P2PKH input
BANANABLOCKS_BASE = os.environ.get("BANANABLOCKS_API_BASE", "https://bananablocks.com/api/v1").rstrip("/")
MARKER = Path(__file__).resolve().parent.parent / ".send_once_done.json"


def _service_is_running(api_base: str) -> bool:
    try:
        httpx.get(f"{api_base}/health", timeout=3.0)
        return True
    except httpx.HTTPError:
        return False


def _confirmed_coins_largest_first(address: str, needed: int) -> list[dict]:
    """Pull confirmed outputs, largest first, until they cover `needed` sat."""
    headers = {"User-Agent": "OceanChain-send-once/1.0", "Accept": "application/json"}
    key = os.environ.get("BANANABLOCKS_API_KEY")
    if key:
        headers["X-API-Key"] = key
    coins: list[dict] = []
    total = 0
    last_value = None
    cursor = None
    with httpx.Client() as client:
        while len(coins) < MAX_INPUTS and total < needed:
            params = {"sort": "value:desc", "limit": 50}
            if cursor:
                params["cursor"] = cursor
            r = client.get(
                f"{BANANABLOCKS_BASE}/address/{quote(address, safe='')}/utxos",
                params=params, headers=headers, timeout=120.0,
            )
            r.raise_for_status()
            body = r.json()
            for it in body.get("items", []):
                value = int(it["value"])
                if last_value is not None and value > last_value:
                    raise RuntimeError("BananaBlocks listing is not value-descending; refusing")
                last_value = value
                if int(it.get("block_height") or 0) <= 0:
                    continue  # confirmed only
                coins.append({"txid": str(it["txid"]).lower(), "vout": int(it["vout"]), "value_sat": value})
                total += value
                if len(coins) >= MAX_INPUTS or total >= needed:
                    break
            cursor = body.get("cursor")
            if not body.get("hasMore") or not cursor:
                break
    return coins


def _build(coins, dest_address, amount, change_address, private_key):
    from bitcoinx import Bitcoin, P2PKH_Address, Script, Tx, TxInput, TxOutput
    from tx_builder import calculate_fee
    from config import MIN_CHANGE_OUTPUT_SAT
    from utxo_manager import _sign_p2pkh_inputs

    sum_in = sum(c["value_sat"] for c in coins)
    fee = calculate_fee(10 + len(coins) * INPUT_VBYTES + 2 * 34)
    change = sum_in - amount - fee
    if change < MIN_CHANGE_OUTPUT_SAT:
        raise ValueError(f"inputs {sum_in} sat cannot cover {amount} + fee {fee} + minimum change")
    outputs = [
        TxOutput(amount, P2PKH_Address.from_string(dest_address, Bitcoin).to_script()),
        TxOutput(change, P2PKH_Address.from_string(change_address, Bitcoin).to_script()),
    ]
    inputs = [TxInput(bytes.fromhex(c["txid"])[::-1], c["vout"], Script(), 0xFFFFFFFF) for c in coins]
    tx = Tx(version=1, inputs=inputs, outputs=outputs, locktime=0)
    _sign_p2pkh_inputs(tx, coins, private_key, private_key.public_key)
    return tx.to_bytes().hex(), tx.hex_hash().lower(), fee, change


async def _run(args) -> int:
    from bitcoinx import Bitcoin, P2PKH_Address, PrivateKey
    from config import BSV_PRIVATE_KEY_WIF, DATABASE_URL, GORILLA_TX_FORMAT
    from tx_builder import get_change_address, to_extended_format_hex

    try:
        dest = P2PKH_Address.from_string(args.to, Bitcoin)
    except Exception as e:  # noqa: BLE001
        print(f"Destination is not a valid mainnet P2PKH address: {e}", file=sys.stderr)
        return 2
    if not 1 <= args.amount_sat <= MAX_SEND_SAT:
        print(f"--amount-sat must be 1..{MAX_SEND_SAT}", file=sys.stderr)
        return 2

    own = get_change_address()
    if args.to == own:
        print("Destination is this wallet's own address; refusing.", file=sys.stderr)
        return 2
    if MARKER.exists():
        print(f"{MARKER} exists: a send was already made. Inspect it, then delete it by hand to send again.",
              file=sys.stderr)
        return 5
    if args.execute and args.confirm_address != args.to:
        print("--confirm-address must exactly equal --to when using --execute.", file=sys.stderr)
        return 2
    if _service_is_running(args.api_base):
        print(f"OceanChain API is answering on {args.api_base}. Run: systemctl stop oceanchain", file=sys.stderr)
        return 4

    # Over-ask slightly so the largest-first pick leaves room for the fee and change.
    coins = _confirmed_coins_largest_first(own, args.amount_sat + 2_000 + MAX_INPUTS * 20)
    private_key = PrivateKey.from_WIF(BSV_PRIVATE_KEY_WIF)
    try:
        raw_hex, txid, fee, change = _build(coins, args.to, args.amount_sat, own, private_key)
    except ValueError as e:
        print(f"Cannot build: {e}\nConfirmed coins found: {len(coins)}, "
              f"{sum(c['value_sat'] for c in coins)} sat. If the sweep is unmined, wait.", file=sys.stderr)
        return 3

    plan = {
        "from": own, "to": args.to, "amount_sat": args.amount_sat, "fee_sat": fee,
        "change_sat": change, "inputs": len(coins),
        "input_sat": sum(c["value_sat"] for c in coins), "txid": txid, "tx_bytes": len(raw_hex) // 2,
    }
    print(json.dumps(plan, indent=2))
    if not args.execute:
        print("DRY RUN: nothing broadcast. Add --execute --confirm-address <to> to send.")
        return 0

    from broadcaster import submit, BroadcastError

    gorilla_hex = None
    if GORILLA_TX_FORMAT != "raw":
        script_hex = private_key.public_key.P2PKH_script().to_bytes().hex()
        gorilla_hex = to_extended_format_hex(
            raw_hex, [{"value_sat": c["value_sat"], "locking_script_hex": script_hex} for c in coins]
        )
    submit_mask = None
    try:
        result = await submit(raw_hex, gorilla_tx_hex=gorilla_hex)
        submit_mask = int(result.get("submit_mask") or 1)
        print(f"Broadcast OK via {result.get('broadcaster')} status={result.get('status')}")
    except BroadcastError as e:
        if getattr(e, "submit_mask", None):
            submit_mask = int(e.submit_mask)
            print(f"Posted but parked by an endpoint (submit_mask={submit_mask}): {e}", file=sys.stderr)
        else:
            print(f"Broadcast failed, nothing was sent: {e}", file=sys.stderr)
            return 6

    MARKER.write_text(json.dumps({**plan, "at": int(time.time()), "submit_mask": submit_mask}))
    print(f"Marker written: {MARKER}")

    import asyncpg

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        async with conn.transaction():
            await conn.executemany(
                "DELETE FROM utxos WHERE txid = $1 AND vout = $2 AND utxo_role = 'reserve'",
                [(c["txid"], c["vout"]) for c in coins],
            )
            await conn.execute(
                """
                INSERT INTO utxos (txid, vout, value_sat, utxo_role, locked, pending, submit_mask)
                VALUES ($1, 1, $2, 'reserve', FALSE, TRUE, $3)
                ON CONFLICT (txid, vout) DO NOTHING
                """,
                txid, change, submit_mask,
            )
    finally:
        await conn.close()
    print(f"DONE. txid={txid}  explorer: https://whatsonchain.com/tx/{txid}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--to", required=True)
    p.add_argument("--amount-sat", type=int, required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--confirm-address", default="")
    p.add_argument("--api-base", default=os.environ.get("OCEANCHAIN_API_BASE", "http://127.0.0.1:8000").rstrip("/"))
    return asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
