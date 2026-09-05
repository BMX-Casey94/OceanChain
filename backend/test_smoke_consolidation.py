#!/usr/bin/env python3
"""
Offline smoke tests for reserve consolidation (no DB, no network, no real funds).

Covers the pure tx-building path used by UTXOManager.consolidate_reserve:
  * structure: N P2PKH inputs -> exactly one P2PKH output back to the wallet
  * fee sufficiency: the 150 vbytes/input estimate always covers the actual
    signed size (so the configured fee rate is never underpaid), even at the
    production chunk cap of CONSOLIDATION_MAX_INPUTS
  * signatures: every input's DER signature verifies against the BSV
    SigHash ALL | FORKID digest — the same helper signs fan-out refills
  * guards: < 2 inputs and fee-uncoverable input sets raise ValueError

Run from backend/ with the venv active:

    python test_smoke_consolidation.py
"""
from __future__ import annotations

import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitcoinx import Bitcoin, SigHash, Tx  # noqa: E402

from tx_builder import calculate_fee  # noqa: E402
from utxo_manager import (  # noqa: E402
    _CONSOLIDATION_INPUT_VBYTES,
    _build_consolidation_tx,
)
from bitcoinx import PrivateKey  # noqa: E402


def _fresh_key() -> PrivateKey:
    return PrivateKey.from_hex(secrets.token_hex(32))


def _fake_utxos(n: int, value_sat: int) -> list[dict]:
    return [
        {"txid": secrets.token_hex(32), "vout": i % 4, "value_sat": value_sat}
        for i in range(n)
    ]


def _first_push(script: bytes) -> bytes:
    n = script[0]
    assert 1 <= n <= 75, f"unexpected push length {n}"
    return script[1 : 1 + n]


def test_structure_and_fee() -> None:
    key = _fresh_key()
    address = key.public_key.to_address(network=Bitcoin).to_string()
    utxos = [
        {"txid": secrets.token_hex(32), "vout": 0, "value_sat": 10_000},
        {"txid": secrets.token_hex(32), "vout": 1, "value_sat": 5_000},
        {"txid": secrets.token_hex(32), "vout": 2, "value_sat": 2_537},
    ]
    raw_hex, txid, fee_sat, output_value = _build_consolidation_tx(utxos, address, key)

    sum_in = 17_537
    expected_fee = calculate_fee(10 + 3 * _CONSOLIDATION_INPUT_VBYTES + 34)
    assert fee_sat == expected_fee, (fee_sat, expected_fee)
    assert output_value == sum_in - fee_sat, (output_value, sum_in, fee_sat)
    assert len(txid) == 64 and txid == txid.lower()

    tx = Tx.from_hex(raw_hex)
    assert tx.hex_hash().lower() == txid
    assert len(tx.inputs) == 3
    assert len(tx.outputs) == 1, "consolidation must produce exactly one output"
    assert int(tx.outputs[0].value) == output_value
    expected_script = key.public_key.P2PKH_script().to_bytes()
    assert bytes(tx.outputs[0].script_pubkey) == expected_script
    for txin in tx.inputs:
        script = bytes(txin.script_sig)
        assert script, "input must be signed"
        assert _first_push(script)[-1] == 0x41, "SigHash must be ALL | FORKID"
    print("ok - structure_and_fee")


def test_fee_covers_actual_signed_size() -> None:
    key = _fresh_key()
    address = key.public_key.to_address(network=Bitcoin).to_string()
    for n in (2, 3, 25, 400):  # 400 == default CONSOLIDATION_MAX_INPUTS chunk
        utxos = _fake_utxos(n, 1_000)
        raw_hex, _, fee_sat, _ = _build_consolidation_tx(utxos, address, key)
        actual_bytes = len(bytes(Tx.from_hex(raw_hex).to_bytes()))
        est_bytes = 10 + n * _CONSOLIDATION_INPUT_VBYTES + 34
        assert actual_bytes <= est_bytes, (
            f"n={n}: actual {actual_bytes} exceeds estimate {est_bytes} — fee would underpay"
        )
        # And the fee really does pay for the actual size at the configured rate.
        assert fee_sat >= calculate_fee(actual_bytes), (n, fee_sat, actual_bytes)
    print("ok - fee_covers_actual_signed_size")


def test_signatures_verify() -> None:
    key = _fresh_key()
    address = key.public_key.to_address(network=Bitcoin).to_string()
    utxos = _fake_utxos(5, 4_321)
    raw_hex, _, _, _ = _build_consolidation_tx(utxos, address, key)
    tx = Tx.from_hex(raw_hex)
    script_code = key.public_key.P2PKH_script()
    for idx, utxo in enumerate(utxos):
        sig_with_type = _first_push(bytes(tx.inputs[idx].script_sig))
        der_sig = sig_with_type[:-1]
        digest = tx.signature_hash(
            input_index=idx,
            value=utxo["value_sat"],
            script_code=script_code,
            sighash=SigHash(0x41),
        )
        assert key.public_key.verify_der_signature(der_sig, digest, hasher=None), (
            f"input {idx} signature does not verify"
        )
    print("ok - signatures_verify")


def test_requires_two_inputs() -> None:
    key = _fresh_key()
    address = key.public_key.to_address(network=Bitcoin).to_string()
    try:
        _build_consolidation_tx(_fake_utxos(1, 100_000), address, key)
    except ValueError:
        print("ok - requires_two_inputs")
        return
    raise AssertionError("single-input consolidation must raise ValueError")


def test_uneconomical_rejected() -> None:
    key = _fresh_key()
    address = key.public_key.to_address(network=Bitcoin).to_string()
    # 2 x 10 sat can never cover a ~2-input fee at any sane rate.
    try:
        _build_consolidation_tx(_fake_utxos(2, 10), address, key)
    except ValueError:
        print("ok - uneconomical_rejected")
        return
    raise AssertionError("fee-uncoverable consolidation must raise ValueError")


def main() -> int:
    test_structure_and_fee()
    test_fee_covers_actual_signed_size()
    test_signatures_verify()
    test_requires_two_inputs()
    test_uneconomical_rejected()
    print("all consolidation smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
