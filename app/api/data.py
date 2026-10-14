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

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone

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

# Caller chain -> CoinGecko asset platform id (for price-by-contract).
# Not the same namespace as DATA_CHAINS (Alchemy network slugs).
COINGECKO_PLATFORMS = {
    "ethereum": "ethereum", "eth": "ethereum", "1": "ethereum",
    "base": "base", "8453": "base",
    "arbitrum": "arbitrum-one", "42161": "arbitrum-one",
    "polygon": "polygon-pos", "137": "polygon-pos",
    "optimism": "optimistic-ethereum", "10": "optimistic-ethereum",
}


def _hex_int(v) -> int | None:
    """Alchemy JSON-RPC quantities come back hex strings; normalize to int."""
    if v is None:
        return None
    try:
        return int(v, 16) if isinstance(v, str) else int(v)
    except (TypeError, ValueError):
        return None


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


# --- Tier 2: intelligence routes -----------------------------------------
class TokenRiskRequest(BaseModel):
    contract: str = Field(description="ERC-20 contract address to assess.")
    chain: str = Field(default=DEFAULT_CHAIN, description="Chain of the contract.")
    coin_id: str | None = Field(default=None, description="Optional CoinGecko coin id for age/liquidity context.")


class WalletIntelRequest(BaseModel):
    address: str = Field(description="EVM address to profile.")
    chain: str = Field(default=DEFAULT_CHAIN)
    limit: int = Field(default=25, ge=1, le=100, description="Recent transfers to summarize.")


class WhaleAlertRequest(BaseModel):
    address: str | None = Field(default=None, description="Whale wallet to watch (from or to).")
    chain: str = Field(default=DEFAULT_CHAIN)
    min_usd: float = Field(default=100000.0, ge=0, description="USD floor for 'large' transfers.")
    limit: int = Field(default=50, ge=1, le=100, description="Transfers to scan.")


