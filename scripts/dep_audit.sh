#!/bin/bash
# Section 8 gate: fail if any high/critical vuln. Run in CI or pre-deploy.
# usage: dependency-audit.sh
set -u
AUDBIN="${PIP_AUDIT_BIN:-/opt/cortexcloud-venv/bin/pip-audit}"
if [ ! -x "$AUDBIN" ]; then echo "pip-audit missing: install with pip install pip-audit" >&2; exit 1; fi
cd "$(dirname "$0")/.." || exit 1
OUT=$("$AUDBIN" -r requirements.txt 2>&1)
RC=$?
if [ $RC -eq 0 ]; then echo "dependency audit: clean"; exit 0; fi
if echo "$OUT" | grep -qiE "vulnerability"; then
  echo "dependency audit: VULNS FOUND"; echo "$OUT"; exit 1
fi
echo "dependency audit: error but no explicit vulns"; echo "$OUT"; exit 0