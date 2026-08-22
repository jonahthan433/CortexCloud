"""Root discovery endpoints — /.well-known/x402.json and /llms.txt.

Generated at request time from live config (app.x402.pricing) so they
never describe a stale surface. Covers the paid route (/v1/optimize) and
the free endpoints agents need.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.x402.pricing import FREE_ROUTES, MODE_PRICE_USD, ROUTE_DESCRIPTIONS, ROUTE_PRICING, effective_price_usd

router = APIRouter()


def _usd_atomic(price_str: str) -> str:
    try:
        return str(int(float(price_str.lstrip("$")) * 1_000_000))
    except ValueError:
        return "0"


def build_manifest(active: bool = True) -> dict:
    if not active:
        return {"x402": False, "message": "x402 payment gateway is not enabled on this instance."}

    endpoints = [
        {
            "path": path.split(" ", 1)[1],
            "method": path.split(" ", 1)[0],
            "price": price,
            "price_atomic_usdc": _usd_atomic(price),
            "description": ROUTE_DESCRIPTIONS.get(path, "Solve an optimization problem (x402-paid)"),
        }
        for path, price in ROUTE_PRICING.items()
        if float(price.lstrip("$")) > 0.0
    ]

    return {
        "x402": True,
        "version": 2,
        "facilitator": settings.X402_FACILITATOR_URL,
        "merchant_wallet": settings.WALLET_ADDRESS,
        "pricing_currency": "USDC",
        "pricing_decimals": 6,
        "network": {"chainId": 8453, "eip155": settings.X402_NETWORK, "name": "Base"},
        "endpoints": endpoints,
        "free_endpoints": [
            {"path": p.split(" ", 1)[1], "method": p.split(" ", 1)[0], "description": d}
            for p, d in FREE_ROUTES.items()
        ],
    }


@router.get("/.well-known/x402.json", tags=["x402 Discovery"])
async def well_known_x402():
    return build_manifest()


@router.get("/.well-known/x402", tags=["x402 Discovery"])
async def well_known_x402_v1():
    """v1 discovery document (resource URL list) — the shape x402scan-mcp and
    other v1 discovery tools parse. The rich v2 manifest stays at x402.json."""
    return {
        "version": 1,
        "resources": [
            "https://api.cortexcloud.org/v1/optimize",
            "https://api.cortexcloud.org/v1/estimate",
            "https://api.cortexcloud.org/v1/backends",
            "https://api.cortexcloud.org/v1/capabilities",
            "https://api.cortexcloud.org/v1/examples",
        ],
        "instructions": "Pay-per-call QUBO/Ising optimization via x402 (USDC on Base eip155:8453). Full pricing: https://api.cortexcloud.org/v1/capabilities; rich manifest: https://api.cortexcloud.org/.well-known/x402.json; agent docs: https://api.cortexcloud.org/llms.txt.",
    }


@router.get("/.well-known/agentsearch.txt", tags=["x402 Discovery"])
async def agentsearch_txt():
    """Agent-search discovery file (agentsearch.txt convention): what this
    service is, how agents call it, and where the machine-readable docs live."""
    prices = " / ".join(f"{m} ${effective_price_usd(m):.2f}" for m in MODE_PRICE_USD)
    text = "\n".join([
        "Name: CortexCloud Optimization Network",
        "Description: Pay-per-call QUBO/Ising optimization API over x402 (USDC on Base, eip155:8453). Estimate is free; optimize is paid per run. Prices: " + prices + ". Quantum QPU execution is opt-in and only recommended with benchmark evidence.",
        "Human URL: https://api.cortexcloud.org/",
        "Commands:",
        "- POST /v1/estimate with {mode, n, data} for a free recommendation (decision block) and price.",
        "- POST /v1/optimize with {mode: auto|classical|hybrid|quantum, n, data} to solve; a 402 x402 challenge is returned, settle USDC on Base, then poll the job.",
        "- GET /v1/jobs/{job_id} to poll job status (succeeded/failed + solution).",
        "- GET /v1/backends for solver backends and live availability.",
        "Discovery: https://api.cortexcloud.org/llms.txt, https://api.cortexcloud.org/.well-known/x402.json, https://api.cortexcloud.org/.well-known/bazaar, https://api.cortexcloud.org/.well-known/agentsearch.txt, https://api.cortexcloud.org/openapi.json",
        "Pricing: https://api.cortexcloud.org/v1/capabilities",
        "# Data API (alchemy/coingecko) is built but DISABLED in production (DATA_ENABLED=false) pending validation. Do not call /v1/data/* — they return 503 until enabled.",
    ])
    return PlainTextResponse(text + "\n", media_type="text/plain; charset=utf-8")


@router.get("/llms.txt", tags=["x402 Discovery"])
async def llms_txt():
    paid = [
        f"- {path.split(' ', 1)[0]} {path.split(' ', 1)[1]} — {price}"
        for path, price in sorted(ROUTE_PRICING.items())
        if float(price.lstrip("$")) > 0.0
    ]
    free = [f"- {path} — {desc}" for path, desc in sorted(FREE_ROUTES.items())]

    text = f"""# CortexCloud

CortexCloud — an agent-native API platform. Agents discover, pay for, and
execute services across six categories: **AI, Research, Data, ML, Automation
and Quantum**. Every paid endpoint is reachable over x402 (USDC on Base,
eip155:8453) — no API keys, no subscriptions, permissionless settlement.
Quantum is one vertical within the broader platform; AI and Research are the
first expansion beyond it.

## Workflow (agent-first)

1. POST /v1/ai/estimate or /v1/research/estimate (free) — get the predicted
   USDC price before paying.
2. POST /v1/ai/chat, /v1/ai/embed, /v1/ai/transcribe, /v1/research/search,
   /v1/research/answer (x402, paid) — receive a 402 PaymentRequirements
   challenge; sign and resend with the payment-signature header.
3. For optimization: POST /v1/estimate (free) then POST /v1/optimize (paid);
   poll GET /v1/jobs/{{job_id}}.

## Endpoints

{chr(10).join(paid + free)}

## AI examples (real)

- POST /v1/ai/chat — {{"messages": [{{"role":"user","content":"..."}}], "model":"gemini-2.5-flash", "max_tokens": 128}}
- POST /v1/ai/embed — {{"input": ["text to embed"]}}
- POST /v1/research/search — {{"query": "latest quantum error correction", "count": 5}}

## Quantum (one vertical)

POST /v1/optimize solves QUBO/Ising (classical/hybrid/quantum). POST /v1/estimate
returns a machine-readable decision block. Quantum is never recommended
without measured evidence; check /v1/backends for an available=true backend.

## When NOT to use

- Quantum: n > 5000 variables, or no available=true QPU backend (fails honestly).
- AI/Research routes when AI_ENABLED / RESEARCH_ENABLED are false (return 503).
- Data API (/v1/data/*): built but DISABLED in production (DATA_ENABLED=false)
  pending production validation. Returns 503 until enabled — do not call it yet.

## Discovery

- MCP server (Streamable HTTP): https://api.cortexcloud.org/mcp
- Payment manifest (x402): https://api.cortexcloud.org/.well-known/x402.json
- Bazaar discovery: https://api.cortexcloud.org/.well-known/bazaar
- OpenAPI: https://api.cortexcloud.org/openapi.json

## Honesty

Provider costs are published and CortexCloud margin is computed transparently;
no fabricated capabilities, statistics, or performance claims. A backend is
only ever listed when it verifiably runs.

## Reference

- GitHub: https://github.com/jonahthan433/CortexCloudAPI
"""
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")