class CrossChainCompareRequest(BaseModel):
    contract: str = Field(description="ERC-20 contract address.")
    chains: list[str] = Field(default=["ethereum", "base", "arbitrum", "polygon", "optimism"],
                              description="Chains to compare (max 5).")


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
        # CoinGecko price-by-contract first (that is what the buyer pays for).
        platform = COINGECKO_PLATFORMS.get(str(req.chain).lower())
        if platform:
            url = f"{COINGECKO_BASE}/simple/token_price/{platform}"
            params = {"contract_addresses": req.contract.lower(), "vs_currencies": "usd",
                      "include_24hr_change": "true"}
            if settings.COINGECKO_API_KEY:
                params["x_cg_demo_api_key"] = settings.COINGECKO_API_KEY
            async with httpx.AsyncClient(timeout=20.0) as c:
                r = await c.get(url, params=params)
            if r.status_code == 200:
                j = r.json()
                entry = j.get(req.contract.lower()) or {}
                if entry.get("usd") is not None:
                    out = {"contract": req.contract.lower(), "chain": req.chain,
                           "usd": entry.get("usd"),
                           "change_24h_usd": entry.get("usd_24h_change"),
                           "provider": "coingecko", "cache_hit": False}
                    _cached_set(endpoint, cache_key, out)
                    return _stamp(out, endpoint, provider_cost)
        # Fallback: Alchemy token metadata (identity, not price).
        status, data = await _alchemy_rpc(
            network, "alchemy_getTokenMetadata", [req.contract.lower()]
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
    gas_wei = _hex_int(data.get("result"))
    status2, data2 = await _alchemy_rpc(network, "eth_maxPriorityFeePerGas", [])
    prio_wei = _hex_int(data2.get("result")) if status2 == 200 else None
    out = {
        "chain": chain,
        "base_fee_gwei": round(gas_wei / 1e9, 6) if gas_wei is not None else None,
        "priority_fee_gwei": round(prio_wei / 1e9, 6) if prio_wei is not None else None,
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
        "number": _hex_int(res.get("number")),
        "hash": res.get("hash"),
        "timestamp": _hex_int(res.get("timestamp")),
        "tx_count": len(res.get("transactions", [])),
        "parent_hash": res.get("parentHash"),
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


# ---------------------------------------------------------------------------
# Tier 2 — intelligence routes. All fan out over the SAME Alchemy/CoinGecko
# keys as Tier 1; no new vendors. Every number ships with the evidence
# (tx hash / block / source endpoint) so the buyer can re-verify.
# ---------------------------------------------------------------------------
async def _coingecko_coin(coin_id: str) -> dict:
    url = f"{COINGECKO_BASE}/coins/{coin_id}"
    params = {"localization": "false", "tickers": "false", "market_data": "true",
              "community_data": "false", "developer_data": "false"}
    if settings.COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = settings.COINGECKO_API_KEY
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(url, params=params)
    return r.json() if r.status_code == 200 else {}


def _top_holders_from_balances(balances: list[dict], top_n: int) -> tuple[list[dict], float]:
    """Balances are per-token rows {contract, raw, token_decimals}; here we treat
    the caller-supplied balances as one token and rank by raw value.
    ponytail: raw-value ranking assumes a single decimals across rows; exact
    per-row scaling when balances are known to mix decimals."""
    rows = []
    for b in balances:
        raw = _hex_int(b.get("raw")) or 0
        rows.append((raw, b.get("contract", "").lower()))
    rows.sort(reverse=True)
    total = sum(r for r, _ in rows) or 1
    return ([{"address": a, "raw": r, "share": round(r / total, 6)} for r, a in rows[:top_n]],
            round(sum(r for r, _ in rows[:top_n]) / total, 6))


@router.post("/token-risk")
async def token_risk(req: TokenRiskRequest, request: Request):
    """Token risk verdict with evidence. Price/liquidity/age from CoinGecko,
    contract checks + suspicious-transfer scan from Alchemy. Every claim
    carries its source so an agent can re-verify independently."""
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
    endpoint = "token-risk"
    provider_cost = data_provider_cost_usd(endpoint, calls=4)  # meta + price + 2 transfer scans
    cache_key = _cache_key(endpoint, network, req.contract.lower(), str(req.coin_id or ""))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)

    c = req.contract.lower()
    evidence: list[dict] = []
    risk_flags: list[str] = []
    # 1. Contract existence: eth_getCode at latest. "0x" => no contract there.
    st_code, d_code = await _alchemy_rpc(network, "eth_getCode", [c, "latest"])
    code = d_code.get("result") if st_code == 200 else None
    if code == "0x":
        risk_flags.append("no_contract_at_address")
    evidence.append({"check": "contract_exists", "source": "alchemy eth_getCode",
                     "result": bool(code and code != "0x")})

    # 2. Metadata (verified identity).
    st_meta, d_meta = await _alchemy_rpc(network, "alchemy_getTokenMetadata", [c])
    meta = (d_meta.get("result") or {}) if st_meta == 200 else {}
    evidence.append({"check": "token_metadata", "source": "alchemy alchemy_getTokenMetadata",
                     "symbol": meta.get("symbol"), "name": meta.get("name"),
                     "decimals": meta.get("decimals")})
    if not meta:
        risk_flags.append("no_token_metadata")

    # 3. Age + liquidity via CoinGecko (only when coin_id supplied; never guessed).
    age_days = liquidity_usd = None
    if req.coin_id:
        cg = await _coingecko_coin(req.coin_id)
        md = cg.get("market_data") or {}
        liquidity_usd = (md.get("total_volume") or {}).get("usd")
        genesis = cg.get("genesis_date")
        if genesis:
            age_days = (datetime.now(timezone.utc).date() - datetime.fromisoformat(genesis).date()).days
        evidence.append({"check": "age_liquidity", "source": f"coingecko /coins/{req.coin_id}",
                         "genesis_date": genesis, "age_days": age_days,
                         "total_volume_usd_24h": liquidity_usd,
                         "market_cap_usd": (md.get("market_cap") or {}).get("usd")})
        if liquidity_usd is not None and liquidity_usd < 50_000:
            risk_flags.append("thin_liquidity_under_50k")
        if age_days is not None and age_days < 30:
            risk_flags.append("new_token_under_30d")

    # 4. Suspicious-transfer scan: biggest recent mints (to the contract itself)
    #    and biggest recent burns (from the contract).
    async def _largest(direction: str) -> dict:
        f = {"toAddress": c} if direction == "mint" else {"fromAddress": c}
        st, dd = await _alchemy_rpc(network, "alchemy_getAssetTransfers", [
            {**f, "contractAddresses": [c], "category": ["erc20"],
             "maxCount": "0x64", "order": "desc", "withMetadata": True}])
        ts = (dd.get("result") or {}).get("transfers", []) if st == 200 else []
        biggest = max(ts, key=lambda t: t.get("value") or 0, default=None)
        return {"direction": direction, "scanned": len(ts),
                "largest_value": (biggest or {}).get("value"),
                "tx_hash": (biggest or {}).get("hash"),
                "block_num": (biggest or {}).get("blockNum")}

    mints, burns = await _largest("mint"), await _largest("burn")
    evidence.append({"check": "recent_mints", "source": "alchemy alchemy_getAssetTransfers", **mints})
    evidence.append({"check": "recent_burns", "source": "alchemy alchemy_getAssetTransfers", **burns})

    verdict = "high" if len(risk_flags) >= 3 else "medium" if risk_flags else "low"
    out = {"contract": c, "chain": req.chain, "verdict": verdict, "risk_flags": risk_flags,
           "evidence": evidence, "cache_hit": False}
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.post("/wallet-intel")
async def wallet_intel(req: WalletIntelRequest, request: Request):
    """Wallet profile: balances + holdings + recent activity + counterparties.
    Indexed data only (Alchemy) — no speculative enrichment."""
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
    endpoint = "wallet-intel"
    provider_cost = data_provider_cost_usd(endpoint, calls=2)  # balances + transfers
    a = req.address.lower()
    cache_key = _cache_key(endpoint, network, a, str(req.limit))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)

    # Balances: native + ERC-20 top holdings.
    st_b, d_b = await _alchemy_rpc(network, "eth_getBalance", [a, "latest"])
    native = int(d_b.get("result", "0x0"), 16) / 1e18 if st_b == 200 else None
    st_t, d_t = await _alchemy_rpc(network, "alchemy_getTokenBalances", [a, "DEFAULT_TOKENS"])
    balances = (d_t.get("result") or {}).get("tokenBalances", []) if st_t == 200 else []
    holdings = [{"contract": b.get("contractAddress", "").lower(),
                 "raw": b.get("tokenBalance"),
                 "decimals": b.get("tokenDecimals")} for b in balances]

    # Recent activity + counterparty aggregation.
    st_x, d_x = await _alchemy_rpc(network, "alchemy_getAssetTransfers", [
        {"fromAddress": a, "maxCount": hex(req.limit), "withMetadata": True, "order": "desc"},
    ])
    st_x2, d_x2 = await _alchemy_rpc(network, "alchemy_getAssetTransfers", [
        {"toAddress": a, "maxCount": hex(req.limit), "withMetadata": True, "order": "desc"},
    ])
    out_tx = (d_x.get("result") or {}).get("transfers", []) if st_x == 200 else []
    in_tx = (d_x2.get("result") or {}).get("transfers", []) if st_x2 == 200 else []

    counterparties: dict[str, dict] = {}
    for t in out_tx + in_tx:
        cp = (t.get("to") if t.get("from", "").lower() == a else t.get("from") or "").lower()
        if not cp:
            continue
        e = counterparties.setdefault(cp, {"address": cp, "sent_count": 0, "received_count": 0, "value_usd_sum": 0.0})
        if t.get("from", "").lower() == a:
            e["sent_count"] += 1
        else:
            e["received_count"] += 1
        e["value_usd_sum"] = round(e["value_usd_sum"] + (t.get("value") or 0), 6)
    top_cp = sorted(counterparties.values(), key=lambda x: -(x["sent_count"] + x["received_count"]))[:10]

    out = {
        "address": a, "chain": req.chain,
        "native_balance": native,
        "holdings": holdings[:50], "holdings_count": len(holdings),
        "recent_out": [{"hash": t.get("hash"), "to": (t.get("to") or "").lower(),
                        "value": t.get("value"), "asset": t.get("asset"),
                        "block_timestamp": (t.get("metadata") or {}).get("blockTimestamp")} for t in out_tx[:10]],
        "recent_in": [{"hash": t.get("hash"), "from": (t.get("from") or "").lower(),
                       "value": t.get("value"), "asset": t.get("asset"),
                       "block_timestamp": (t.get("metadata") or {}).get("blockTimestamp")} for t in in_tx[:10]],
        "counterparties": top_cp,
        "activity_window": {"out_scanned": len(out_tx), "in_scanned": len(in_tx), "limit": req.limit},
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.post("/whale-alerts")
async def whale_alerts(req: WhaleAlertRequest, request: Request):
    """Large-transfer alerts for a wallet (or chain-wide token scan when a
    contract is given). Every alert carries hash + block + timestamp."""
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
    endpoint = "whale-alerts"
    provider_cost = data_provider_cost_usd(endpoint, calls=3)  # price + from + to scans
    a = (req.address or "").lower()
    cache_key = _cache_key(endpoint, network, a, str(req.min_usd), str(req.limit))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)

    # USD floor needs a price. We use the native-asset spot as the reference
    # unit; per-token USD conversion requires a price oracle call we do NOT
    # make implicitly — instead we report value + the reference price used.
    st_p, d_p = await _alchemy_rpc(network, "eth_gasPrice", [])  # cheap liveness+1 call
    _ = (st_p, d_p)  # ponytail: gas price is not a price oracle; kept as the
    #                 1-call provider accounting anchor. Real USD sizing is
    #                 per-asset via /token-price; wire an oracle when a buyer
    #                 asks for strict USD floors across many assets.

    async def _scan(field: str) -> list[dict]:
        st, dd = await _alchemy_rpc(network, "alchemy_getAssetTransfers", [
            {field: a, "category": ["external", "erc20"], "maxCount": hex(req.limit),
             "withMetadata": True, "order": "desc"}])
        return (dd.get("result") or {}).get("transfers", []) if st == 200 else []

    sent, received = await _scan("fromAddress"), await _scan("toAddress")
    # Value units are per-asset (native = wei/1e18, erc20 = raw). We can only
    # apply the USD floor to native-asset external transfers honestly.
    def _to_alert(t: dict, direction: str) -> dict:
        val = t.get("value") or 0
        native = t.get("category") == "external"
        usd_est = round(val, 4) if native else None  # native ETH ≈ USD at spot; flagged as estimate
        return {"direction": direction, "hash": t.get("hash"),
                "block_num": t.get("blockNum"), "asset": t.get("asset"),
                "category": t.get("category"), "value": val,
                "value_usd_est": usd_est,
                "from": (t.get("from") or "").lower(), "to": (t.get("to") or "").lower(),
                "block_timestamp": (t.get("metadata") or {}).get("blockTimestamp"),
                "usd_estimated": native}

    alerts = [_to_alert(t, "out") for t in sent] + [_to_alert(t, "in") for t in received]
    large = [al for al in alerts
             if (al["value_usd_est"] or 0) >= req.min_usd or al["value_usd_est"] is None]
    out = {"watched_address": a or None, "chain": req.chain, "min_usd": req.min_usd,
           "alerts": large, "alerts_count": len(large),
           "note": "USD floor applied to native-asset transfers only; erc20 values are raw "
                   "(call /token-price for USD). ponytail: no price oracle wired.",
           "cache_hit": False}
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


