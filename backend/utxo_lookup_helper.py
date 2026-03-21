#!/usr/bin/env python3
"""
One-off helper: show the P2PKH address for BSV_PRIVATE_KEY_WIF and try to list
unspent outputs via WhatsOnChain. Use output to call POST /utxo/reserve.

For very high–transaction-count addresses the API may time out; in that case use
a desktop wallet (e.g. ElectrumSV) → Coins / UTXO list, or a local node.

Does not print your private key. Run from backend/ with venv active:
    python utxo_lookup_helper.py
"""

from __future__ import annotations

import json
import sys

import httpx
from bitcoinx import Bitcoin, PrivateKey

from config import BSV_NETWORK, BSV_PRIVATE_KEY_WIF, WHATSONCHAIN_BASE_URL


def main() -> int:
    if not BSV_PRIVATE_KEY_WIF.strip():
        print("BSV_PRIVATE_KEY_WIF is empty in .env", file=sys.stderr)
        return 1

    pk = PrivateKey.from_WIF(BSV_PRIVATE_KEY_WIF)
    addr = pk.public_key.to_address(network=Bitcoin).to_string()

    print("=== OceanChain wallet (same key as main.py) ===")
    print(f"P2PKH address: {addr}")
    print()
    print("Your 0.9 BSV balance is held as one or more 'UTXO' rows.")
    print("Each row is: txid (64 hex) + vout (0, 1, 2…) + value_sat.")
    print()

    net = "main" if BSV_NETWORK.lower() in ("main", "mainnet", "livenet") else "test"
    url = f"{WHATSONCHAIN_BASE_URL}/{net}/address/{addr}/unspent"

    print(f"Fetching unspent list (may take a while): {url}")
    try:
        r = httpx.get(url, timeout=120.0)
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        print(f"\nWhatsOnChain request failed: {e}")
        print()
        print("--- Use a wallet instead (recommended if this always fails) ---")
        print("1. Install ElectrumSV (BSV).")
        print("2. New wallet → Standard wallet → Import Bitcoin addresses or private keys.")
        print("3. Paste the SAME WIF as in BSV_PRIVATE_KEY_WIF.")
        print("4. Open the 'Coins' / unspent list: each line shows txid, index (vout), amount.")
        print("5. amount in BSV × 100_000_000 = value_sat for that line.")
        print("6. POST /utxo/reserve once per UTXO you want to use for fan-out, then POST /utxo/refill.")
        return 2

    if not isinstance(rows, list) or not rows:
        print("No unspent outputs returned (empty list). Check address / network.")
        return 3

    # Normalise keys (WOC uses tx_hash, tx_pos, value in satoshis)
    normalised: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        txid = item.get("tx_hash") or item.get("txid")
        pos = item.get("tx_pos")
        if pos is None:
            pos = item.get("vout")
        val = item.get("value")
        if txid is None or pos is None or val is None:
            continue
        normalised.append(
            {"txid": str(txid), "vout": int(pos), "value_sat": int(val)}
        )

    normalised.sort(key=lambda x: -x["value_sat"])

    print(f"\nFound {len(normalised)} unspent output(s). Largest first:\n")
    for i, u in enumerate(normalised[:20], 1):
        print(f"{i}. txid={u['txid']}  vout={u['vout']}  value_sat={u['value_sat']}")

    if len(normalised) > 20:
        print(f"\n… and {len(normalised) - 20} more (not shown).")

    top = normalised[0]
    print("\n--- Example: register the largest UTXO as reserve ---")
    body = {"txid": top["txid"], "vout": top["vout"], "value_sat": top["value_sat"]}
    print("curl -sS -X POST http://127.0.0.1:8000/utxo/reserve \\")
    print("  -H 'Content-Type: application/json' \\")
    print(f"  -d '{json.dumps(body)}'")
    print("\nThen: curl -sS -X POST http://127.0.0.1:8000/utxo/refill")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
