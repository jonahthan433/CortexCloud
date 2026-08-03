"""
x402 payment-gated MARKET DATA endpoints (Wave 1 — keyless public upstreams).

Mirrors the breadth of competing gateways (BlockRun) using FREE public APIs so
no external keys are required. All routes are read-only proxies; the x402
middleware gates them by path (see ROUTE_PRICING).

Upstreams (keyless):
  - DeFiLlama  : chains, protocols, TVL, token prices, yields
  - CoinGecko  : crypto spot + market history + coin list
  - Frankfurter: FX spot + history + currency list (ECB data)
  - Public RPC : Ethereum JSON-RPC (llamarpc)

NOTE: dynamic values are QUERY params (never path params) so the x402
middleware path-only pricing lookup matches exactly.
"""
import logging
import httpx
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger("cortexcloud.x402.market")

router = APIRouter()

DEFILLAMA = "https://api.llama.fi"
DEFILLAMA_COINS = "https://coins.llama.fi"
DEFILLAMA_YIELDS = "https://yields.llama.fi"
CG_BASE = "https://api.coingecko.com/api/v3"
FX_BASE = "https://open.er-api.com/v6"
ETH_RPC = "https://eth.llamarpc.com"

_HEADERS = {"Accept": "application/json", "User-Agent": "CortexCloud/1.0"}


async def _get(url: str, upstream: str, params: dict | None = None):
    async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS, follow_redirects=True) as c:
        r = await c.get(url, params=params)
        if r.status_code != 200:
            return JSONResponse(status_code=502, content={"error": f"upstream_{upstream}", "detail": r.text[:300]})
        return JSONResponse(r.json())


# ---------------- DeFiLlama ----------------
@router.get("/defillama/chains")
async def defillama_chains():
    """All chains with current TVL (DeFiLlama, free)."""
    return await _get(f"{DEFILLAMA}/v2/chains", "defillama")


@router.get("/defillama/protocols")
async def defillama_protocols():
    """All DeFi protocols with TVL (DeFiLlama, free)."""
    return await _get(f"{DEFILLAMA}/protocols", "defillama")


@router.get("/defillama/protocol")
async def defillama_protocol(slug: str = Query(..., description="Protocol slug, e.g. aave")):
    """Historical TVL for one protocol. ?slug=aave"""
    return await _get(f"{DEFILLAMA}/protocol/{slug}", "defillama")


@router.get("/defillama/prices")
async def defillama_prices(coins: str = Query(..., description="Comma list, e.g. ethereum:0x...,coingecko:bitcoin")):
    """Current token prices across chains (DeFiLlama). ?coins=coingecko:bitcoin"""
    return await _get(f"{DEFILLAMA_COINS}/prices/current/{coins}", "defillama")


@router.get("/defillama/yields")
async def defillama_yields():
    """All yield/APY pools (DeFiLlama, free)."""
    return await _get(f"{DEFILLAMA_YIELDS}/pools", "defillama")


# ---------------- Crypto (CoinGecko) ----------------
@router.get("/crypto/list")
async def crypto_list():
    """List all supported CoinGecko coins (id/symbol/name)."""
    return await _get(f"{CG_BASE}/coins/list", "coingecko")


@router.get("/crypto/price")
async def crypto_price(
    id: str = Query(..., description="CoinGecko coin id, e.g. bitcoin"),
    vs: str = Query("usd", description="vs currency, e.g. usd"),
):
    """Spot price + 24h change/mcap for a coin. ?id=bitcoin&vs=usd"""
    return await _get(
        f"{CG_BASE}/simple/price",
        "coingecko",
        params={"ids": id, "vs_currencies": vs, "include_24hr_change": "true", "include_market_cap": "true"},
    )


@router.get("/crypto/history")
async def crypto_history(
    id: str = Query(..., description="CoinGecko coin id, e.g. bitcoin"),
    vs: str = Query("usd", description="vs currency"),
    days: str = Query("30", description="Number of days of history, e.g. 30"),
):
    """OHLC/market-chart history for a coin. ?id=bitcoin&vs=usd&days=30"""
    return await _get(
        f"{CG_BASE}/coins/{id}/market_chart",
        "coingecko",
        params={"vs_currency": vs, "days": days},
    )


# ---------------- FX (Frankfurter / ECB) ----------------
@router.get("/fx/list")
async def fx_list():
    """List of supported currencies with latest rates vs EUR (open.er-api.com)."""
    return await _get(f"{FX_BASE}/latest/EUR", "er-api")


@router.get("/fx/price")
async def fx_price(
    base: str = Query("EUR", description="Base currency, e.g. EUR"),
    quote: str = Query("USD", description="Quote currency, e.g. USD"),
):
    """Latest FX rate. ?base=EUR&quote=USD -> returns {base,quote,rate,time_last_update_utc}."""
    async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS, follow_redirects=True) as c:
        r = await c.get(f"{FX_BASE}/latest/{base}")
        if r.status_code != 200:
            return JSONResponse(status_code=502, content={"error": "upstream_er-api", "detail": r.text[:300]})
        body = r.json()
    rate = body.get("rates", {}).get(quote)
    if rate is None:
        return JSONResponse(status_code=404, content={"error": "unknown_quote", "quote": quote})
    return JSONResponse({
        "base": base,
        "quote": quote,
        "rate": rate,
        "time_last_update_utc": body.get("time_last_update_utc"),
    })


@router.get("/fx/history")
async def fx_history(
    base: str = Query("EUR", description="Base currency"),
    quote: str = Query("USD", description="Quote currency"),
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
):
    """FX rate history over a date range. ?base=EUR&quote=USD&start=2025-01-01&end=2025-02-01"""
    return await _get(f"{FX_BASE}/history/{base}", "er-api", params={"start_date": start, "end_date": end})


# ---------------- Ethereum RPC ----------------
@router.post("/rpc/ethereum")
async def rpc_ethereum(payload: dict):
    """Proxy an Ethereum JSON-RPC call. Body = standard JSON-RPC request."""
    async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as c:
        r = await c.post(ETH_RPC, json=payload)
        if r.status_code != 200:
            return JSONResponse(status_code=502, content={"error": "upstream_ethrpc", "detail": r.text[:300]})
        return JSONResponse(r.json())
