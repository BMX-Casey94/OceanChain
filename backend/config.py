"""
Ocechain Configuration Module

Loads all configuration values from environment variables using python-dotenv.
Exposes module-level constants for use throughout the application.

Note: on-chain OP_RETURN prefix is Ocechain (brand-aligned).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
# override=True: values in backend/.env win over stale/empty shell exports (e.g. BSV_NETWORK).
load_dotenv(dotenv_path=env_path, override=True)

# AISstream Configuration
AISSTREAM_API_KEY: str = os.getenv("AISSTREAM_API_KEY", "")
AISSTREAM_WS_URL: str = "wss://stream.aisstream.io/v0/stream"

# Message types we can parse into the vessel snapshot (Phase 1 position-class). See docs/AIS_MESSAGE_EXPANSION_PLAN.md.
SUPPORTED_AIS_POSITION_MESSAGE_TYPES: frozenset[str] = frozenset(
    {
        "PositionReport",
        "StandardClassBPositionReport",
        "ExtendedClassBPositionReport",
        "LongRangeAisBroadcastMessage",
    }
)
# Static/voyage data — type, name, IMO, destination. Merged onto existing positions only.
SUPPORTED_AIS_STATIC_MESSAGE_TYPES: frozenset[str] = frozenset(
    {
        "ShipStaticData",
        "StaticDataReport",
    }
)
SUPPORTED_AIS_FILTER_MESSAGE_TYPES: frozenset[str] = (
    SUPPORTED_AIS_POSITION_MESSAGE_TYPES | SUPPORTED_AIS_STATIC_MESSAGE_TYPES
)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _parse_aisstream_filter_message_types(raw: str) -> list[str]:
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    if not parts:
        return ["PositionReport"]
    return _dedupe_preserve_order(parts)


AISSTREAM_FILTER_MESSAGE_TYPES: list[str] = _parse_aisstream_filter_message_types(
    os.getenv(
        "AISSTREAM_FILTER_MESSAGE_TYPES",
        "PositionReport,ShipStaticData",
    ).strip()
)

# BSV Wallet Configuration
BSV_PRIVATE_KEY_WIF: str = os.getenv("BSV_PRIVATE_KEY_WIF", "")
BSV_NETWORK: str = os.getenv("BSV_NETWORK", "main")

# ARC Broadcaster Configuration
TAAL_API_KEY: str = os.getenv("TAAL_API_KEY", "")
# GorillaPool Arcade (ARC-compatible); higher-throughput path vs legacy arc.gorillapool.io/v1/tx.
# Override with GORILLA_ARC_URL if needed (e.g. rollback).
GORILLA_ARC_URL: str = os.getenv("GORILLA_ARC_URL", "https://arcade.gorillapool.io/tx")
# Gorilla payload format sent in `rawTx` for GorillaPool submissions.
# `raw` = standard tx hex, `ef` = BIP-239 Transaction Extended Format, `auto` = EF when available, else raw.
GORILLA_TX_FORMAT: str = os.getenv("GORILLA_TX_FORMAT", "raw").strip().lower()
TAAL_ARC_URL: str = "https://arc.taal.com/v1/tx"
WHATSONCHAIN_BASE_URL: str = "https://api.whatsonchain.com/v1/bsv"

# Database Configuration
DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/oceanchain")

# UTXO Pool Configuration
# Each vessel tx spends one pool UTXO; fee is only tens–low hundreds of sats at typical sizes/rates.
# Smaller UTXO_VALUE_EACH + higher UTXO_POOL_TARGET = less capital locked, more rows (fan-out needs
# one wallet input covering TARGET × VALUE_EACH + fan-out fee).
UTXO_POOL_TARGET: int = int(os.getenv("UTXO_POOL_TARGET", "800"))
UTXO_VALUE_EACH: int = int(os.getenv("UTXO_VALUE_EACH", "3000"))
MIN_CHANGE_OUTPUT_SAT: int = int(os.getenv("MIN_CHANGE_OUTPUT_SAT", "1"))
# If true, run one fan-out from the funded wallet when the pool is empty at startup.
UTXO_AUTO_REFILL_ON_START: bool = os.getenv("UTXO_AUTO_REFILL_ON_START", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# After a failed automatic fan-out, skip retry for this many seconds (reduces log spam when
# wallet cannot yet afford UTXO_POOL_TARGET × UTXO_VALUE_EACH). Set 0 to retry every monitor tick.
REFILL_FAILURE_COOLDOWN_SECONDS: int = int(os.getenv("REFILL_FAILURE_COOLDOWN_SECONDS", "900"))
# Safety cap for a single fan-out refill. Very large multi-input refills are expensive,
# slow to validate, and currently correlate with poor propagation / validator failures.
# Set 0 to disable the cap.
FANOUT_MAX_INPUTS: int = int(os.getenv("FANOUT_MAX_INPUTS", "512"))
# When > 0, WhatsOnChain sync and admin bulk reserve import skip UTXOs below this value (reduces dust rows).
RESERVE_MIN_IMPORT_SAT: int = int(os.getenv("RESERVE_MIN_IMPORT_SAT", "0"))

# Database pool sizing — controls how many Postgres backend processes run concurrently.
# At high BROADCAST_CONCURRENCY every pool slot runs constant UPDATE/DELETE/INSERT cycles;
# 20 slots on a 4-core VPS can saturate CPU.  3-5 is typically plenty for UTXO operations.
DB_POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN_SIZE", "2"))
DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", "5"))

# Broadcasting Configuration
BATCH_INTERVAL_SECONDS: int = int(os.getenv("BATCH_INTERVAL_SECONDS", "10"))
# Max concurrent vessel broadcasts (ARC + DB per task). Tune via env if ARC/Postgres show strain.
BROADCAST_CONCURRENCY: int = int(os.getenv("BROADCAST_CONCURRENCY", "450"))
# App-side ARC target status. The broadcaster submits first, then polls GET /tx/{txid}
# until this lifecycle state is reached before counting the tx as successful.
ARC_WAIT_FOR_STATUS: str = os.getenv("ARC_WAIT_FOR_STATUS", "SEEN_ON_NETWORK").strip().upper()
# Maximum seconds to wait for ARC status polling before retry/failover.
ARC_MAX_TIMEOUT_SECONDS: int = int(os.getenv("ARC_MAX_TIMEOUT_SECONDS", "10"))
# Periodic INFO log: successes/failures/samples (seconds). Set 0 to disable the summary task.
LOG_SUMMARY_INTERVAL_SECONDS: int = int(os.getenv("LOG_SUMMARY_INTERVAL_SECONDS", "120"))
# Per-HTTP-request ARC logs at INFO when true; otherwise DEBUG only (summary still INFO).
VERBOSE_ARC_LOGS: bool = os.getenv("VERBOSE_ARC_LOGS", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# Uvicorn HTTP access log (one line per API request); usually off for VPS noise.
UVICORN_ACCESS_LOG: bool = os.getenv("UVICORN_ACCESS_LOG", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Server Configuration
VPS_API_PORT: int = int(os.getenv("VPS_API_PORT", "8000"))

# Public API / CORS (comma-separated origins for the Ocechain frontend)
CORS_ALLOW_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:3000,https://ocechain.com,https://www.ocechain.com",
    ).split(",")
    if o.strip()
]
# Light rate limit for public vessel search (requests per IP per window)
VESSEL_SEARCH_RATE_LIMIT: int = int(os.getenv("VESSEL_SEARCH_RATE_LIMIT", "60"))
VESSEL_SEARCH_RATE_WINDOW_SECONDS: int = int(
    os.getenv("VESSEL_SEARCH_RATE_WINDOW_SECONDS", "60")
)
VESSELS_LIST_DEFAULT_LIMIT: int = int(os.getenv("VESSELS_LIST_DEFAULT_LIMIT", "8000"))
# Hard cap for GET /vessels limit= (full fleet snapshots can exceed 60k).
VESSELS_LIST_MAX_LIMIT: int = int(os.getenv("VESSELS_LIST_MAX_LIMIT", "100000"))

# In-memory trail for route tracker: last N broadcast positions per MMSI (process-local).
VESSEL_TRAIL_MAX_POINTS: int = int(os.getenv("VESSEL_TRAIL_MAX_POINTS", "200"))

# Optional: on first successful vessel broadcast after startup, write raw tx hex to this path
# (ASCII, one line) for offline checks: POST https://api.whatsonchain.com/v1/bsv/main/tx/decode
# with JSON {"txhex":"..."}. See scripts/woc_decode_sample.sh
LOG_SAMPLE_RAW_TX_PATH: str = os.getenv("LOG_SAMPLE_RAW_TX_PATH", "").strip()

# Optional: protects POST /utxo/sync-reserves-woc (bulk import of unspents from WhatsOnChain).
# Generate a long random string; send header X-OceanChain-Admin-Key: <value>.
OCEANCHAIN_ADMIN_API_KEY: str = os.getenv("OCEANCHAIN_ADMIN_API_KEY", "").strip()

# Transaction Constants
OP_RETURN_PREFIX: bytes = b"Ocechain"
# Second push after prefix: compact 20-byte binary (default), or UTF-8 minified JSON for human-readable explorers.
OP_RETURN_ENCODING: str = os.getenv("OP_RETURN_ENCODING", "binary").strip().lower()
# Fee rate: satoshis per 1000 bytes of the *serialized* transaction (standard BSV quoting).
FEE_RATE_SAT_PER_KB: float = float(os.getenv("FEE_RATE_SAT_PER_KB", "102.5"))
# Optional floor (satoshis per tx) applied after the sat/kB calculation. Default 1 keeps the
# effective rate at your configured FEE_RATE only; raising this increases effective sat/kB on small txs.
MIN_TX_FEE_SAT: int = int(os.getenv("MIN_TX_FEE_SAT", "1"))

# First guess for vessel OP_RETURN fee iteration (tx_builder measures the signed tx and converges).
ESTIMATED_TX_SIZE: int = int(os.getenv("ESTIMATED_TX_SIZE", "220"))

# When selecting pool UTXOs, require enough value for fee at this serialized-size ceiling (≥ realistic tx).
VESSEL_TX_FEE_WORST_CASE_BYTES: int = int(os.getenv("VESSEL_TX_FEE_WORST_CASE_BYTES", "320"))


def validate_config() -> list[str]:
    """
    Validate that all required configuration values are set.
    Returns a list of missing/invalid configuration keys.
    """
    errors: list[str] = []
    
    if not AISSTREAM_API_KEY:
        errors.append("AISSTREAM_API_KEY is required")
    
    if not BSV_PRIVATE_KEY_WIF:
        errors.append("BSV_PRIVATE_KEY_WIF is required")
    
    if not DATABASE_URL or DATABASE_URL == "postgresql://user:pass@localhost/oceanchain":
        errors.append("DATABASE_URL should be configured with actual credentials")
    
    if BSV_NETWORK not in {"main", "test"}:
        errors.append("BSV_NETWORK must be 'main' or 'test'")

    if OP_RETURN_ENCODING not in {"binary", "json"}:
        errors.append("OP_RETURN_ENCODING must be 'binary' or 'json'")

    if LOG_SUMMARY_INTERVAL_SECONDS < 0:
        errors.append("LOG_SUMMARY_INTERVAL_SECONDS must be >= 0")
    elif 0 < LOG_SUMMARY_INTERVAL_SECONDS < 10:
        errors.append("LOG_SUMMARY_INTERVAL_SECONDS must be 0 or >= 10")

    if UTXO_POOL_TARGET < 1:
        errors.append("UTXO_POOL_TARGET must be >= 1")
    if UTXO_VALUE_EACH < 60:
        errors.append(
            "UTXO_VALUE_EACH must be >= 60 sat (worst-case fee ~34 sat + dust margin)"
        )

    if REFILL_FAILURE_COOLDOWN_SECONDS < 0:
        errors.append("REFILL_FAILURE_COOLDOWN_SECONDS must be >= 0")

    if FANOUT_MAX_INPUTS < 0:
        errors.append("FANOUT_MAX_INPUTS must be >= 0")

    if RESERVE_MIN_IMPORT_SAT < 0:
        errors.append("RESERVE_MIN_IMPORT_SAT must be >= 0")

    if DB_POOL_MIN_SIZE < 1:
        errors.append("DB_POOL_MIN_SIZE must be >= 1")
    if DB_POOL_MAX_SIZE < DB_POOL_MIN_SIZE:
        errors.append("DB_POOL_MAX_SIZE must be >= DB_POOL_MIN_SIZE")
    if DB_POOL_MAX_SIZE > 50:
        errors.append("DB_POOL_MAX_SIZE must be <= 50")

    if BROADCAST_CONCURRENCY < 1:
        errors.append("BROADCAST_CONCURRENCY must be >= 1")
    elif BROADCAST_CONCURRENCY > 512:
        errors.append("BROADCAST_CONCURRENCY must be <= 512")

    allowed_arc_wait = {
        "UNKNOWN",
        "QUEUED",
        "RECEIVED",
        "STORED",
        "ANNOUNCED_TO_NETWORK",
        "REQUESTED_BY_NETWORK",
        "SENT_TO_NETWORK",
        "ACCEPTED_BY_NETWORK",
        "SEEN_ON_NETWORK",
        "SEEN_IN_ORPHAN_MEMPOOL",
        "MINED",
        "CONFIRMED",
        "IMMUTABLE",
    }
    if ARC_WAIT_FOR_STATUS not in allowed_arc_wait:
        errors.append(
            "ARC_WAIT_FOR_STATUS must be one of: "
            + ", ".join(sorted(allowed_arc_wait))
        )
    if ARC_MAX_TIMEOUT_SECONDS < 1:
        errors.append("ARC_MAX_TIMEOUT_SECONDS must be >= 1")
    elif ARC_MAX_TIMEOUT_SECONDS > 30:
        errors.append("ARC_MAX_TIMEOUT_SECONDS must be <= 30")

    if GORILLA_TX_FORMAT not in {"raw", "ef", "auto"}:
        errors.append("GORILLA_TX_FORMAT must be one of: raw, ef, auto")

    for mt in AISSTREAM_FILTER_MESSAGE_TYPES:
        if mt not in SUPPORTED_AIS_FILTER_MESSAGE_TYPES:
            errors.append(
                f"AISSTREAM_FILTER_MESSAGE_TYPES: unsupported type {mt!r} "
                f"(supported: {', '.join(sorted(SUPPORTED_AIS_FILTER_MESSAGE_TYPES))})"
            )

    return errors


def get_config_summary() -> dict:
    """
    Return a summary of the current configuration (with sensitive values masked).
    """
    return {
        "aisstream_api_key": "***" if AISSTREAM_API_KEY else "(not set)",
        "aisstream_filter_message_types": list(AISSTREAM_FILTER_MESSAGE_TYPES),
        "bsv_private_key_wif": "***" if BSV_PRIVATE_KEY_WIF else "(not set)",
        "bsv_network": BSV_NETWORK,
        "taal_api_key": "***" if TAAL_API_KEY else "(not set)",
        "gorilla_arc_url": GORILLA_ARC_URL,
        "gorilla_tx_format": GORILLA_TX_FORMAT,
        "database_url": DATABASE_URL[:30] + "..." if len(DATABASE_URL) > 30 else DATABASE_URL,
        "utxo_pool_target": UTXO_POOL_TARGET,
        "utxo_value_each": UTXO_VALUE_EACH,
        "utxo_auto_refill_on_start": UTXO_AUTO_REFILL_ON_START,
        "refill_failure_cooldown_seconds": REFILL_FAILURE_COOLDOWN_SECONDS,
        "fanout_max_inputs": FANOUT_MAX_INPUTS,
        "min_change_output_sat": MIN_CHANGE_OUTPUT_SAT,
        "db_pool_min_size": DB_POOL_MIN_SIZE,
        "db_pool_max_size": DB_POOL_MAX_SIZE,
        "batch_interval_seconds": BATCH_INTERVAL_SECONDS,
        "broadcast_concurrency": BROADCAST_CONCURRENCY,
        "arc_wait_for_status": ARC_WAIT_FOR_STATUS,
        "arc_max_timeout_seconds": ARC_MAX_TIMEOUT_SECONDS,
        "vps_api_port": VPS_API_PORT,
        "fee_rate_sat_per_kb": FEE_RATE_SAT_PER_KB,
        "min_tx_fee_sat": MIN_TX_FEE_SAT,
        "vessel_tx_fee_worst_case_bytes": VESSEL_TX_FEE_WORST_CASE_BYTES,
        "op_return_encoding": OP_RETURN_ENCODING,
        "log_summary_interval_seconds": LOG_SUMMARY_INTERVAL_SECONDS,
        "verbose_arc_logs": VERBOSE_ARC_LOGS,
        "uvicorn_access_log": UVICORN_ACCESS_LOG,
        "admin_api_key_configured": bool(OCEANCHAIN_ADMIN_API_KEY),
        "reserve_min_import_sat": RESERVE_MIN_IMPORT_SAT,
        "log_sample_raw_tx_configured": bool(LOG_SAMPLE_RAW_TX_PATH),
    }
