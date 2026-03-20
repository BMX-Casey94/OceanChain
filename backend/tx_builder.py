"""
OceanChain Transaction Builder Module

Constructs BSV OP_RETURN transactions containing encoded vessel position data.
Uses the bitcoinx library for transaction construction and signing.
"""

import json
import math
import struct
from typing import Any, Optional

from bitcoinx import (
    PrivateKey,
    TxInput,
    TxOutput,
    Tx,
    Script,
    P2PKH_Address,
    Bitcoin,
    SigHash,
    pack_byte,
)

from config import (
    BSV_PRIVATE_KEY_WIF,
    OP_RETURN_PREFIX,
    OP_RETURN_ENCODING,
    FEE_RATE_SAT_PER_KB,
    ESTIMATED_TX_SIZE,
    MIN_CHANGE_OUTPUT_SAT,
    MIN_TX_FEE_SAT,
    VESSEL_TX_FEE_WORST_CASE_BYTES,
)


def _encode_position_payload(position: dict[str, Any]) -> bytes:
    """
    Encode a vessel position into a 20-byte payload.
    
    Payload structure (big-endian):
        Bytes 0-3:   MMSI as uint32
        Bytes 4-7:   Latitude as int32 (degrees × 600,000, clamped)
        Bytes 8-11:  Longitude as int32 (degrees × 600,000, clamped)
        Bytes 12-13: Speed as uint16 (knots × 10, max 65535)
        Bytes 14-15: Heading as uint16 (degrees, 0xFFFF if unavailable)
        Bytes 16-19: Timestamp as uint32 (unix seconds)
    
    Args:
        position: Dict containing vessel position data
        
    Returns:
        20-byte encoded payload
    """
    # MMSI (uint32)
    mmsi = int(position.get("mmsi", 0)) & 0xFFFFFFFF
    
    # Latitude (int32, degrees × 600,000)
    # Valid range: -90 to 90 degrees
    lat = float(position.get("latitude", 0.0))
    lat = max(-90.0, min(90.0, lat))
    lat_encoded = int(lat * 600000)
    lat_encoded = max(-2147483648, min(2147483647, lat_encoded))
    
    # Longitude (int32, degrees × 600,000)
    # Valid range: -180 to 180 degrees
    lon = float(position.get("longitude", 0.0))
    lon = max(-180.0, min(180.0, lon))
    lon_encoded = int(lon * 600000)
    lon_encoded = max(-2147483648, min(2147483647, lon_encoded))
    
    # Speed (uint16, knots × 10)
    speed = float(position.get("speed", 0.0))
    speed_encoded = int(speed * 10)
    speed_encoded = max(0, min(65535, speed_encoded))
    
    # Heading (uint16, degrees or 0xFFFF if unavailable)
    heading = position.get("heading", 0xFFFF)
    if heading is None or heading == 511:
        heading_encoded = 0xFFFF
    else:
        heading_encoded = int(heading) & 0xFFFF
    
    # Timestamp (uint32, unix seconds)
    timestamp = int(position.get("timestamp", 0)) & 0xFFFFFFFF
    
    # Pack into 20 bytes (big-endian)
    payload = struct.pack(
        ">IiiHHI",
        mmsi,
        lat_encoded,
        lon_encoded,
        speed_encoded,
        heading_encoded,
        timestamp,
    )
    
    return payload


def _encode_position_json(position: dict[str, Any]) -> bytes:
    """
    UTF-8 minified JSON for the second OP_RETURN push (human-readable in block explorers).

    Same logical fields as the 20-byte binary format; larger on-chain footprint and fee.
    """
    heading = position.get("heading")
    if heading is None or heading == 511:
        heading_out: Optional[int] = None
    else:
        h = int(heading) & 0xFFFF
        heading_out = None if h == 0xFFFF else h

    obj = {
        "mmsi": int(position.get("mmsi", 0)) & 0xFFFFFFFF,
        "latitude": round(float(position.get("latitude", 0.0)), 6),
        "longitude": round(float(position.get("longitude", 0.0)), 6),
        "speed": round(float(position.get("speed", 0.0)), 2),
        "heading": heading_out,
        "timestamp": int(position.get("timestamp", 0)) & 0xFFFFFFFF,
    }
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def encode_position_for_op_return(position: dict[str, Any]) -> bytes:
    """Second push bytes: either 20-byte binary or JSON, per OP_RETURN_ENCODING."""
    if OP_RETURN_ENCODING == "json":
        return _encode_position_json(position)
    return _encode_position_payload(position)


