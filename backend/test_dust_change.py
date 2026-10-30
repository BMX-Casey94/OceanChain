#!/usr/bin/env python3
"""
Offline tests for dust change omission in build_op_return_tx.

No database, no network, and no real funds. After tx_builder is imported, the
configured WIF is replaced with a key generated in this process, and the change
address is derived from that same key.

Covers:
  * a healthy coin keeps a P2PKH change output and pays a sufficient fee
  * an end-of-life coin omits change, pays the whole input as fee, and the
    output-count flip from 1 to 2 is monotonic
  * signatures verify for both shapes under SigHash ALL | FORKID
  * a value below the fee raises ValueError
  * canonical txids match bitcoinx for both shapes
  * change is never a sub-viable amount

Run from backend/ with the venv active:

    python test_dust_change.py
"""
from __future__ import annotations

import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitcoinx import Bitcoin, P2PKH_Address, PrivateKey, SigHash, Tx  # noqa: E402

import tx_builder  # noqa: E402
from tx_builder import (  # noqa: E402
    ESTIMATED_TX_SIZE,
    _build_op_return_script,
    build_op_return_tx,
    calculate_fee,
    canonical_txid_from_raw_hex,
    encode_position_for_op_return,
    minimum_viable_utxo_value,
)

# build_op_return_tx reads this module global at call time. Replace it before
# any transaction is built so the configured key is never used.
_KEY = PrivateKey.from_hex(secrets.token_hex(32))
tx_builder.BSV_PRIVATE_KEY_WIF = _KEY.to_WIF()
# Omission is opt-in (OMIT_DUST_CHANGE, default off in config). Enable it for the
# omission tests; test_flag_off_keeps_change restores the default and checks it.
tx_builder.OMIT_DUST_CHANGE = True
_CHANGE_ADDRESS = _KEY.public_key.to_address(network=Bitcoin).to_string()

_POSITION = {
    "mmsi": 235012345,
    "latitude": 51.5074,
    "longitude": -0.1278,
    "speed": 12.4,
    "heading": 180,
    "timestamp": 1_700_000_000,
}

# Inclusive scan cap from the omission search. The flip sits well below this
# at the configured fee rate; the test fails if it does not.
_SEARCH_UPPER_SAT = 400


def _utxo(value_sat: int) -> dict:
    return {"txid": secrets.token_hex(32), "vout": 0, "value_sat": value_sat}


def _first_push(script: bytes) -> bytes:
    n = script[0]
    assert 1 <= n <= 75, f"unexpected push length {n}"
    return script[1 : 1 + n]


def _op_return_script() -> bytes:
    payload = encode_position_for_op_return(_POSITION)
    return _build_op_return_script(payload).to_bytes()


def _change_script() -> bytes:
    return P2PKH_Address.from_string(_CHANGE_ADDRESS, Bitcoin).to_script().to_bytes()


def _build(value_sat: int) -> tuple[str, int, Tx]:
    try:
        raw_hex, change = build_op_return_tx(_utxo(value_sat), _POSITION, _CHANGE_ADDRESS)
    except ValueError as exc:
        raise AssertionError(f"value {value_sat} sat unexpectedly raised: {exc}") from exc
    return raw_hex, change, Tx.from_hex(raw_hex)


def _serialised_size(raw_hex: str, tx: Tx) -> int:
    size = len(bytes.fromhex(raw_hex))
    assert size == len(tx.to_bytes()), (size, len(tx.to_bytes()))
    return size


def _assert_op_return(tx: Tx) -> bytes:
    assert len(tx.inputs) == 1
    script = bytes(tx.outputs[0].script_pubkey)
    assert int(tx.outputs[0].value) == 0, int(tx.outputs[0].value)
    assert script[:2] == b"\x00\x6a", script[:2].hex()
    assert script == _op_return_script()
    return script


