"""
x402 payment-gated DATA marketplace endpoints (Phase B).

Keyless upstreams (no external API keys required):
  - CoinGecko  : token prices / market data
  - DEXScreener: DEX pairs / liquidity / price discovery

These are read-only proxies. The x402 middleware already gates them by path,
so callers must pay before the proxy runs. Responses are normalized to a
simple JSON shape agents can consume.

NOTE: all dynamic values are passed as QUERY params (never path params) so the
x402 middleware path-only pricing lookup matches exactly.

S4: CoinGecko responses cached 30s, DEXScreener 15s, keyed on the full URL
(query params included), with request coalescing — concurrent callers for the
same key share ONE upstream fetch.
"""
import logging
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.cache import cached_json
from app.core.http import shared_client

logger = logging.getLogger("cortexcloud.x402.data")

router = APIRouter()

CG_BASE = "https://api.coingecko.com/api/v3"
DEX_BASE = "https://api.dexscreener.com/latest/dex"

_HEADERS = {"Accept": "application/json", "User-Agent": "CortexCloud/1.0"}


async def _fetch(url: str) -> dict:
    """Shared pooled upstream fetch; raises RuntimeError on non-200."""
    c = shared_client("up:coingecko_dex", 12.0, _HEADERS)
    r = await c.get(url)
    if r.status_code != 200:
        raise RuntimeError(r.text[:300])
    return r.json()


def _cached(url: str, ttl: int):
    async def _inner():
        try:
            data, _ = await cached_json(f"x402:cache:{url}", ttl, lambda: _fetch(url))
            return JSONResponse(data)
        except RuntimeError as e:
            return JSONResponse(status_code=502, content={"error": "upstream", "detail": str(e)})
    return _inner


@router.get("/data/prices")
async def data_prices(
    ids: str = Query(..., description="Comma-separated CoinGecko coin ids, e.g. bitcoin,ethereum"),
    vs: str = Query("usd", description="Comma-separated vs currencies, e.g. usd,eur"),
):
    """Spot prices from CoinGecko. e.g. ?ids=bitcoin,ethereum&vs=usd. Cached 30s."""
    return await _cached(f"{CG_BASE}/simple/price?ids={ids}&vs_currencies={vs}", 30)()


@router.get("/data/coins/search")
async def data_coin_search(q: str = Query(..., description="Coin name or symbol to search")):
    """Search CoinGecko coins by name/symbol. Cached 30s."""
    return await _cached(f"{CG_BASE}/search?query={q}", 30)()


@router.get("/data/dex/search")
async def data_dex_search(q: str = Query(..., description="Token symbol or address to search, e.g. WETH")):
    """Search DEX pairs on DEXScreener by token/address. Cached 15s."""
    return await _cached(f"{DEX_BASE}/search?q={q}", 15)()


@router.get("/data/dex/pairs")
async def data_dex_pairs(
    chain: str = Query(..., description="Chain id, e.g. ethereum, base, solana"),
    pair: str = Query(..., description="Token address or pair address"),
):
    """Top DEX pairs for a token on a given chain. ?chain=ethereum&pair=0x... Cached 15s."""
    return await _cached(f"{DEX_BASE}/tokens/{chain}/{pair}", 15)()
