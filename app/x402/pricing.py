"""x402 pricing — single source of truth for paid/free routes.

/v1/optimize is the only paid route; its price follows the requested
mode (classical 0.05 / hybrid 0.10 / quantum 0.85). Everything else is
free. The middleware reads this dict by path to build the 402 challenge,
so this table is also what discovery (/.well-known/x402.json, llms.txt,
bazaar) renders.

Costs are kept separate from prices: MODE_PRICE_USD is what customers
pay; PROVIDER_COST_USD is our estimated per-run provider cost (model
basis; finer per-device estimates live in the solver adapters, e.g. the
braket device cfg). gross_margin_usd(mode) = price - cost. Quantum must
never be sold below estimated provider cost unless QUANTUM_ALLOW_SUBSIDY
=true (enforced in runner.quantum_cost_cap_error + braket preflight).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
# ---------------------------------------------------------------------------
# AI + Research expansion pricing.
#
# Provider costs are NOT hardcoded into business logic: each provider exposes
# a published-rate table and an estimate_cost() method. Customer price is
# pegged to that live provider cost via PRICING.markup + floor, so when a
# provider reprices, CortexCloud margin is preserved automatically. The
# published rates below are VERIFIED advertised list rates (Aug 2026) and are
# data, not logic — they live in PROVIDER_PRICING so they can be updated in
# one place without touching any route.
# ---------------------------------------------------------------------------

# Markup applied over provider cost, and the minimum customer price floor so
# tiny calls still cover ~$0.0015 infra+payment fixed cost at a healthy margin.
PRICING_MARKUP = 1.35          # 35% gross margin over provider cost
PRICING_FLOOR_USD = 0.004      # minimum sell price for any AI/Research call
INFRA_FIXED_USD = 0.0015       # compute+db+bandwidth+hosting+payment relay


@dataclass
class ProviderPricing:
    """Published, advertised provider rates. Data only — no business logic."""
    name: str
    # token-based models: (input $/1M tokens, output $/1M tokens)
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    # flat per-call rate (search/answer/embed fallbacks)
    per_call: float = 0.0


# Verified advertised list rates (Aug 2026). OpenRouter passes through
# first-party prices; Brave Search API published plan rates.
PROVIDER_PRICING = {
    # --- AI: OpenRouter unified gateway (one key, first-party rates) ---
    "openrouter:gemini-2.5-flash": ProviderPricing("Google Gemini 2.5 Flash", 0.30, 2.50),
    "openrouter:gemini-2.0-flash": ProviderPricing("Google Gemini 2.0 Flash", 0.10, 0.40),
    "openrouter:gpt-4o-mini": ProviderPricing("OpenAI GPT-4o-mini", 0.15, 0.60),
    "openrouter:gemini-text-embedding-004": ProviderPricing("Google text-embedding-004", 0.025, 0.0),
    # --- AI: Gemini STT (free-tier/metered; flat per-request estimate) ---
    "gemini:stt": ProviderPricing("Google Gemini STT", per_call=0.0005),
    # --- Research: Brave Search API published plan rates (Aug 2026) ---
    "brave:web": ProviderPricing("Brave Web Search", per_call=0.004),
    "brave:answer": ProviderPricing("Brave AI-Grounding answer", per_call=0.005),
}


@dataclass
class ProviderCost:
    provider_cost_usd: float
    detail: str = ""


class BaseProvider:
    """Provider abstraction. Concrete providers implement estimate_cost()
    from the advertised rate table so the public API never changes when a
    vendor is swapped (e.g. Brave -> Exa)."""

    slug: str = "base"
    # (name, api_model_id) tuples the route accepts
    models: tuple = ()

    def estimate_cost(self, *args, **kwargs) -> ProviderCost:  # pragma: no cover
        raise NotImplementedError


class OpenRouterAIChat(BaseProvider):
    slug = "openrouter"
    models = (
        ("gemini-2.5-flash", "openrouter:gemini-2.5-flash"),
        ("gemini-2.0-flash", "openrouter:gemini-2.0-flash"),
        ("gpt-4o-mini", "openrouter:gpt-4o-mini"),
    )
    _DEFAULT = "gemini-2.5-flash"

    def estimate_cost(self, model: str | None = None,
                      input_tokens: int = 0, output_tokens: int = 0, **_kw) -> ProviderCost:
        key = dict(self.models).get(model or self._DEFAULT, "openrouter:gemini-2.5-flash")
        p = PROVIDER_PRICING[key]
        cost = (input_tokens / 1_000_000 * (p.input_per_1m or 0)
                + output_tokens / 1_000_000 * (p.output_per_1m or 0))
        return ProviderCost(cost, f"{key} in={input_tokens} out={output_tokens}")


class OpenRouterEmbed(BaseProvider):
    slug = "openrouter"
    models = (("text-embedding-004", "openrouter:gemini-text-embedding-004"),)
    _DEFAULT = "text-embedding-004"

    def estimate_cost(self, model: str | None = None, input_tokens: int = 0, **_kw) -> ProviderCost:
        p = PROVIDER_PRICING["openrouter:gemini-text-embedding-004"]
        cost = input_tokens / 1_000_000 * (p.input_per_1m or 0)
        return ProviderCost(cost, f"embed in={input_tokens}")


class GeminiSTT(BaseProvider):
    slug = "gemini"
    models = (("default", "gemini:stt"),)

    def estimate_cost(self, seconds: float = 0.0, **_kw) -> ProviderCost:
        # Metered per-minute upstream; flat per-request estimate.
        return ProviderCost(PROVIDER_PRICING["gemini:stt"].per_call, f"stt ~{seconds:.0f}s")


class BraveSearch(BaseProvider):
    slug = "brave"
    models = (("web", "brave:web"), ("answer", "brave:answer"))

    def estimate_cost(self, kind: str = "web", **_kw) -> ProviderCost:
        key = "brave:answer" if kind == "answer" else "brave:web"
        return ProviderCost(PROVIDER_PRICING[key].per_call, key)


# Registry: route -> provider instance. Swap a vendor by changing the class.
AI_PROVIDERS = {
    "chat": OpenRouterAIChat(),
    "embed": OpenRouterEmbed(),
    "transcribe": GeminiSTT(),
}
RESEARCH_PROVIDERS = {
    "search": BraveSearch(),
    "answer": BraveSearch(),
}


def pegged_price(provider_cost_usd: float, floor: float = PRICING_FLOOR_USD) -> float:
    """Customer price = max(floor, provider_cost * markup + infra fixed)."""
    return max(floor, round(provider_cost_usd * PRICING_MARKUP + INFRA_FIXED_USD, 6))


# Chat price needs the token counts; estimate first, then peg.
def ai_chat_cost(model: str | None, input_tokens: int, output_tokens: int) -> ProviderCost:
    return AI_PROVIDERS["chat"].estimate_cost(model, input_tokens, output_tokens)


def ai_chat_price_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    return pegged_price(ai_chat_cost(model, input_tokens, output_tokens).provider_cost_usd)


def ai_embed_price_usd(input_tokens: int) -> float:
    return pegged_price(AI_PROVIDERS["embed"].estimate_cost(input_tokens=input_tokens).provider_cost_usd)


def ai_transcribe_price_usd(seconds: float = 0.0) -> float:
    return pegged_price(AI_PROVIDERS["transcribe"].estimate_cost(seconds=seconds).provider_cost_usd)


def research_price_usd(kind: str = "web") -> float:
    return pegged_price(RESEARCH_PROVIDERS["search"].estimate_cost(kind).provider_cost_usd)


# mode -> USD per optimization run (customer price)
MODE_PRICE_USD = {"classical": 0.05, "hybrid": 0.10, "quantum": 0.85}

# mode -> estimated provider cost per run, USD (model basis). Quantum
# reflects the verified Aug-2026 Rigetti Cepheus-1-108Q run (1024 shots,
# $0.35). Solver adapters may carry finer per-device estimates; this
# table is the documented default the margin guard reasons about.
# Quantum mode cost: $0.50/run (Braket rigetti, primary provider; fixed
# 1024 shots -> flat cost) + buffer. IBM Open Plan fallback costs $0.00 and
# stays sellable at the effective price via the per-provider margin guard.
# Verified Rigetti Cepheus-1-108Q on Braket: $0.30/task + $0.000425/shot
# (published rate card, Aug-2026) = $0.7352 at the fixed 1024 shots; round
# up 0.75 as the billing buffer. IBM Open Plan fallback costs $0.00.
PROVIDER_COST_USD = {"classical": 0.0, "hybrid": 0.0, "quantum": 0.75}

# Per-request fixed costs beyond provider spend (model basis):
INFRA_COST_USD = 0.0010     # compute, DB, bandwidth, Cloudflare, hosting
PAYMENT_COST_USD = 0.0005   # x402 verify + settlement relay + ledger write


def total_cost_usd(mode: str, provider_cost: float | None = None) -> float:
    """All-in cost of one paid request: provider + infra + payment."""
    m = (mode or "auto").lower()
    prov = PROVIDER_COST_USD.get(m, 0.0) if provider_cost is None else float(provider_cost)
    return prov + INFRA_COST_USD + PAYMENT_COST_USD

# Margin policy: the charged price for a mode is never below the list
# price, and never below provider_cost x MARKUP — prices move with
# provider cost automatically. List prices are the published floor.
MARKUP = 2.0

ROUTE_PRICING = {
    "POST /v1/optimize": "$0.05",  # base; middleware overrides per mode
    # AI category — price overridden per-request from token counts (pegged to provider cost).
    "POST /v1/ai/chat": "$0.004",
    "POST /v1/ai/embed": "$0.004",
    "POST /v1/ai/transcribe": "$0.004",
    # Research category — flat per-call, pegged to Brave cost.
    "POST /v1/research/search": "$0.006",
    "POST /v1/research/answer": "$0.012",
    # Data API (Tier 1) — all endpoints at the $0.004 floor; provider cost is
    # far below the floor, so the charged price is the floor (see DATA block).
    "POST /v1/data/token-balances": "$0.004",
    "POST /v1/data/token-price": "$0.004",
    "POST /v1/data/nft-ownership": "$0.004",
    "POST /v1/data/tx-history": "$0.004",
    "GET /v1/data/gas-oracle": "$0.004",
    "GET /v1/data/block": "$0.004",
}

ROUTE_DESCRIPTIONS = {
    "POST /v1/optimize": "Solve a QUBO/Ising optimization problem. USDC on Base via x402; returns a job_id to poll.",
    "POST /v1/ai/chat": "Chat completion via OpenRouter (Gemini/OpenAI). x402-paid, USDC on Base. Price quoted from requested max_tokens + estimated input.",
    "POST /v1/ai/embed": "Text embeddings via Google text-embedding-004 (OpenRouter). x402-paid per token.",
    "POST /v1/ai/transcribe": "Speech-to-text via Gemini. x402-paid per request.",
    "POST /v1/research/search": "Grounded web search with citations via Brave Search API. x402-paid per call.",
    "POST /v1/research/answer": "Cited answer synthesis via Brave AI-Grounding. x402-paid per call.",
    # Data API (Tier 1)
    "POST /v1/data/token-balances": "ERC-20 token balances for a wallet on a chain (Alchemy Token API). x402-paid, USDC on Base.",
    "POST /v1/data/token-price": "Spot USD price for a token/coin (CoinGecko where free tier suffices, else Alchemy). x402-paid.",
    "POST /v1/data/nft-ownership": "NFTs owned by a wallet on a chain (Alchemy NFT API). x402-paid, USDC on Base.",
    "POST /v1/data/tx-history": "Normalized transactions for an address on a chain (Alchemy Transfers API). x402-paid, USDC on Base.",
    "GET /v1/data/gas-oracle": "Current base fee + priority fee (gas price) for a chain (Alchemy). x402-paid, USDC on Base.",
    "GET /v1/data/block": "Block by number or 'latest' on a chain (Alchemy). x402-paid, USDC on Base.",
}

FREE_ROUTES = {
    "POST /v1/estimate": "Analyze a problem (free) — recommended mode/algorithm/backend, decision block for agents, estimated runtime and USDC price.",
    "GET /v1/jobs/{job_id}": "Poll an optimization job by id (free).",
    "GET /v1/backends": "List solver backends and availability (free).",
    "GET /v1/capabilities": "Service capabilities, limits, payment terms (free).",
    "GET /v1/examples": "Canonical portfolio/assignment/scheduling/routing/QUBO examples with schemas, constraints and pricing (free).",
    "POST /v1/simulate": "Dry-run a problem (free) — feasibility and confidence score before paying for a solve.",
    "POST /v1/solvers/portfolio": "Build a cardinality-constrained Markowitz QUBO from returns/covariance (free).",
    "POST /v1/solvers/bin-packing": "Build a bin-packing QUBO from item weights and bin capacity (free).",
    "POST /v1/solvers/routing": "Build a TSP tour QUBO from a distance matrix (free).",
    # AI + Research free discovery/estimate endpoints.
    "POST /v1/ai/estimate": "Free: predict token cost + USDC price for a chat request before paying.",
    "POST /v1/research/estimate": "Free: predict the USDC price for a search/answer request before paying.",
}


def price_for_mode(mode: str, n: int | None = None) -> str:
    return f"${effective_price_usd(mode, n=n):.6f}"


# Size-based classical pricing: exact brute-force fits n<=20, heuristic
# classical (SA) handles mid problems, large jobs are premium compute.
CLASSICAL_SIZE_TIERS: tuple[tuple[int, float], ...] = ((20, 0.05), (200, 0.10), (2**31 - 1, 0.25))


def classical_price_for_n(n: int) -> float:
    """Classical customer price by problem size (n variables)."""
    n = int(n or 0)
    for cap, price in CLASSICAL_SIZE_TIERS:
        if n <= cap:
            return price
    return 0.25


def effective_price_usd(mode: str, provider_cost: float | None = None, n: int | None = None) -> float:
    """Charged price for a mode: max(list price, provider cost x MARKUP).
    Classical/auto prices are size-aware (n tiers). provider_cost defaults
    to the mode's estimated provider cost, so the price rises automatically
    if provider costs climb."""
    m = (mode or "auto").lower()
    if m in ("classical", "auto") and n is not None:
        base = classical_price_for_n(n)
    else:
        base = MODE_PRICE_USD.get(m, MODE_PRICE_USD["classical"])
    cost = total_cost_usd(m, provider_cost)
    return max(base, cost * MARKUP)


def sellable_at_mode_price(mode: str, provider_cost: float) -> bool:
    """True when a provider's estimated cost fits under the charged price
    (margin >= 0 at current prices)."""
    try:
        return total_cost_usd(mode, provider_cost) <= effective_price_usd(mode)
    except (TypeError, ValueError):
        return False


def gross_margin_usd(mode: str) -> float:
    """Customer price minus estimated provider cost, USD."""
    m = (mode or "auto").lower()
    return effective_price_usd(m) - total_cost_usd(m)


def below_cost(mode: str) -> bool:
    """True when the route would sell below estimated provider cost."""
    return gross_margin_usd(mode) < 0.0


def usd_to_usdc_atomic(usd_str: str) -> int:
    try:
        return int(float(usd_str.lstrip("$")) * 1_000_000)
    except (TypeError, ValueError):
        return 0


def usdc_atomic_to_usd(atomic: int) -> float:
    return int(atomic) / 1_000_000


# ---------------------------------------------------------------------------
# Data API (Tier 1) — Alchemy primary, CoinGecko where free tier suffices.
#
# VERIFIED provider economics (Aug 2026, not invented):
#   - Alchemy Pay-As-You-Go: $0.45 per 1,000,000 Compute Units (CU);
#     $0.40/M after 300M CU/mo. Free tier = 30,000,000 CU/mo.
#     Documented avg ~25 CU per API call -> PAYG marginal ~$0.00001125/call.
#   - CoinGecko free/Demo: 10,000 calls/mo, ~30-100/min, $0.00.
# So every Data endpoint's provider cost is well under the $0.004 floor:
# the charged price IS the floor and margin auto-derives. If Alchemy reprices
# (CU rate or avg-per-call CU), update PROVIDER_PRICING['alchemy:call'].cost
# in ONE place and CortexCloud price/margin follow automatically.
# ---------------------------------------------------------------------------

# Provider cost is expressed as a flat per-call USD figure (avg CU basis).
# `cost` here = the data field the route passes to estimate_cost(); the helper
# returns it as provider_cost_usd. Keeps the same data-only table contract as AI.
PROVIDER_PRICING["alchemy:call"] = ProviderPricing("Alchemy (avg ~25 CU/call)", per_call=0.00001125)
PROVIDER_PRICING["coingecko:price"] = ProviderPricing("CoinGecko (free tier)", per_call=0.0)


class AlchemyData(BaseProvider):
    """Alchemy Data API (Token/NFT/Transfers/Node). One key, one vendor."""
    slug = "alchemy"
    models = (("alchemy", "alchemy:call"),)

    def estimate_cost(self, *a, **_kw) -> ProviderCost:
        # Flat per-call cost on the avg-CU basis. `calls` lets batch endpoints
        # scale honestly (e.g. multi-token balance fan-out); default 1.
        calls = max(1, int(_kw.get("calls", 1)))
        return ProviderCost(self._cost() * calls,
                            f"alchemy {calls} call(s) @ {self._cost():.8f}")

    @staticmethod
    def _cost() -> float:
        return PROVIDER_PRICING["alchemy:call"].per_call


class CoinGeckoData(BaseProvider):
    """CoinGecko price (free tier where it suffices)."""
    slug = "coingecko"
    models = (("coingecko", "coingecko:price"),)

    def estimate_cost(self, *a, **_kw) -> ProviderCost:
        return ProviderCost(PROVIDER_PRICING["coingecko:price"].per_call, "coingecko free tier")


DATA_PROVIDERS = {
    "token-balances": AlchemyData(),
    "nft-ownership": AlchemyData(),
    "tx-history": AlchemyData(),
    "gas-oracle": AlchemyData(),
    "block": AlchemyData(),
    "token-price": CoinGeckoData(),   # CoinGecko free tier; see route for fallback to Alchemy
}


def data_provider_cost_usd(endpoint: str, calls: int = 1) -> float:
    """Estimated provider cost USD for a Data endpoint (public, recomputable)."""
    prov = DATA_PROVIDERS.get(endpoint, AlchemyData())
    return round(prov.estimate_cost(calls=calls).provider_cost_usd, 8)


def data_price_usd(endpoint: str, calls: int = 1) -> float:
    """Charged price = pegged(floor-aware) provider cost. Floor => $0.004."""
    return pegged_price(data_provider_cost_usd(endpoint, calls))


# Endpoint -> cache TTL (seconds). Short, because Data is hot/changing.
# Per the brief: price 10s, balances 15s, gas 5s, block 5s. Tx/NFT 15s.
DATA_TTL_S = {
    "token-price": 10,
    "token-balances": 15,
    "nft-ownership": 15,
    "tx-history": 15,
    "gas-oracle": 5,
    "block": 5,
}

# Canonical chain ids we accept (EVM). Maps caller "chain" -> Alchemy network slug.
DATA_CHAINS = {
    "ethereum": "eth-mainnet",
    "eth": "eth-mainnet",
    "1": "eth-mainnet",
    "base": "base-mainnet",
    "8453": "base-mainnet",
    "arbitrum": "arb-mainnet",
    "42161": "arb-mainnet",
    "polygon": "polygon-mainnet",
    "137": "polygon-mainnet",
    "optimism": "opt-mainnet",
    "10": "opt-mainnet",
}
DEFAULT_CHAIN = "ethereum"

# ---------------------------------------------------------------------------
# ML API (Tier 1) — image-generate / image-understand / rerank.
#
# VERIFIED published provider rates (Aug 2026, data not logic):
#   - fal.ai SDXL: ~$0.0015-0.004 /image; Flux.1: ~$0.01-0.03 /image (per-call).
#   - Replicate (fallback) SDXL: ~$0.002-0.005 /image; similar Flux.
#   - Cohere rerank-v3: ~$0.001 /1k docs ranked; Jina rerank ~$0.001 /1k.
#   - Gemini vision (image-understand) via OpenRouter: ~$0.0003 /call.
# Charged price = pegged(floor-aware) provider cost (same model as AI/Data),
# so margins auto-peg and a provider reprice is a one-line table edit.
# ---------------------------------------------------------------------------
PROVIDER_PRICING["fal:sdxl"] = ProviderPricing("fal.ai SDXL", per_call=0.003)
PROVIDER_PRICING["fal:flux"] = ProviderPricing("fal.ai Flux.1", per_call=0.02)
PROVIDER_PRICING["replicate:sdxl"] = ProviderPricing("Replicate SDXL", per_call=0.004)
PROVIDER_PRICING["replicate:flux"] = ProviderPricing("Replicate Flux.1", per_call=0.025)
PROVIDER_PRICING["cohere:rerank"] = ProviderPricing("Cohere rerank-v3", per_call=0.001)
PROVIDER_PRICING["jina:rerank"] = ProviderPricing("Jina rerank", per_call=0.001)
PROVIDER_PRICING["openrouter:gemini-vision"] = ProviderPricing("Gemini 2.5 Flash vision", 0.30, 2.50)


class FalImage(BaseProvider):
    slug = "fal"
    models = (("sdxl", "fal:sdxl"), ("flux", "fal:flux"))

    def estimate_cost(self, model: str | None = None, **_kw) -> ProviderCost:
        key = "fal:flux" if (model or "sdxl") == "flux" else "fal:sdxl"
        return ProviderCost(PROVIDER_PRICING[key].per_call, key)


class ReplicateImage(BaseProvider):
    slug = "replicate"
    models = (("sdxl", "replicate:sdxl"), ("flux", "replicate:flux"))

    def estimate_cost(self, model: str | None = None, **_kw) -> ProviderCost:
        key = "replicate:flux" if (model or "sdxl") == "flux" else "replicate:sdxl"
        return ProviderCost(PROVIDER_PRICING[key].per_call, key)


class CohereRerank(BaseProvider):
    slug = "cohere"
    models = (("rerank-v3", "cohere:rerank"),)

    def estimate_cost(self, docs: int = 0, **_kw) -> ProviderCost:
        return ProviderCost(PROVIDER_PRICING["cohere:rerank"].per_call, "cohere:rerank")


class JinaRerank(BaseProvider):
    slug = "jina"
    models = (("rerank", "jina:rerank"),)

    def estimate_cost(self, docs: int = 0, **_kw) -> ProviderCost:
        return ProviderCost(PROVIDER_PRICING["jina:rerank"].per_call, "jina:rerank")


class GeminiVision(BaseProvider):
    slug = "openrouter"
    models = (("gemini-2.5-flash", "openrouter:gemini-vision"),)

    def estimate_cost(self, model: str | None = None, input_tokens: int = 0, output_tokens: int = 0, **_kw) -> ProviderCost:
        # Free OpenRouter multimodal models (id endswith ':free') cost $0.
        if (model or settings.ML_VISION_MODEL).endswith(":free"):
            return ProviderCost(0.0, "openrouter:gemini-vision:free")
        return ProviderCost(
            PROVIDER_PRICING["openrouter:gemini-vision"].input_per_1m / 1_000_000 * (input_tokens or 300)
            + PROVIDER_PRICING["openrouter:gemini-vision"].output_per_1m / 1_000_000 * (output_tokens or 200),
            "openrouter:gemini-vision",
        )


ML_PROVIDERS = {
    "image-generate": (FalImage(), ReplicateImage()),   # primary, fallback
    "image-understand": GeminiVision(),
    "rerank": (CohereRerank(), JinaRerank()),           # primary, fallback
}


def ml_provider_cost_usd(endpoint: str, model: str | None = None, docs: int = 0, input_tokens: int = 0, output_tokens: int = 0) -> float:
    """Estimated provider cost USD for an ML endpoint (public, recomputable)."""
    prov = ML_PROVIDERS.get(endpoint)
    if prov is None:
        return 0.0
    primary = prov[0] if isinstance(prov, tuple) else prov
    if endpoint == "rerank":
        return round(primary.estimate_cost(docs=docs).provider_cost_usd, 8)
    if endpoint == "image-understand":
        return round(primary.estimate_cost(input_tokens=input_tokens, output_tokens=output_tokens).provider_cost_usd, 8)
    return round(primary.estimate_cost(model=model).provider_cost_usd, 8)


def ml_price_usd(endpoint: str, model: str | None = None, docs: int = 0, input_tokens: int = 0, output_tokens: int = 0) -> float:
    """Charged price = pegged(floor-aware) provider cost. Floor => $0.004 (gen) / rerank $0.006."""
    floor = 0.006 if endpoint == "rerank" else 0.004
    return pegged_price(ml_provider_cost_usd(endpoint, model, docs, input_tokens, output_tokens), floor)


# Endpoint -> cache TTL (seconds). Image-gen is uncacheable (per-request);
# understand/rerank are deterministic on input -> short TTL.
ML_TTL_S = {
    "image-generate": 0,
    "image-understand": 15,
    "rerank": 30,
}


# Register ML paid routes + free estimate in the single source of truth.
ROUTE_PRICING.update({
    "POST /v1/ml/image-generate": f"${ml_price_usd('image-generate', 'sdxl'):.3f}",
    "POST /v1/ml/image-understand": f"${ml_price_usd('image-understand'):.3f}",
    "POST /v1/ml/rerank": f"${ml_price_usd('rerank'):.3f}",
})
ROUTE_DESCRIPTIONS.update({
    "POST /v1/ml/image-generate": "Text-to-image generation (fal.ai primary, Replicate fallback; SDXL/Flux). x402-paid, USDC on Base.",
    "POST /v1/ml/image-understand": "Vision: caption / OCR / describe an image (Gemini vision via OpenRouter). x402-paid, USDC on Base.",
    "POST /v1/ml/rerank": "Result reranking by relevance (Cohere primary, Jina fallback). x402-paid, USDC on Base.",
})
FREE_ROUTES.update({
    "POST /v1/ml/estimate": "Free: predict the USDC price for an ML request before paying.",
})

