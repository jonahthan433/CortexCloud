#!/usr/bin/env python3
"""Regenerate openapi.json from the live app, preserving the curated discovery bits.

Unlike update_openapi_v2.py (stale positioning text, ai-ml category), this keeps
the manual fields that were added for discovery:
  - info.x-guidance, info.contact, info.x-apisguru-categories
  - root x-agentcash-provenance.ownershipProofs

Every paid operation is re-priced from app.x402.pricing.ROUTE_PRICING (single
source), so a price change cannot drift. Run from the repo root on CT105:
    cd /opt/ccapi-test && /opt/cortexcloud-venv/bin/python regen_discovery_openapi.py
"""
import json
import os

from app.core.config import settings
from app.main import create_app
from app.middleware.x402 import INPUT_SCHEMAS, TEMPO_USDC
from app.x402.pricing import ROUTE_PRICING

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "openapi.json")

with open(BASE) as fh:
    curated = json.load(fh)

spec = create_app(override_openapi=False).openapi()
# Not part of the advertised product surface: /v1/track is the landing-page
# GTM beacon (anonymous 204, no capability), /internal is operator plumbing.
_PRIVATE = ("/internal", "/v1/track")
spec["paths"] = {
    k: v for k, v in spec["paths"].items() if not k.startswith(_PRIVATE)
}

# Curated discovery metadata must survive a regeneration.
info = spec.setdefault("info", {})
for key in ("x-guidance", "x-apisguru-categories", "contact"):
    if key in curated.get("info", {}):
        info[key] = curated["info"][key]
if "x-agentcash-provenance" in curated:
    spec["x-agentcash-provenance"] = curated["x-agentcash-provenance"]
# Carry over any other curated root-level x-* branding/discovery fields
# (x-logo is consumed by APIs.guru-style directories).
for key, value in curated.items():
    if key.startswith("x-") and key not in spec:
        spec[key] = value
if "servers" in curated:
    spec["servers"] = curated["servers"]

paid = 0
for path, methods in spec.get("paths", {}).items():
    for method, op in methods.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        op.pop("security", None)
        key = f"{method.upper()} {path}"
        price = ROUTE_PRICING.get(key)
        if price is not None and price != "$0.00":
            amount = f"{float(price.lstrip('$')):.6f}"
            atomic = str(int(float(price.lstrip('$')) * 1_000_000))
            op.setdefault("responses", {}).setdefault(
                "402", {"description": "Payment Required — x402 PaymentRequirements challenge"}
            )
            op["security"] = [{"x402": []}]
            op["x-payment-info"] = {
                "price": {"mode": "fixed", "currency": "USD", "amount": amount},
                "protocols": [
                    {"x402": {}},
                    {"mpp": {"method": "tempo", "intent": "charge", "currency": TEMPO_USDC}},
                ],
                # legacy x402scan compat (kept alongside canonical keys)
                "scheme": "x402",
                "network": settings.X402_NETWORK,
                "asset": "USDC",
                "price_atomic_usdc": atomic,
                "decimals": 6,
            }
            paid += 1
        else:
            op["security"] = []

        in_schema = INPUT_SCHEMAS.get(path)
        if in_schema and not op.get("requestBody") and not op.get("parameters"):
            props = in_schema.get("properties", {})
            req = in_schema.get("required", [])
            op["requestBody"] = {
                "required": bool(req),
                "content": {
                    "application/json": {
                        "schema": {"type": "object", "properties": props, "required": req}
                    }
                },
            }

with open(BASE, "w") as fh:
    json.dump(spec, fh, indent=2, ensure_ascii=False)

print(f"openapi.json: {len(spec['paths'])} paths, {paid} paid operations")
