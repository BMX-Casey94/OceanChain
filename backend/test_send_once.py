"""Offline tests for scripts/send_once.py transaction building (throwaway key, no network)."""
import os
import sys
from pathlib import Path

from bitcoinx import Bitcoin, PrivateKey, Tx

_KEY = PrivateKey.from_random()
os.environ["BSV_PRIVATE_KEY_WIF"] = _KEY.to_WIF()
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import send_once  # noqa: E402

DEST = "12rQ4ENSF3eaN2FWBCfgwmyQXRFnP9KNrz"
OWN = _KEY.public_key.to_address(network=Bitcoin).to_string()


def test_builds_two_outputs_and_balances():
    coins = [
        {"txid": "ab" * 32, "vout": 3, "value_sat": 30_000_000},
        {"txid": "cd" * 32, "vout": 0, "value_sat": 25_000_000},
    ]
    raw, txid, fee, change = send_once._build(coins, DEST, 50_000_000, OWN, _KEY)
    tx = Tx.from_hex(raw)
    assert len(tx.inputs) == 2
    assert [o.value for o in tx.outputs] == [50_000_000, change]
    assert 55_000_000 - 50_000_000 - fee == change
    assert tx.hex_hash().lower() == txid
    assert all(len(i.script_sig) > 100 for i in tx.inputs)


def test_rejects_when_change_would_be_unviable():
    try:
        send_once._build([{"txid": "ab" * 32, "vout": 0, "value_sat": 50_000_010}], DEST, 50_000_000, OWN, _KEY)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


if __name__ == "__main__":
    test_builds_two_outputs_and_balances()
    test_rejects_when_change_would_be_unviable()
    print("SEND_ONCE_OK")
