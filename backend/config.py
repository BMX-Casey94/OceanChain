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
UTXO_POOL_TARGET: int = int(os.getenv("UTXO_POOL_TARGET", "500"))
UTXO_VALUE_EACH: int = int(os.getenv("UTXO_VALUE_EACH", "10000"))
MIN_CHANGE_OUTPUT_SAT: int = int(os.getenv("MIN_CHANGE_OUTPUT_SAT", "1"))
# If true, run one fan-out from the funded wallet when the pool is empty at startup.
UTXO_AUTO_REFILL_ON_START: bool = os.getenv("UTXO_AUTO_REFILL_ON_START", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Broadcasting Configuration
BATCH_INTERVAL_SECONDS: int = int(os.getenv("BATCH_INTERVAL_SECONDS", "10"))

# Server Configuration
VPS_API_PORT: int = int(os.getenv("VPS_API_PORT", "8000"))

# Transaction Constants
OP_RETURN_PREFIX: bytes = b"OCEANCHAIN"
FEE_RATE_SAT_PER_KB: float = 102.5

# Estimated transaction size in bytes (for fee calculation)
ESTIMATED_TX_SIZE: int = 220


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
        "min_change_output_sat": MIN_CHANGE_OUTPUT_SAT,
        "batch_interval_seconds": BATCH_INTERVAL_SECONDS,
        "vps_api_port": VPS_API_PORT,
        "fee_rate_sat_per_kb": FEE_RATE_SAT_PER_KB,
    }