def _assert_fee_covers(raw_hex: str, tx: Tx, fee_paid: int) -> None:
    size = _serialised_size(raw_hex, tx)
    required = calculate_fee(size)
    assert fee_paid >= required, (fee_paid, required, size)


def _assert_signature(tx: Tx, input_value: int) -> None:
    sig_with_type = _first_push(bytes(tx.inputs[0].script_sig))
    assert sig_with_type[-1] == 0x41, "SigHash must be ALL | FORKID"
    digest = tx.signature_hash(
        input_index=0,
        value=input_value,
        script_code=_KEY.public_key.P2PKH_script(),
        sighash=SigHash(0x41),
    )
    assert _KEY.public_key.verify_der_signature(sig_with_type[:-1], digest, hasher=None), (
        f"signature does not verify for input value {input_value}"
    )


def _assert_omitted(value_sat: int, raw_hex: str, change: int, tx: Tx, normal_script: bytes) -> None:
    assert len(tx.outputs) == 1, (value_sat, len(tx.outputs))
    assert change == 0, (value_sat, change)
    script = _assert_op_return(tx)
    assert script == normal_script, value_sat
    fee_paid = value_sat - sum(int(out.value) for out in tx.outputs)
    assert fee_paid == value_sat, (value_sat, fee_paid, change)
    _assert_fee_covers(raw_hex, tx, fee_paid)


def _assert_change_kept(value_sat: int, raw_hex: str, change: int, tx: Tx) -> None:
    minimum = minimum_viable_utxo_value()
    assert len(tx.outputs) == 2, (value_sat, len(tx.outputs))
    _assert_op_return(tx)
    assert int(tx.outputs[1].value) == change, (value_sat, int(tx.outputs[1].value), change)
    assert bytes(tx.outputs[1].script_pubkey) == _change_script()
    assert change >= minimum, (value_sat, change, minimum)
    fee_paid = value_sat - change
    assert fee_paid == value_sat - int(tx.outputs[1].value)
    _assert_fee_covers(raw_hex, tx, fee_paid)


def test_healthy_coin() -> None:
    value_sat = 10_000
    raw_hex, change, tx = _build(value_sat)
    _assert_change_kept(value_sat, raw_hex, change, tx)
    print("PASS test_healthy_coin")


def test_end_of_life_coin() -> None:
    minimum = minimum_viable_utxo_value()
    assert minimum < _SEARCH_UPPER_SAT, (
        f"minimum viable {minimum} sat is not below the search cap {_SEARCH_UPPER_SAT}"
    )

    # One normal (two-output) encoding, used to prove omitted scripts match it.
    normal_raw, normal_change, normal_tx = _build(10_000)
    _assert_change_kept(10_000, normal_raw, normal_change, normal_tx)
    normal_script = bytes(normal_tx.outputs[0].script_pubkey)

    rows: list[tuple[int, str, int, Tx]] = []
    for value_sat in range(minimum, _SEARCH_UPPER_SAT + 1):
        raw_hex, change, tx = _build(value_sat)
        n_outputs = len(tx.outputs)
        assert n_outputs in (1, 2), (value_sat, n_outputs)
        rows.append((value_sat, raw_hex, change, tx))

    seen_two = False
    first_kept: int | None = None
    for value_sat, _raw_hex, _change, tx in rows:
        n_outputs = len(tx.outputs)
        if n_outputs == 2:
            if not seen_two:
                first_kept = value_sat
                seen_two = True
            continue
        assert not seen_two, (
            f"value {value_sat} sat reverted to 1 output after omission stopped at {first_kept}"
        )

    assert first_kept is not None, (
        f"output count never flipped from 1 to 2 between {minimum} and {_SEARCH_UPPER_SAT}"
    )
    last_omitted = first_kept - 1
    assert last_omitted >= minimum, (last_omitted, minimum, first_kept)

    # Just above the viable floor, plus the largest value that still omits change.
    sample_values = (minimum, minimum + 1, minimum + 10, last_omitted)
    by_value = {value_sat: (raw_hex, change, tx) for value_sat, raw_hex, change, tx in rows}
    for value_sat in sample_values:
        assert value_sat < first_kept, (value_sat, first_kept)
        raw_hex, change, tx = by_value[value_sat]
        _assert_omitted(value_sat, raw_hex, change, tx, normal_script)

    kept_raw, kept_change, kept_tx = by_value[first_kept]
    _assert_change_kept(first_kept, kept_raw, kept_change, kept_tx)

    print(
        "PASS test_end_of_life_coin "
        f"(omission stops at {first_kept} sat; last omitted value {last_omitted} sat)"
    )


