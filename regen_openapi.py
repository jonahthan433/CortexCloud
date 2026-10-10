#!/usr/bin/env python3
"""Regenerate openapi.json from the live app.

mppscan/x402scan discovery gate: every payable operation must carry
x-payment-info (price + protocols incl. mpp) + a 402 response, free routes
need security: [], and info.contact.email verifies ownership. Single source
of prices = app.x402.pricing.ROUTE_PRICING (server-side dynamic pricing may
differ; mppscan requires static, so endpoints that reprice per request are
registered with their dynamic bounds).

Run on CT105 (has the venv):
  cd /opt/CortexCloudAPI && /opt/cortexcloud-venv/bin/python regen_openapi.py
"""
import json
import sys

sys.path.insert(0, "/opt/CortexCloudAPI")

from app.main import create_app
from app.x402.pricing import ROUTE_PRICING


def _usd(route_key: str) -> float:
    try:
        return float(ROUTE_PRICING.get(route_key, "$0.004").lstrip("$"))
    except ValueError:
        return 0.004


def _payment_info(path: str, method: str) -> dict:
    fixed = _usd(f"{method.upper()} {path}")
    return {
        "x-payment-info": {
            "price": {"mode": "fixed", "currency": "USD", "amount": str(fixed)},
            # Runtime settles x402 only; declare x402 truthfully. Add the mpp
            # object back (with non-empty method/intent/currency) only once
            # MPP/Tempo settlement is actually live, or discovery flags it malformed.
            "protocols": [{"x402": {}}],
        }
    }


app = create_app(override_openapi=False)
spec = app.openapi()
spec["paths"] = {k: v for k, v in spec["paths"].items() if not k.startswith("/internal")}

spec.setdefault("info", {})["contact"] = {"email": "jonathan@cortexcloud.org"}
spec["info"]["x-guidance"] = (
    "Pay-per-call API for AI agents. Free: POST /v1/estimate, GET /v1/backends, "
    "GET /v1/capabilities, GET /v1/examples, POST /v1/simulate, POST /v1/ml/estimate. "
    "Paid (USDC on Base via x402, price in x-payment-info): POST /v1/optimize, "
    "/v1/ai/*, /v1/research/*, /v1/data/*, /v1/ml/*. Call any paid route without a "
    "payment-signature header to receive a 402 challenge with the exact amount; "
    "settle via x402 (EIP-3009 USDC on Base) or MPP and retry with the header."
)

for path, ops in spec["paths"].items():
    for method, op in ops.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        op.setdefault("responses", {}).setdefault(
            "402", {"description": "Payment Required — x402/MPP challenge returned with the exact price"}
        )
        key = f"{method.upper()} {path}"
        if key in ROUTE_PRICING or (path.startswith("/x402/v1/") and path != "/x402/v1/pubkey"):
            op.update(_payment_info(path, method))
        else:
            op.setdefault("security", [])

with open("/opt/CortexCloudAPI/openapi.json", "w") as f:
    json.dump(spec, f, indent=2)

paid = sum(
    1
    for p, ops in spec["paths"].items()
    for m, op in ops.items()
    if m in ("get", "post", "put", "patch", "delete") and "x-payment-info" in op
)
print(f"openapi.json regenerated: {len(spec['paths'])} paths, {paid} payable ops with x-payment-info")
