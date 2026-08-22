"""Data API (Tier 1) — blockchain data via Alchemy (primary) + CoinGecko.

Six endpoints:
  POST /v1/data/token-balances
  POST /v1/data/token-price
  POST /v1/data/nft-ownership
  POST /v1/data/tx-history
  GET  /v1/data/gas-oracle
  GET  /v1/data/block

All paid routes inherit the full x402/MPP/rate-limit/validation/ledger stack
by being registered in app.x402.pricing.ROUTE_PRICING — this router only calls
the upstream provider and returns normalized JSON. It NEVER touches payments.

Provider economics are data, not logic: app.x402.pricing.{DATA_PROVIDERS,
data_provider_cost_usd, data_price_usd}. The charged price (and ledger margin)
auto-derive from the advertised Alchemy CU rate, so a provider reprice is a
one-line table edit, not a code change.

Caching: normalized, deterministic cache keys + endpoint-specific TTLs (price
10s, balances/nft/tx 15s, gas/block 5s). Built on the existing in-process
TTLCache (single-worker; the codebase dropped Redis — see app.core.cache).
No personalized/sensitive data is cached: cache keys include the wallet/address
so two users never share a cached balance.

Feature flag: DATA_ENABLED (default False). When off, every route 503s
honestly, exactly like AI/Research. Discovery still advertises the surface
(listing exists; capability marked unavailable until production validation).
"""
from __future__ import annotations

import hashlib
import json
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.core.cache import TTLCache
from app.core.config import settings
from app.x402.pricing import (
    DATA_CHAINS,
    DATA_PROVIDERS,
    DATA_TTL_S,
    data_provider_cost_usd,
    data_price_usd,
    DEFAULT_CHAIN,
)

logger = logging.getLogger("cortexcloud.api.data")

router = APIRouter(prefix="/v1/data", tags=["data"])

ALCHEMY_BASE = "https://{network}.g.alchemy.com"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
# ponytail: in-process cache (single worker). Swap to Redis by pointing TTLCache
# at a redis-backed store — same .get/.set API. No provider/route changes needed.
_CACHES: dict[str, TTLCache] = {ep: TTLCache(ttl_s) for ep, ttl_s in DATA_TTL_S.items()}


# ---------------------------------------------------------------------------
# Input models (trust-boundary validated before any settlement by the shared
# money-path guard; re-validated here too).
# ---------------------------------------------------------------------------
class AddressRequest(BaseModel):
    address: str = Field(description="EVM address (0x-prefixed, 40 hex).")
    chain: str = Field(default=DEFAULT_CHAIN, description="ethereum|base|arbitrum|polygon|optimism or chain id.")

    @field_validator("address")
    @classmethod
    def _addr(cls, v: str) -> str:
        if not isinstance(v, str) or not __import__("re").fullmatch(r"0x[0-9a-fA-F]{40}", v):
            raise ValueError("address must be a 0x-prefixed 40-hex EVM address")
        return v.lower()


class TokenBalancesRequest(AddressRequest):
    tokens: list[str] | None = Field(default=None, description="Optional ERC-20 contract list; omit for all tokens.")
    max_tokens: int = Field(default=50, ge=1, le=200, description="Cap on returned token entries.")

    @field_validator("tokens")
    @classmethod
    def _tokens(cls, v):
        if v is None:
            return v
        for t in v:
            if not __import__("re").fullmatch(r"0x[0-9a-fA-F]{40}", t):
                raise ValueError(f"invalid token contract: {t}")
        return [t.lower() for t in v]


class TokenPriceRequest(BaseModel):
    # CoinGecko free tier keyed by id (e.g. "ethereum", "usd-coin") or contract.
    id: str | None = Field(default=None, description="CoinGecko coin id, e.g. 'ethereum'.")
    contract: str | None = Field(default=None, description="ERC-20 contract address (with chain) for price-by-contract.")
    chain: str = Field(default=DEFAULT_CHAIN, description="Chain for contract-based price.")


class NFTOwnershipRequest(AddressRequest):
    page_size: int = Field(default=100, ge=1, le=100, description="NFTs per page.")


class TxHistoryRequest(AddressRequest):
    limit: int = Field(default=25, ge=1, le=100, description="Max transactions returned.")
    from_block: int | None = Field(default=None, description="Start block (inclusive).")


class GasOracleRequest(BaseModel):
    chain: str = Field(default=DEFAULT_CHAIN)


class BlockRequest(BaseModel):
    chain: str = Field(default=DEFAULT_CHAIN)
    block: str = Field(default="latest", description="Block number (decimal) or 'latest'.")


def _disabled() -> JSONResponse | None:
    if not settings.DATA_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": "data_disabled", "detail": "Data API not enabled on this instance (DATA_ENABLED=false)"},
        )
    return None