def _build_op_return_script(payload: bytes) -> Script:
    """
    Build an OP_RETURN script with the OceanChain prefix and payload.
    
    Script format:
        OP_FALSE OP_RETURN <push OCEANCHAIN prefix> <push 20-byte payload>
    
    Args:
        payload: Encoded position (20-byte binary or UTF-8 JSON), second data push
        
    Returns:
        Script object
    """
    # OP_FALSE (0x00) + OP_RETURN (0x6a) + push prefix + push payload
    script_bytes = (
        pack_byte(0x00) +  # OP_FALSE
        pack_byte(0x6a) +  # OP_RETURN
        pack_byte(len(OP_RETURN_PREFIX)) + OP_RETURN_PREFIX +  # Push prefix
        pack_byte(len(payload)) + payload  # Push payload
    )
    
    return Script(script_bytes)


def calculate_fee(tx_size_bytes: int = ESTIMATED_TX_SIZE) -> int:
    """
    Calculate the transaction fee based on size and fee rate.
    
    Args:
        tx_size_bytes: Transaction size in bytes
        
    Returns:
        Fee in satoshis (rounded up), at least MIN_TX_FEE_SAT when set above 1
    """
    fee_sat = math.ceil((tx_size_bytes / 1000.0) * FEE_RATE_SAT_PER_KB)
    return max(fee_sat, MIN_TX_FEE_SAT)


def minimum_viable_utxo_value() -> int:
    """
    Minimum input value required to create a standard tx that still leaves
    a change output above the dust threshold.

    Uses a worst-case serialized size so pool UTXOs are not selected when the
    real signed tx (larger than a lowball estimate) would need a higher fee.
    """
    return calculate_fee(VESSEL_TX_FEE_WORST_CASE_BYTES) + MIN_CHANGE_OUTPUT_SAT


