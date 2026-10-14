"""Aggregation API (Tier 1) — batch onchain data across addresses/tokens.

Endpoints (all paid):
  POST /v1/aggregate/balances    token balances summed across multiple addresses
  POST /v1/aggregate/prices      batch price lookup for multiple tokens
  POST /v1/aggregate/nfts        NFT ownership aggregated across addresses
  POST /v1/aggregate/tx-history  tx history combined across addresses

All paid routes inherit x402/MPP/rate-limit/validation/ledger from being
registered in app.x402.pricing.ROUTE_PRICING. This router reuses the same
Alchemy/CoinGecko plumbing as app.api.data -- never touches payments.
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
    data_price_usd,
    DEFAULT_CHAIN,
)

logger = logging.getLogger("cortexcloud.api.aggregate")

router = APIRouter(prefix="/v1/aggregate", tags=["Aggregation"])

ALCHEMY_BASE = "https://{network}.g.alchemy.com"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

_CACHES: dict[str, TTLCache] = {
    "aggregate-balances": TTLCache(15),
    "aggregate-prices": TTLCache(10),
    "aggregate-nfts": TTLCache(15),
    "aggregate-tx-history": TTLCache(15),
}


def _network(chain: str) -> str:
    net = DATA_CHAINS.get(str(chain).lower())
    if not net:
        raise ValueError(f"unsupported chain: {chain}")
    return net


def _cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


async def _alchemy_rpc(network: str, method: str, params: list) -> tuple[int, dict]:
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
    if r.status_code == 200 and isinstance(data, dict) and data.get("error"):
        return 502, data
    return r.status_code, data


async def _alchemy_nft(network: str, owner: str, page_size: int) -> tuple[int, dict]:
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


def _stamp(body: dict, endpoint: str, provider_cost: float) -> dict:
    price = data_price_usd(endpoint)
    body["price_usd"] = price
    body["provider_cost_usd"] = round(provider_cost, 8)
    body["margin_usd"] = round(price - provider_cost, 8)
    body["currency"] = "USDC"
    return body


def _cached_get(endpoint: str, key: str):
    return _CACHES[endpoint].get(key)


def _cached_set(endpoint: str, key: str, value: dict) -> None:
    _CACHES[endpoint].set(key, value)


def _disabled() -> JSONResponse | None:
    if not settings.DATA_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": "data_disabled", "detail": "Aggregation API not enabled"},
        )
    return None


def _need_alchemy() -> JSONResponse | None:
    if not settings.ALCHEMY_API_KEY:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unconfigured", "detail": "Alchemy API key not configured"},
        )
    return None


class AddressListRequest(BaseModel):
    addresses: list[str] = Field(min_length=1, max_length=20, description="EVM addresses (0x-prefixed).")
    chain: str = Field(default=DEFAULT_CHAIN)

    @field_validator("addresses")
    @classmethod
    def _addrs(cls, v):
        import re
        for addr in v:
            if not re.fullmatch(r"0x[0-9a-fA-F]{40}", addr):
                raise ValueError(f"invalid address: {addr}")
        return [a.lower() for a in v]


class TokenIdListRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=50, description="CoinGecko coin ids or contract addresses.")


class TxAggregateRequest(AddressListRequest):
    limit: int = Field(default=25, ge=1, le=100, description="Max transactions per address.")


@router.post("/balances")
async def aggregate_balances(req: AddressListRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})

    endpoint = "token-balances"
    provider_cost = data_price_usd(endpoint) * len(req.addresses)
    cache_key = _cache_key("agg-bal", network, ",".join(sorted(req.addresses)))
    hit = _cached_get("aggregate-balances", cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)

    all_balances: dict[str, dict] = {}
    for addr in req.addresses:
        status, data = await _alchemy_rpc(
            network, "alchemy_getTokenBalances",
            [addr, "DEFAULT_TOKENS", {"maxCount": 50}],
        )
        if status != 200:
            return JSONResponse(status_code=502, content={"error": "upstream_alchemy", "detail": json.dumps(data)[:500]})
        for b in data.get("result", {}).get("tokenBalances", []):
            contract = b.get("contractAddress", "").lower()
            if contract not in all_balances:
                all_balances[contract] = {
                    "contract": contract,
                    "addresses": [],
                    "token_decimals": b.get("tokenDecimals"),
                }
            all_balances[contract]["addresses"].append({"address": addr, "raw": b.get("tokenBalance")})

    out = {
        "chain": req.chain,
        "addresses_count": len(req.addresses),
        "token_count": len(all_balances),
        "balances": list(all_balances.values()),
        "cache_hit": False,
    }
    _cached_set("aggregate-balances", cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.post("/prices")
async def aggregate_prices(req: TokenIdListRequest, request: Request):
    if d := _disabled():
        return d

    endpoint = "token-price"
    provider_cost = data_price_usd(endpoint)
    cache_key = _cache_key("agg-price", ",".join(sorted(req.ids)))
    hit = _cached_get("aggregate-prices", cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)

    ids_str = ",".join(req.ids)
    url = f"{COINGECKO_BASE}/simple/price"
    params = {"ids": ids_str, "vs_currencies": "usd", "include_24hr_change": "true"}
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(url, params=params)
    try:
        prices = r.json() if r.content else {}
    except Exception:
        prices = {}

    results = []
    for tid in req.ids:
        p = prices.get(tid, {})
        results.append({"id": tid, "usd_price": p.get("usd"), "usd_24h_change": p.get("usd_24h_change")})

    out = {"count": len(results), "prices": results, "cache_hit": False}
    _cached_set("aggregate-prices", cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.post("/nfts")
async def aggregate_nfts(req: AddressListRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})

    endpoint = "nft-ownership"
    provider_cost = data_price_usd(endpoint) * len(req.addresses)
    cache_key = _cache_key("agg-nft", network, ",".join(sorted(req.addresses)))
    hit = _cached_get("aggregate-nfts", cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)

    all_nfts: dict[str, dict] = {}
    for addr in req.addresses:
        status, data = await _alchemy_nft(network, addr, 100)
        if status != 200:
            continue
        for nft in data.get("ownedNfts", []):
            key = f"{nft.get('contract', {}).get('address', '')}:{nft.get('tokenId', '')}"
            if key not in all_nfts:
                all_nfts[key] = {
                    "contract": nft.get("contract", {}).get("address", "").lower(),
                    "token_id": nft.get("tokenId"),
                    "name": nft.get("name"),
                    "owners": [],
                }
            all_nfts[key]["owners"].append(addr)

    out = {
        "chain": req.chain,
        "addresses_count": len(req.addresses),
        "nft_count": len(all_nfts),
        "nfts": list(all_nfts.values()),
        "cache_hit": False,
    }
    _cached_set("aggregate-nfts", cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.post("/tx-history")
async def aggregate_tx_history(req: TxAggregateRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})

    endpoint = "tx-history"
    provider_cost = data_price_usd(endpoint) * len(req.addresses)
    cache_key = _cache_key("agg-tx", network, ",".join(sorted(req.addresses)), str(req.limit))
    hit = _cached_get("aggregate-tx-history", cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)

    all_txs = []
    for addr in req.addresses:
        status, data = await _alchemy_rpc(
            network, "alchemy_getAssetTransfers",
            [{"fromAddress": addr, "maxCount": str(req.limit), "category": ["external", "erc20", "erc721", "erc1155"]}],
        )
        if status != 200:
            continue
        for tx in data.get("result", {}).get("transfers", []):
            tx["_from_address"] = addr
            all_txs.append(tx)

    out = {
        "chain": req.chain,
        "addresses_count": len(req.addresses),
        "tx_count": len(all_txs),
        "transactions": all_txs[:req.limit * len(req.addresses)],
        "cache_hit": False,
    }
    _cached_set("aggregate-tx-history", cache_key, out)
    return _stamp(out, endpoint, provider_cost)