def _need_alchemy() -> JSONResponse | None:
    if not settings.ALCHEMY_API_KEY:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unconfigured", "detail": "Alchemy API key not configured on gateway"},
        )
    return None


def _network(chain: str) -> str:
    net = DATA_CHAINS.get(str(chain).lower())
    if not net:
        raise ValueError(f"unsupported chain: {chain}")
    return net


def _cache_key(*parts: str) -> str:
    """Normalized, deterministic cache key (no secrets, no personal bleed-over)."""
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def _cached_get(endpoint: str, key: str):
    return _CACHES[endpoint].get(key)


def _cached_set(endpoint: str, key: str, value: dict) -> None:
    _CACHES[endpoint].set(key, value)


def _stamp(body: dict, endpoint: str, provider_cost: float) -> dict:
    """Attach pricing/cost metadata the client and ledger need."""
    price = data_price_usd(endpoint)
    body["price_usd"] = price
    body["provider_cost_usd"] = round(provider_cost, 8)
    body["margin_usd"] = round(price - provider_cost, 8)
    body["currency"] = "USDC"
    return body


async def _alchemy_nft(network: str, owner: str, page_size: int) -> tuple[int, dict]:
    """Alchemy NFT API is REST (not /v2 JSON-RPC). Bearer auth."""
    url = f"{ALCHEMY_BASE.format(network=network)}/nft/v3/getNFTsForOwner"
    params = {"owner": owner, "pageSize": page_size, "withMetadata": "true"}
    headers = {"Authorization": f"Bearer {settings.ALCHEMY_API_KEY}"}
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(url, params=params, headers=headers)
    try:
        data = r.json() if r.content else {}
    except Exception:
        data = {}
    if r.status_code == 200 and isinstance(data, dict) and data.get("error"):
        return 502, data
    return r.status_code, data


