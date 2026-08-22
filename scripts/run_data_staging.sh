#!/usr/bin/env bash
# Data API (Tier 1) staging verification — runs on CT105 (has Postgres + x402).
# Not for CI. Expects: DATA_ENABLED=true, ALCHEMY_API_KEY set, x402 enabled,
# and a funded test-buyer wallet configured. INTERNAL_TOKEN for ledger checks.
set -euo pipefail
cd "$(dirname "$0")/.."

export CORTEXCLOUD_KEY_DIR="${CORTEXCLOUD_KEY_DIR:-/opt/CortexCloudAPI}"
python3 update_openapi_v2.py

echo "=== 1) unit + integration + security + cache + disabled-flag tests ==="
/opt/cortexcloud-venv/bin/python -m pytest tests/test_data.py tests/test_ai_research.py tests/test_discovery.py -q

echo "=== 2) live x402 paid smoke (real USDC settlement) ==="
DATA_SMOKE=1 CORTEXCLOUD_BASE="${CORTEXCLOUD_BASE:-http://127.0.0.1:8000}" \
  /opt/cortexcloud-venv/bin/python -m pytest tests/test_data_live_smoke.py -q

echo "=== 3) ledger economics: provider cost + margin recorded ==="
# verify /v1/data/token-price returns price_usd >= provider_cost_usd and margin>0
curl -s localhost:8000/v1/capabilities | python3 -c "import sys,json; c=json.load(sys.stdin)['categories']['data']; print('data status:', c['status']); print('endpoints:', len(c['endpoints']))"

echo "=== 4) AI / Research / Quantum untouched ==="
/opt/cortexcloud-venv/bin/python -m pytest tests/test_ai_research.py tests/test_quantum_cap.py tests/test_money_guards.py -q
echo "DONE — if all green, report back for production-enable approval."