def build_op_return_tx(
    utxo: dict[str, Any],
    position: dict[str, Any],
    change_address: str,
) -> tuple[str, int]:
    """
    Build a complete OP_RETURN transaction for a vessel position.
    
    Transaction structure:
        Input:  1 input spending the provided UTXO
        Output 0: OP_RETURN script (0 satoshis)
        Output 1: P2PKH change output
    
    Args:
        utxo: Dict with keys: txid, vout, value_sat
        position: Dict with vessel position data
        change_address: BSV address for change output
        
    Returns:
        Tuple of (raw_tx_hex, change_value_sat)
    """
    # Get private key from config
    private_key = PrivateKey.from_WIF(BSV_PRIVATE_KEY_WIF)
    public_key = private_key.public_key
    
    # Parse UTXO data
    prev_txid = bytes.fromhex(utxo["txid"])[::-1]  # Reverse for little-endian
    prev_vout = int(utxo["vout"])
    input_value = int(utxo["value_sat"])
    
    # Fee: start from an estimate, then align to the signed serialized size at FEE_RATE_SAT_PER_KB.
    # If the estimate was below the true size, we were under-paying; this fixes that without
    # raising your configured sat/kB rate.
    fee = calculate_fee(ESTIMATED_TX_SIZE)
    payload = encode_position_for_op_return(position)
    op_return_script = _build_op_return_script(payload)
    change_addr = P2PKH_Address.from_string(change_address, Bitcoin)
    change_script = change_addr.to_script()
    prev_output_script = public_key.P2PKH_script()
    sighash_type = SigHash(0x41)  # SIGHASH_ALL | SIGHASH_FORKID (BSV)

    for _ in range(6):
        change_value = input_value - fee
        if change_value < MIN_CHANGE_OUTPUT_SAT:
            minimum_value = minimum_viable_utxo_value()
            raise ValueError(
                f"Insufficient UTXO value: {input_value} sat, "
                f"minimum viable value is {minimum_value} sat"
            )

        op_return_output = TxOutput(0, op_return_script)
        change_output = TxOutput(change_value, change_script)
        tx_input = TxInput(prev_txid, prev_vout, Script(), 0xFFFFFFFF)

        tx = Tx(
            version=1,
            inputs=[tx_input],
            outputs=[op_return_output, change_output],
            locktime=0,
        )

        sig_hash = tx.signature_hash(
            input_index=0,
            value=input_value,
            script_code=prev_output_script,
            sighash=sighash_type,
        )
        signature = private_key.sign(sig_hash, hasher=None)
        signature_bytes = signature + pack_byte(0x41)

        pub_key_bytes = public_key.to_bytes()
        script_sig = (
            pack_byte(len(signature_bytes)) + signature_bytes +
            pack_byte(len(pub_key_bytes)) + pub_key_bytes
        )
        tx.inputs[0].script_sig = Script(script_sig)

        actual_bytes = len(tx.to_bytes())
        required_fee = calculate_fee(actual_bytes)
        if fee >= required_fee:
            return (tx.to_bytes().hex(), change_value)
        fee = required_fee

    raise RuntimeError(
        "Could not converge on a fee for OP_RETURN tx after several iterations; "
        "check FEE_RATE_SAT_PER_KB / MIN_TX_FEE_SAT and UTXO_VALUE_EACH."
    )


def get_change_address() -> str:
    """
    Get the change address derived from the configured private key.
    
    Returns:
        BSV address string (P2PKH)
    """
    private_key = PrivateKey.from_WIF(BSV_PRIVATE_KEY_WIF)
    address = private_key.public_key.to_address(network=Bitcoin)
    return address.to_string()


def decode_position_payload(payload: bytes) -> dict[str, Any]:
    """
    Decode a 20-byte position payload back to readable values.
    For JSON on-chain payloads, use decode_op_return_payload instead.
    """
    if len(payload) != 20:
        raise ValueError(f"Expected 20 bytes, got {len(payload)}")

    mmsi, lat_enc, lon_enc, speed_enc, heading_enc, timestamp = struct.unpack(
        ">IiiHHI", payload
    )

    return {
        "mmsi": str(mmsi),
        "latitude": lat_enc / 600000.0,
        "longitude": lon_enc / 600000.0,
        "speed": speed_enc / 10.0,
        "heading": None if heading_enc == 0xFFFF else heading_enc,
        "timestamp": timestamp,
    }


def decode_op_return_payload(payload: bytes) -> dict[str, Any]:
    """
    Decode the second OP_RETURN data push (binary or JSON) to the same shape as decode_position_payload.
    """
    if len(payload) == 0:
        raise ValueError("Empty OP_RETURN payload")

    if payload[:1] == b"{":
        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON in OP_RETURN payload: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("OP_RETURN JSON must be an object")
        mmsi = data.get("mmsi", 0)
        ts = int(data.get("timestamp", 0)) & 0xFFFFFFFF
        lat = float(data.get("latitude", 0.0))
        lon = float(data.get("longitude", 0.0))
        spd = float(data.get("speed", 0.0))
        hdg = data.get("heading")
        if hdg is None:
            heading_out = None
        else:
            heading_out = int(hdg) & 0xFFFF
            if heading_out == 0xFFFF:
                heading_out = None
        return {
            "mmsi": str(int(mmsi) & 0xFFFFFFFF),
            "latitude": lat,
            "longitude": lon,
            "speed": spd,
            "heading": heading_out,
            "timestamp": ts,
        }

    return decode_position_payload(payload)