async def _alchemy_rpc(network: str, method: str, params: list) -> tuple[int, dict]:
    """Alchemy Enhanced/JSON-RPC APIs are POSTed to /v2 as {"method","params"}.
    Authenticated via Authorization: Bearer <key> header."""
    url = f"{ALCHEMY_BASE.format(network=network)}/v2"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    headers = {
        "Authorization": f"Bearer {settings.ALCHEMY_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(url, json=body, headers=headers)
    try:
        data = r.json() if r.content else {}
    except Exception:
        data = {}
    # JSON-RPC errors come back as HTTP 200 with {"error": {...}}
    if r.status_code == 200 and isinstance(data, dict) and data.get("error"):
        return 502, data
    return r.status_code, data


# ---------------------------------------------------------------------------
# Routes (each: gate -> cache -> upstream -> normalize -> stamp)
# ---------------------------------------------------------------------------
@router.post("/token-balances")
async def token_balances(req: TokenBalancesRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
    endpoint = "token-balances"
    calls = max(1, len(req.tokens) if req.tokens else 1)
    provider_cost = data_provider_cost_usd(endpoint, calls)
    cache_key = _cache_key(endpoint, network, req.address, ",".join(sorted(req.tokens or [])) or "all", str(req.max_tokens))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)
    # Alchemy Token Balances (plural) endpoint
    status, data = await _alchemy_rpc(
        network, "alchemy_getTokenBalances",
        [req.address, req.tokens if req.tokens else "DEFAULT_TOKENS", {"maxCount": req.max_tokens}],
    )
    if status != 200:
        return JSONResponse(status_code=status or 502, content={"error": "upstream_alchemy", "detail": json.dumps(data)[:500]})
    balances = data.get("result", {}).get("tokenBalances", [])
    # Normalize: Alchemy returns hex tokenBalances; convert to decimal strings.
    out = {
        "address": req.address,
        "chain": req.chain,
        "token_count": len(balances),
        "balances": [
            {
                "contract": b.get("contractAddress", "").lower(),
                "raw": b.get("tokenBalance"),
                "token_decimals": b.get("tokenDecimals"),
            }
            for b in balances
        ],
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.post("/token-price")
async def token_price(req: TokenPriceRequest, request: Request):
    if d := _disabled():
        return d
    endpoint = "token-price"
    provider_cost = data_provider_cost_usd(endpoint)
    cache_key = _cache_key(endpoint, str(req.id or ""), str(req.contract or ""), req.chain)
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)
    # CoinGecko free tier first (where it suffices).
    if req.id:
        url = f"{COINGECKO_BASE}/simple/price"
        params = {"ids": req.id, "vs_currencies": "usd", "include_24hr_change": "true"}
        if settings.COINGECKO_API_KEY:
            params["x_cg_demo_api_key"] = settings.COINGECKO_API_KEY
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(url, params=params)
        if r.status_code == 200:
            j = r.json()
            price = (j.get(req.id) or {}).get("usd")
            if price is not None:
                out = {"id": req.id, "usd": price,
                       "change_24h_usd": (j.get(req.id) or {}).get("usd_24h_change"),
                       "provider": "coingecko", "cache_hit": False}
                _cached_set(endpoint, cache_key, out)
                return _stamp(out, endpoint, provider_cost)
        # fall through to Alchemy if CoinGecko misses
    if req.contract:
        try:
            network = _network(req.chain)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
        if e := _need_alchemy():
            return e
        status, data = await _alchemy_rpc(
            network, "alchemy_getTokenMetadata", [{"address": req.contract.lower()}]
        )
        if status == 200 and data.get("result"):
            res = data["result"]
            out = {"contract": req.contract.lower(), "chain": req.chain,
                   "symbol": res.get("symbol"), "name": res.get("name"),
                   "decimals": res.get("decimals"), "provider": "alchemy", "cache_hit": False}
            _cached_set(endpoint, cache_key, out)
            return _stamp(out, endpoint, provider_cost)
        return JSONResponse(status_code=status or 502, content={"error": "upstream", "detail": json.dumps(data)[:500]})
    return JSONResponse(status_code=400, content={"error": "bad_request", "detail": "provide 'id' or 'contract'"})


@router.post("/nft-ownership")
async def nft_ownership(req: NFTOwnershipRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
    endpoint = "nft-ownership"
    provider_cost = data_provider_cost_usd(endpoint)
    cache_key = _cache_key(endpoint, network, req.address, str(req.page_size))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)
    status, data = await _alchemy_nft(network, req.address, req.page_size)
    if status != 200:
        return JSONResponse(status_code=status or 502, content={"error": "upstream_alchemy", "detail": json.dumps(data)[:500]})
    owned = data.get("ownedNfts", [])
    out = {
        "address": req.address,
        "chain": req.chain,
        "total_count": data.get("totalCount"),
        "nfts": [
            {"contract": (n.get("contractAddress") or "").lower(),
             "token_id": n.get("tokenId"),
             "name": (n.get("name") or (n.get("metadata") or {}).get("name")),
             "collection": (n.get("collection") or {}).get("name")}
            for n in owned
        ],
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.post("/tx-history")
async def tx_history(req: TxHistoryRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
    endpoint = "tx-history"
    provider_cost = data_provider_cost_usd(endpoint)
    cache_key = _cache_key(endpoint, network, req.address, str(req.limit), str(req.from_block or "latest"))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)
    params = [{
        "fromAddress": req.address,
        "maxCount": str(req.limit),
        "category": ["external", "erc20", "erc721", "erc1155"],
    }]
    if req.from_block is not None:
        params[0]["fromBlock"] = str(req.from_block)
    status, data = await _alchemy_rpc(network, "alchemy_getAssetTransfers", params)
    if status != 200:
        return JSONResponse(status_code=status or 502, content={"error": "upstream_alchemy", "detail": json.dumps(data)[:500]})
    txs = data.get("result", {}).get("transfers", [])
    out = {
        "address": req.address,
        "chain": req.chain,
        "count": len(txs),
        "transactions": [
            {"hash": t.get("hash"), "from": (t.get("from") or "").lower(), "to": (t.get("to") or "").lower(),
             "value": t.get("value"), "asset": t.get("asset"), "category": t.get("category"),
             "block_num": t.get("blockNum"), "timestamp": t.get("metadata", {}).get("blockTimestamp")}
            for t in txs
        ],
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.get("/gas-oracle")
async def gas_oracle(chain: str = DEFAULT_CHAIN):
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
    endpoint = "gas-oracle"
    provider_cost = data_provider_cost_usd(endpoint)
    cache_key = _cache_key(endpoint, network)
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)
    status, data = await _alchemy_rpc(network, "eth_gasPrice", [])
    if status != 200:
        return JSONResponse(status_code=status or 502, content={"error": "upstream_alchemy", "detail": json.dumps(data)[:500]})
    res = data.get("result")
    out = {
        "chain": chain,
        "base_fee_gwei": res,
        "priority_fee_gwei": None,
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.get("/block")
async def block(chain: str = DEFAULT_CHAIN, block: str = "latest"):
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
    endpoint = "block"
    provider_cost = data_provider_cost_usd(endpoint)
    cache_key = _cache_key(endpoint, network, str(block))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)
    status, data = await _alchemy_rpc(network, "eth_getBlockByNumber", [str(block), False])
    if status != 200:
        return JSONResponse(status_code=status or 502, content={"error": "upstream_alchemy", "detail": json.dumps(data)[:500]})
    res = data.get("result", {})
    out = {
        "chain": chain,
        "number": res.get("number"),
        "hash": res.get("hash"),
        "timestamp": res.get("timestamp"),
        "tx_count": len(res.get("transactions", [])),
        "parent_hash": res.get("parentHash"),
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)