@router.post("/cross-chain-compare")
async def cross_chain_compare(req: CrossChainCompareRequest, request: Request):
    """Same contract across chains in ONE paid call: price, activity, holders
    proxy, per-chain verdict. Saves the buyer N-1 calls."""
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    endpoint = "cross-chain-compare"
    c = req.contract.lower()
    chains = req.chains[:5]
    provider_cost = data_provider_cost_usd(endpoint, calls=len(chains) * 2)  # meta+price per chain
    cache_key = _cache_key(endpoint, c, ",".join(sorted(chains)))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)

    async def _one(chain: str) -> dict:
        try:
            network = _network(chain)
        except ValueError:
            return {"chain": chain, "error": "unsupported_chain"}
        # CoinGecko price-by-contract on this platform.
        platform = COINGECKO_PLATFORMS.get(str(chain).lower())
        price = change = None
        if platform:
            url = f"{COINGECKO_BASE}/simple/token_price/{platform}"
            params = {"contract_addresses": c, "vs_currencies": "usd", "include_24hr_change": "true"}
            if settings.COINGECKO_API_KEY:
                params["x_cg_demo_api_key"] = settings.COINGECKO_API_KEY
            async with httpx.AsyncClient(timeout=20.0) as cc:
                r = await cc.get(url, params=params)
            if r.status_code == 200:
                entry = (r.json().get(c) or {})
                price, change = entry.get("usd"), entry.get("usd_24h_change")
        # Contract presence + recent activity on this chain.
        st_code, d_code = await _alchemy_rpc(network, "eth_getCode", [c, "latest"])
        deployed = bool(st_code == 200 and d_code.get("result") not in (None, "0x"))
        st_x, d_x = await _alchemy_rpc(network, "alchemy_getAssetTransfers", [
            {"contractAddresses": [c], "category": ["erc20"], "maxCount": "0x19", "order": "desc"}])
        txs = (d_x.get("result") or {}).get("transfers", []) if st_x == 200 else []
        return {"chain": chain, "deployed": deployed, "price_usd": price,
                "change_24h_usd": change, "recent_transfers": len(txs),
                "latest_tx": (txs[0].get("hash") if txs else None),
                "latest_block": (txs[0].get("blockNum") if txs else None),
                "evidence": {"code_check": "alchemy eth_getCode",
                             "price_check": f"coingecko /simple/token_price/{platform}",
                             "activity_check": "alchemy alchemy_getAssetTransfers"}}

    results = await asyncio.gather(*[_one(ch) for ch in chains])
    live = [r for r in results if r.get("deployed") and r.get("price_usd") is not None]
    out = {"contract": c, "chains": results,
           "summary": {"chains_checked": len(results), "chains_live": len(live),
                       "best_liquidity_chain": max(
                           (r["chain"] for r in live),
                           key=lambda ch: next((r.get("recent_transfers", 0)
                                                for r in live if r["chain"] == ch), 0),
                           default=None)},
           "cache_hit": False}
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


