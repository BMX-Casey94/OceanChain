"""
OceanChain Configuration Module

Loads all configuration values from environment variables using python-dotenv.
Exposes module-level constants for use throughout the application.
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

# BSV Wallet Configuration
BSV_PRIVATE_KEY_WIF: str = os.getenv("BSV_PRIVATE_KEY_WIF", "")
BSV_NETWORK: str = os.getenv("BSV_NETWORK", "main")

# ARC Broadcaster Configuration
TAAL_API_KEY: str = os.getenv("TAAL_API_KEY", "")
GORILLA_ARC_URL: str = "https://arc.gorillapool.io/v1/tx"
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

# Broadcasting Configuration
BATCH_INTERVAL_SECONDS: int = int(os.getenv("BATCH_INTERVAL_SECONDS", "10"))
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

# Transaction Constants
OP_RETURN_PREFIX: bytes = b"OCEANCHAIN"
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
    if UTXO_VALUE_EACH < 500:
        errors.append(
            "UTXO_VALUE_EACH should be >= 500 sat (needs to cover fee + min change; "
            "use 2000–5000+ for JSON OP_RETURN / headroom)"
        )

    if REFILL_FAILURE_COOLDOWN_SECONDS < 0:
        errors.append("REFILL_FAILURE_COOLDOWN_SECONDS must be >= 0")

    return errors


def get_config_summary() -> dict:
    """
    Return a summary of the current configuration (with sensitive values masked).
    """
    return {
        "aisstream_api_key": "***" if AISSTREAM_API_KEY else "(not set)",
        "bsv_private_key_wif": "***" if BSV_PRIVATE_KEY_WIF else "(not set)",
        "bsv_network": BSV_NETWORK,
        "taal_api_key": "***" if TAAL_API_KEY else "(not set)",
        "database_url": DATABASE_URL[:30] + "..." if len(DATABASE_URL) > 30 else DATABASE_URL,
        "utxo_pool_target": UTXO_POOL_TARGET,
        "utxo_value_each": UTXO_VALUE_EACH,
        "utxo_auto_refill_on_start": UTXO_AUTO_REFILL_ON_START,
        "refill_failure_cooldown_seconds": REFILL_FAILURE_COOLDOWN_SECONDS,
        "min_change_output_sat": MIN_CHANGE_OUTPUT_SAT,
        "batch_interval_seconds": BATCH_INTERVAL_SECONDS,
        "vps_api_port": VPS_API_PORT,
        "fee_rate_sat_per_kb": FEE_RATE_SAT_PER_KB,
        "min_tx_fee_sat": MIN_TX_FEE_SAT,
        "vessel_tx_fee_worst_case_bytes": VESSEL_TX_FEE_WORST_CASE_BYTES,
        "op_return_encoding": OP_RETURN_ENCODING,
        "log_summary_interval_seconds": LOG_SUMMARY_INTERVAL_SECONDS,
        "verbose_arc_logs": VERBOSE_ARC_LOGS,
        "uvicorn_access_log": UVICORN_ACCESS_LOG,
    }
