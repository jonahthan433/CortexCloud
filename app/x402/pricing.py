"""
Centralized pricing configuration for x402 payment-gated routes.

Prices are in USD strings (e.g. "$0.005" = 0.5¢ per request).
These are converted to USDC atomic units (6 decimals on Base) for the x402 challenge.
"""

# Default per-request prices by route (only for the /x402/v1 prefix)
ROUTE_PRICING: dict[str, str] = {
    # Chat completions
    "POST /x402/v1/chat/completions": "$0.005",
    "POST /x402/v1/responses": "$0.005",
    
    # Embeddings
    # S1: flat $0.005 per call regardless of batch size (better economics for
    # agents doing bulk embedding).
    "POST /x402/v1/embeddings": "$0.005",
    
    # Models (Free)
    "GET /x402/v1/models": "$0.00",
    
    # Data marketplace (Phase B) — keyless upstreams
    
    # On-chain Base data (Phase B extension) — public RPC, keyless
    "GET /x402/v1/data/base/balance": "$0.005",
    "GET /x402/v1/data/base/token-balance": "$0.005",
    "GET /x402/v1/data/base/nonce": "$0.005",
    "GET /x402/v1/data/prices": "$0.005",
    "GET /x402/v1/data/coins/search": "$0.005",
    "GET /x402/v1/data/dex/search": "$0.005",
    "GET /x402/v1/data/dex/pairs": "$0.005",
    # ---- Wave 1: Market data (keyless public upstreams) ----
    "GET /x402/v1/defillama/chains": "$0.005",
    "GET /x402/v1/defillama/protocols": "$0.005",
    "GET /x402/v1/defillama/protocol": "$0.005",
    "GET /x402/v1/defillama/prices": "$0.005",
    "GET /x402/v1/defillama/yields": "$0.005",
    "GET /x402/v1/crypto/list": "$0.005",
    "GET /x402/v1/crypto/price": "$0.005",
    "GET /x402/v1/crypto/history": "$0.01",
    "GET /x402/v1/fx/list": "$0.005",
    "GET /x402/v1/fx/price": "$0.005",
    "GET /x402/v1/fx/history": "$0.01",
    "POST /x402/v1/rpc/ethereum": "$0.005",
    # ---- Wave 2: AI modalities (provider keys) ----
    "POST /x402/v1/images/generations": "$0.02",
    "POST /x402/v1/images/image2image": "$0.04",
    "POST /x402/v1/audio/speech": "$0.02",
    "POST /x402/v1/audio/transcriptions": "$0.003",
    "POST /x402/v1/messages": "$0.005",
    "POST /x402/v1/videos/generations": "$0.20",
    # ---- Wave 3: Search (Exa AI) ----
    "POST /x402/v1/search": "$0.03",
    "POST /x402/v1/search/contents": "$0.02",
    # ---- S4: data marketplace expansion ----
    "GET /x402/v1/data/news": "$0.02",
    "GET /x402/v1/data/eth/balance": "$0.001",
    "GET /x402/v1/data/solana/balance": "$0.001",
    "GET /x402/v1/data/defi/yields": "$0.005",
    "GET /x402/v1/data/gas": "$0.001",
    # ---- S5: agent-native async jobs + batch embeds ----
    "POST /x402/v1/jobs": "$0.005",
    "POST /x402/v1/embeddings/batch": "$0.005",
}

# Route descriptions for x402 challenge
ROUTE_DESCRIPTIONS: dict[str, str] = {
    "POST /x402/v1/chat/completions": "OpenAI-compatible chat completions via CortexCloud AI gateway.",
    "POST /x402/v1/responses": "OpenAI-compatible chat completions (alias) via CortexCloud AI gateway.",
    "POST /x402/v1/embeddings": "OpenAI-compatible text embeddings via CortexCloud AI gateway - flat $0.005 per call regardless of batch size.",
    "GET /x402/v1/defillama/protocols": "All DeFi protocols with TVL (DeFiLlama).",
    "GET /x402/v1/crypto/price": "Crypto spot price, 24h change and market cap.",
    "GET /x402/v1/fx/price": "Latest fiat FX rate (ECB data).",
    "POST /x402/v1/images/generations": "AI image generation (Flux/Stability via OpenRouter) - pay per image in USDC.",
    "POST /x402/v1/audio/speech": "AI text-to-speech (OpenAI) - pay per call in USDC.",
    "POST /x402/v1/audio/transcriptions": "AI speech-to-text (Groq Whisper) - pay per call in USDC.",
    "POST /x402/v1/messages": "Anthropic-native Messages API via CortexCloud.",
    "POST /x402/v1/videos/generations": "AI text-to-video (xAI) - pay per clip in USDC.",
    "POST /x402/v1/search": "Web search via Exa AI - fixed price per query.",
    "POST /x402/v1/search/contents": "Fetch content for search result IDs via Exa AI - fixed price per fetch.",
}


def usd_to_usdc_atomic(price_str: str) -> str:
    """
    Converts a USD price string to USDC atomic units (string representing integer).
    USDC on Base has 6 decimals.
    Example: "$0.005" -> "5000"
             "$0.001" -> "1000"
    """
    val = price_str.lstrip('$')
    try:
        amount = float(val)
        atomic = int(amount * 1_000_000)
        return str(atomic)
    except ValueError:
        return "0"