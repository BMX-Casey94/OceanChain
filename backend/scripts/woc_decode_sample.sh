#!/usr/bin/env bash
# POST one raw vessel tx hex to WhatsOnChain /tx/decode and print the JSON (includes "txid").
#
# Produces the txid WOC's node derives from your bytes. Compare to Postgres and to GET /tx/…
# (GET often returns 404 for txs WOC does not index even when decode succeeds.)
#
# Prerequisite: set LOG_SAMPLE_RAW_TX_PATH in .env (e.g. /tmp/oceanchain_sample_tx.hex),
# restart oceanchain, wait for one successful broadcast — the engine writes the file once.
#
# Usage (from backend/, after sourcing .env if you use BSV_NETWORK=test):
#   bash scripts/woc_decode_sample.sh
#   bash scripts/woc_decode_sample.sh /path/to/sample.hex

set -euo pipefail

FILE="${1:-/tmp/oceanchain_sample_tx.hex}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$BACKEND_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$BACKEND_DIR/.env"
  set +a
fi

NET="${BSV_NETWORK:-main}"
if [[ ! -f "$FILE" ]]; then
  echo "Missing file: $FILE" >&2
  echo "Set LOG_SAMPLE_RAW_TX_PATH=$FILE in backend/.env, restart oceanchain, wait for one OK broadcast." >&2
  exit 1
fi

PAYLOAD="$(python3 -c "
import json, sys
path = sys.argv[1]
with open(path, encoding='ascii') as f:
    h = ''.join(f.read().split())
print(json.dumps({'txhex': h}))
" "$FILE")"

RESP="$(curl -sS -X POST "https://api.whatsonchain.com/v1/bsv/${NET}/tx/decode" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")"
echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"

echo ""
echo "# If \"txid\" matches your DB but GET /tx/{txid} is 404, WOC is not serving that tx via lookup (indexing/policy)."