def test_signatures_verify() -> None:
    # Far from the omission boundary: one coin that keeps change, one that drops it.
    for value_sat in (10_000, minimum_viable_utxo_value()):
        _raw_hex, _change, tx = _build(value_sat)
        _assert_signature(tx, value_sat)
    print("PASS test_signatures_verify")


def test_insufficient_value() -> None:
    estimated_fee = calculate_fee(ESTIMATED_TX_SIZE)
    value_sat = estimated_fee - 1
    assert value_sat >= 0, estimated_fee
    try:
        build_op_return_tx(_utxo(value_sat), _POSITION, _CHANGE_ADDRESS)
    except ValueError as exc:
        assert "Insufficient UTXO value" in str(exc), str(exc)
    else:
        raise AssertionError(
            f"value {value_sat} sat below estimated fee {estimated_fee} sat must raise ValueError"
        )
    print("PASS test_insufficient_value")


def test_canonical_txid() -> None:
    for value_sat in (10_000, minimum_viable_utxo_value()):
        raw_hex, _change, tx = _build(value_sat)
        txid = canonical_txid_from_raw_hex(raw_hex)
        assert isinstance(txid, str), (value_sat, txid)
        assert len(txid) == 64, (value_sat, txid)
        assert txid == txid.lower(), txid
        assert all(c in "0123456789abcdef" for c in txid), txid
        assert txid == tx.hex_hash().lower(), (value_sat, txid, tx.hex_hash())
    print("PASS test_canonical_txid")


def test_no_subviable_change() -> None:
    minimum = minimum_viable_utxo_value()
    for value_sat in range(minimum, minimum + 300):
        _raw_hex, change, tx = _build(value_sat)
        assert change == 0 or change >= minimum, (value_sat, change, minimum)
        if change == 0:
            assert len(tx.outputs) == 1, (value_sat, len(tx.outputs), change)
        else:
            assert len(tx.outputs) == 2, (value_sat, len(tx.outputs), change)
            assert int(tx.outputs[1].value) == change
            assert int(tx.outputs[1].value) >= minimum
    print("PASS test_no_subviable_change")


def test_flag_off_keeps_change() -> None:
    """Default behaviour (OMIT_DUST_CHANGE off): every coin keeps its change output."""
    import config

    assert config.OMIT_DUST_CHANGE is False or os.getenv("OMIT_DUST_CHANGE"), (
        "OMIT_DUST_CHANGE must default to off"
    )
    minimum = minimum_viable_utxo_value()
    tx_builder.OMIT_DUST_CHANGE = False
    try:
        for value_sat in range(minimum, minimum + 120):
            raw_hex, change, tx = _build(value_sat)
            assert len(tx.outputs) == 2, (value_sat, len(tx.outputs))
            assert change >= 1, (value_sat, change)
            assert int(tx.outputs[1].value) == change
            _assert_fee_covers(raw_hex, tx, value_sat - change)
    finally:
        tx_builder.OMIT_DUST_CHANGE = True
    print("PASS test_flag_off_keeps_change")


def main() -> int:
    test_flag_off_keeps_change()
    test_healthy_coin()
    test_end_of_life_coin()
    test_signatures_verify()
    test_insufficient_value()
    test_canonical_txid()
    test_no_subviable_change()
    print("all dust-change tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