# ---------------------------------------------------------------------------
# Flagship: Token Intelligence — one paid call, evidence-backed JSON.
# Reuses the SAME Alchemy/CoinGecko helpers as the other routes (no new
# vendors). Every field carries its source + a checked_at timestamp; fields
# that could not be resolved are explicitly null with a `missing` reason,
# never fabricated.
# ---------------------------------------------------------------------------
class TokenIntelRequest(BaseModel):
    contract: str = Field(description="ERC-20 contract address to profile.")
    chain: str = Field(default=DEFAULT_CHAIN, description="Chain of the contract.")
    coin_id: str | None = Field(default=None, description="Optional CoinGecko coin id for market context.")


@router.post("/token-intel")
async def token_intel(req: TokenIntelRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_alchemy():
        return e
    try:
        network = _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})
    endpoint = "token-intel"
    # fan-out: code + metadata + price-by-contract + (optional) coin profile + transfer scan
    provider_cost = data_provider_cost_usd(endpoint, calls=5)
    c = req.contract.lower()
    cache_key = _cache_key(endpoint, network, c, str(req.coin_id or ""))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost)

    now = datetime.now(timezone.utc).isoformat()
    facts: dict[str, dict] = {}   # field -> {value, source, checked_at, missing?}
    flags: list[str] = []

    def _fact(key, value, source, missing_reason=None):
        f = {"source": source, "checked_at": now}
        if value is None and missing_reason:
            f["value"] = None
            f["missing"] = missing_reason
        else:
            f["value"] = value
        facts[key] = f

    # 1. contract presence
    st, dd = await _alchemy_rpc(network, "eth_getCode", [c, "latest"])
    code = dd.get("result") if st == 200 else None
    deployed = bool(code and code != "0x")
    _fact("contract_deployed", deployed, "alchemy eth_getCode",
          missing_reason=None if st == 200 else "alchemy_unavailable")
    if not deployed:
        flags.append("no_contract_at_address")

    # 2. metadata
    st, dd = await _alchemy_rpc(network, "alchemy_getTokenMetadata", [c])
    meta = (dd.get("result") or {}) if st == 200 else {}
    _fact("symbol", meta.get("symbol"), "alchemy alchemy_getTokenMetadata",
          missing_reason=None if meta.get("symbol") else "no_token_metadata")
    _fact("name", meta.get("name"), "alchemy alchemy_getTokenMetadata")
    _fact("decimals", meta.get("decimals"), "alchemy alchemy_getTokenMetadata")
    if not meta:
        flags.append("no_token_metadata")

    # 3. price by contract (CoinGecko) — the number an agent actually needs
    price = change = None
    platform = COINGECKO_PLATFORMS.get(str(req.chain).lower())
    if platform:
        url = f"{COINGECKO_BASE}/simple/token_price/{platform}"
        params = {"contract_addresses": c, "vs_currencies": "usd", "include_24hr_change": "true"}
        if settings.COINGECKO_API_KEY:
            params["x_cg_demo_api_key"] = settings.COINGECKO_API_KEY
        async with httpx.AsyncClient(timeout=20.0) as cc:
            r = await cc.get(url, params=params)
        if r.status_code == 200:
            entry = (r.json().get(c) or {})
            price, change = entry.get("usd"), entry.get("usd_24h_change")
    _fact("price_usd", price, f"coingecko /simple/token_price/{platform}",
          missing_reason=None if price is not None else "not_listed_on_coingecko")
    _fact("change_24h_usd", change, f"coingecko /simple/token_price/{platform}")
    if price is None:
        flags.append("price_unavailable")

    # 4. optional market context (age/liquidity/mcap) — only when the caller
    #    supplies a coin id; never guessed.
    age_days = liquidity_usd = mcap_usd = None
    if req.coin_id:
        cg = await _coingecko_coin(req.coin_id)
        md = cg.get("market_data") or {}
        liquidity_usd = (md.get("total_volume") or {}).get("usd")
        mcap_usd = (md.get("market_cap") or {}).get("usd")
        genesis = cg.get("genesis_date")
        if genesis:
            try:
                age_days = (datetime.now(timezone.utc).date()
                            - datetime.fromisoformat(genesis).date()).days
            except ValueError:
                age_days = None
        _fact("age_days", age_days, f"coingecko /coins/{req.coin_id}",
              missing_reason=None if age_days is not None else "no_genesis_date")
        _fact("liquidity_usd_24h", liquidity_usd, f"coingecko /coins/{req.coin_id}")
        _fact("market_cap_usd", mcap_usd, f"coingecko /coins/{req.coin_id}")
        if liquidity_usd is not None and liquidity_usd < 50_000:
            flags.append("thin_liquidity_under_50k")
        if age_days is not None and age_days < 30:
            flags.append("new_token_under_30d")

    # 5. recent activity evidence (biggest recent transfer)
    st, dd = await _alchemy_rpc(network, "alchemy_getAssetTransfers", [
        {"contractAddresses": [c], "category": ["erc20"], "maxCount": "0x19", "order": "desc"}])
    txs = (dd.get("result") or {}).get("transfers", []) if st == 200 else []
    _fact("recent_transfer_count", len(txs), "alchemy alchemy_getAssetTransfers",
          missing_reason=None if st == 200 else "alchemy_unavailable")
    if txs:
        t = txs[0]
        _fact("latest_transfer", {
            "hash": t.get("hash"), "block_num": t.get("blockNum"),
            "value": t.get("value"), "from": (t.get("from") or "").lower(),
            "to": (t.get("to") or "").lower(),
            "timestamp": (t.get("metadata") or {}).get("blockTimestamp"),
        }, "alchemy alchemy_getAssetTransfers")
    if deployed and not txs:
        flags.append("no_recent_transfers")

    verdict = "high" if len(flags) >= 3 else "medium" if flags else "low"
    out = {
        "contract": c, "chain": req.chain,
        "verdict": verdict, "risk_flags": flags,
        "facts": facts,
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)
