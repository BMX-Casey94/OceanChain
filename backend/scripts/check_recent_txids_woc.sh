#!/usr/bin/env bash
# Check the last N vessel broadcast txids against WhatsOnChain (BSV main).
#
# Txids are read from Postgres: each successful vessel tx records change at pool vout=1.
# WOC is capped ~3 RPS — default pause 0.35s between requests (~2.8 RPS).
#
# Usage (from /opt/OceanChain/backend):
#   chmod +x scripts/check_recent_txids_woc.sh
#   ./scripts/check_recent_txids_woc.sh          # default N=10
#   ./scripts/check_recent_txids_woc.sh 5
#
# Env:
#   DATABASE_URL     — required (or load from .env in backend/)
#   BSV_NETWORK      — main (default) or test → WOC path
#   WOC_SLEEP_SEC    — override pause between calls (default 0.35)

set -euo pipefail

N="${1:-10}"
if ! [[ "$N" =~ ^[0-9]+$ ]] || [[ "$N" -lt 1 ]] || [[ "$N" -gt 500 ]]; then
  echo "usage: $0 [N]   with 1 <= N <= 500" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "error: DATABASE_URL not set (export it or add to backend/.env)" >&2
  exit 1
fi

NET="${BSV_NETWORK:-main}"
if [[ "$NET" == "test" ]]; then
  WOC_SEGMENT="test"
else
  WOC_SEGMENT="main"
fi

SLEEP_SEC="${WOC_SLEEP_SEC:-0.35}"

list_file="$(mktemp)"
body_file="$(mktemp)"
trap 'rm -f "$list_file" "$body_file"' EXIT

psql "$DATABASE_URL" -Atq -v ON_ERROR_STOP=1 -c "
SELECT txid FROM utxos
WHERE utxo_role = 'pool' AND vout = 1
ORDER BY created_at DESC
LIMIT $N;
" >"$list_file"

if [[ ! -s "$list_file" ]]; then
  echo "No rows: pool vout=1 (no recent vessel change outputs in DB yet)." >&2
  exit 1
fi

echo "# WOC segment: bsv/$WOC_SEGMENT  sleep: ${SLEEP_SEC}s between calls"
while IFS= read -r txid || [[ -n "$txid" ]]; do
  [[ -z "$txid" ]] && continue
  url="https://api.whatsonchain.com/v1/bsv/${WOC_SEGMENT}/tx/hash/${txid}"
  code="$(curl -sS -o "$body_file" -w "%{http_code}" "$url")"
  if [[ "$code" == "200" ]]; then
    echo "OK   $txid"
  else
    body="$(head -c 240 "$body_file" | tr '\n' ' ' || true)"
    echo "FAIL $txid  HTTP_${code}  $body"
  fi
  sleep "$SLEEP_SEC"
done <"$list_file"
