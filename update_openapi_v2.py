"""
Regenerate /openapi.json for AgentCash/x402 discovery.

Adds to the existing spec:
  - info.x-guidance   (agent-facing how-to)
  - per-op input schema from app.middleware.x402.INPUT_SCHEMAS (body for POST, query params for GET)
  - security declarations so paid routes are not flagged "unprotected"
  - info.contact (ownership / Poncho)

Idempotent: safe to run repeatedly.
"""
import json
import sys

sys.path.insert(0, "/opt/CortexCloudAPI")
from app.x402.pricing import ROUTE_PRICING
from app.middleware.x402 import INPUT_SCHEMAS, USDC_ON_BASE

SPEC = "/opt/CortexCloudAPI/openapi.json"

with open(SPEC) as f:
    spec = json.load(f)

# --- info.x-guidance: agent-facing instructions ---
GUIDANCE = (
    "CortexCloud is an agent-native AI + data gateway. Call any /x402/v1/* endpoint; "
    "your first call returns HTTP 402 with an x402 PaymentRequirements challenge "
    "(USDC on Base, chain 8453, fee to our operator). Sign the challenge with your wallet "
    "and resend with the X-PAYMENT header. Pay only for what you call — no API keys, no "
    "subscriptions. Examples: POST /x402/v1/chat/completions (OpenAI-compatible chat), "
    "GET /x402/v1/crypto/price escaped poll, POST /x402/v1/images/generations (image "
    "gen). All prices are fixed per call per USDC atomic units. Use the models endpoint "
    "to discover available models. See /openapi.json for schemas."
)
spec["info"]["x-guidance"] = GUIDANCE

# --- shared security scheme for paid (x402) routes ---
spec.setdefault("components", {}).setdefault("securitySchemes", {})
spec["components"]["securitySchemes"]["x402"] = {
    "type": "http",
    "scheme": "bearer",
    "description": "x402-PAYMENT header. Obtain a PaymentRequestRequirements 402, "
    "answer with a wallet ERC-7715 authorization, pass it back in the X-PAYMENT header.",
}

# --- ensure contact email/name ---
spec["info"].setdefault("contact", {})
spec["info"]["contact"]["email"] = spec["info"]["contact"].get("email") or "team@cortexcloud.org"

# --- per-op input schemas + 402 responses + security ---
def _prop_to_param(name, prop, required):
    """Convert an OpenAPI schema property to a query parameter."""
    schema = {}
    for k in ("type", "enum", "default", "description"):
        if k in prop:
            schema[k] = prop[k]
    p = {"name": name, "in": "query", "required": name in required}
    if prop.get("type") == "array":
        p["schema"] = {"type": "array", "items": prop.get("items", {"type": "string"})}
    elif schema:
        p["schema"] = schema
    else:
        p["schema"] = {"type": "string"}
    return p


added = {"schema": 0, "security": 0}
for path, methods in spec.get("paths", {}).items():
    for method, op in methods.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        # Normalize to /x402 prefixed key that INPUT_SCHEMAS uses
        schema_key = path if path.startswith("/x402") else f"/{method}{path}"
        # INPUT_SCHEMAS keys are like "/x402/v1/search" (no method). Try both:
        in_schema = INPUT_SCHEMAS.get(path)
        # ensure paid route declares security + 402
        # idempotent: strip any stale security from previous runs, then re-apply
        op.pop("security", None)
        if "x-payment-info" in op:
            op.setdefault("responses", {}).setdefault(
                "402", {"description": "Payment Required — x402 PaymentRequirements challenge"}
            )
            _free = path in ("/x402/v1/models", "/x402/v1/mcp", "/v1/dashboard/api-keys")
            if _free:
                # genuinely free route: drop x-payment-info + mark security:[] so the
                # scanner treats it as a plain public catalog, not a probed payable op.
                op.pop("x-payment-info", None)
                op["security"] = []
            else:
                op["security"] = [{"x402": []}]
                added["security"] += 1

            # Input schema: POST -> requestBody, GET -> parameters
            if not op.get("parameters") and not op.get("requestBody") and in_schema:
                props = in_schema.get("properties", {})
                req = in_schema.get("required", [])
                if method == "get":
                    op["parameters"] = [
                        _prop_to_param(k, v, req) for k, v in props.items()
                    ] or []
                    added["schema"] += 1
                else:
                    op["requestBody"] = {
                        "required": (method in ("post", "put", "patch")) and bool(
                            req
                        ),
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": props,
                                    "required": req,
                                }
                            }
                        },
                    }
                    added["schema"] += 1

# Sync amounts from ROUTE_PRICING (drift-proof)
synced = 0
for path, methods in spec.get("paths", {}).items():
    for method, op in methods.items():
        key = f"{method.upper()} {path}"
        price = ROUTE_PRICING.get(key)
        if (
            price
            and op.get("x-payment-info", {}).get("price", {}).get("amount")
        ):
            op["x-payment-info"]["price"]["amount"] = price.lstrip("$")
            synced += 1
        # non-paid/legacy ops that didn't get a security key -> exclude from probing
        if "security" not in op:
            # GET /v1/models requires a Bearer API key but carries no x402/x-payment
            # marker. Declare the real (APIKeyHeader) scheme so scanners don't flag
            # it "unprotected": it 401s without a key.
            if method == "get" and path in ("/v1/models",):
                op["security"] = [{"APIKeyHeader": []}]
            else:
                op["security"] = []

with open(SPEC, "w") as f:
    json.dump(spec, f, indent=2)

print(f"guidance=✓ schema={added['schema']} security={added['security']} synced={synced}")