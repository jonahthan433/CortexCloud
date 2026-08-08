"""
Regenerate /openapi.json for x402 discovery + agent tooling.

Builds the spec from the REAL FastAPI app (create_app(False)), then:
  - info.contact (ownership)
  - x402 security scheme + per-op security for the paid route
  - x-payment-info (price in USD + atomic USDC) on the paid route,
    synced from app.x402.pricing so it can't drift
  - 402 response declaration on the paid route
  - per-op requestBody schema for POST /v1/optimize from INPUT_SCHEMAS

Idempotent: safe to run repeatedly.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.middleware.x402 import INPUT_SCHEMAS, TEMPO_USDC  # noqa: E402
from app.x402.pricing import ROUTE_PRICING  # noqa: E402

SPEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openapi.json")

app = create_app(False)
spec = app.openapi()

GUIDANCE = (
    "CortexCloud — optimization infrastructure for AI agents. Discover, pay for, "
    "and execute classical, hybrid, or quantum optimization through a single API. "
    "POST /v1/estimate is free. POST /v1/optimize returns HTTP 402 with an x402 "
    "PaymentRequirements challenge (USDC on Base, chain 8453). Sign the challenge "
    "with your wallet and resend with the payment-signature header. Poll "
    "GET /v1/jobs/{job_id}. No API keys, no subscriptions."
)
spec["info"]["x-guidance"] = GUIDANCE

# Directory-friendly metadata: absolute server URL (apis.guru requires it),
# logo (apis.guru/Glama/mcp.so render x-logo), and listing category.
spec["servers"] = [{"url": "https://api.cortexcloud.org"}]
spec["x-logo"] = {"url": "https://api.cortexcloud.org/cortex-logo.png"}
spec["info"]["x-apisguru-categories"] = ["optimization"]

spec.setdefault("components", {}).setdefault("securitySchemes", {})
spec["components"]["securitySchemes"]["x402"] = {
    "type": "http",
    "scheme": "bearer",
    "description": "x402 payment: obtain a 402 PaymentRequirements challenge, "
    "answer with a wallet authorization, pass it back in the X-PAYMENT signature header.",
}

spec["info"].setdefault("contact", {})
spec["info"]["contact"]["email"] = "team@cortexcloud.org"


def _usd_atomic(price_str: str) -> str:
    try:
        return str(int(float(price_str.lstrip("$")) * 1_000_000))
    except ValueError:
        return "0"


paid = 0
for path, methods in spec.get("paths", {}).items():
    for method, op in methods.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        op.pop("security", None)
        key = f"{method.upper()} {path}"
        if key in ROUTE_PRICING:
            price = ROUTE_PRICING[key]
            op.setdefault("responses", {}).setdefault(
                "402", {"description": "Payment Required — x402 PaymentRequirements challenge"}
            )
            op["security"] = [{"x402": []}]
            amount = f"{float(price.lstrip('$')):.6f}"
            op["x-payment-info"] = {
                # AgentCash / IETF canonical shape
                "price": {"mode": "fixed", "currency": "USD", "amount": amount},
                "protocols": [
                    {"x402": {}},
                    {"mpp": {"method": "tempo", "intent": "charge", "currency": TEMPO_USDC}},
                ],
                # legacy x402scan compat (kept alongside canonical keys)
                "scheme": "x402",
                "network": settings.X402_NETWORK,
                "asset": "USDC",
                "price_atomic_usdc": _usd_atomic(price),
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

with open(SPEC, "w") as f:
    json.dump(spec, f, indent=2)

print(f"openapi.json regenerated: {len(spec.get('paths', {}))} paths, {paid} x402-paid operation(s)")
print(f"  info.title      = {spec['info']['title']}")
print(f"  info.contact    = {spec['info'].get('contact', {}).get('email')}")
print(f"  paid operation  = {[ (m.upper()+' '+p) for p, ms in spec['paths'].items() for m, op in ms.items() if op.get('x-payment-info') ]}")