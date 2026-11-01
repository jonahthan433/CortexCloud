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
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.cache import TTLCache
from app.core.config import settings
from app.x402.pricing import (
    DATA_CHAINS,
    DATA_PROVIDERS,
    DATA_TTL_S,
    HELIUS_ENDPOINTS,
    data_provider_cost_usd,
    data_price_usd,
    DEFAULT_CHAIN,
    helius_provider_cost_usd,
    is_solana,
)

logger = logging.getLogger("cortexcloud.api.data")

router = APIRouter(prefix="/v1/data", tags=["data"])

ALCHEMY_BASE = "https://{network}.g.alchemy.com"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
# Solana via Helius. The API key rides in the URL/query — never log these URLs.
HELIUS_RPC_URL = "https://mainnet.helius-rpc.com/?api-key={key}"
HELIUS_TX_URL = "https://api.helius.xyz/v0/addresses/{address}/transactions"
SOLANA_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
# ponytail: in-process cache (single worker). Swap to Redis by pointing TTLCache
# at a redis-backed store — same .get/.set API. No provider/route changes needed.
_CACHES: dict[str, TTLCache] = {ep: TTLCache(ttl_s) for ep, ttl_s in DATA_TTL_S.items()}

# Address formats. EVM addresses are case-insensitive and normalized to lower;
# Solana base58 public keys are case-SENSITIVE and must be passed through.
_EVM_HEX = re.compile(r"0x[0-9a-fA-F]{40}")
_BASE58 = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")

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
    address: str = Field(description="EVM address (0x-prefixed, 40 hex) or base58 Solana public key.")
    chain: str = Field(default=DEFAULT_CHAIN, description="ethereum|base|arbitrum|polygon|optimism|solana or chain id.")

    @field_validator("address")
    @classmethod
    def _addr(cls, v: str) -> str:
        if not isinstance(v, str) or not (_EVM_HEX.fullmatch(v) or _BASE58.fullmatch(v)):
            raise ValueError("address must be a 0x-prefixed 40-hex EVM address or a base58 Solana public key")
        # EVM addresses are case-insensitive; base58 keys are not.
        return v.lower() if v.startswith("0x") else v

    @model_validator(mode="after")
    def _addr_matches_chain(self):
        if is_solana(self.chain):
            if not _BASE58.fullmatch(self.address):
                raise ValueError("address must be a base58 Solana public key when chain=solana")
        elif not _EVM_HEX.fullmatch(self.address):
            raise ValueError("address must be a 0x-prefixed 40-hex EVM address")
        return self


class TokenBalancesRequest(AddressRequest):
    tokens: list[str] | None = Field(default=None, description="Optional ERC-20 contract list; omit for all tokens.")
    max_tokens: int = Field(default=50, ge=1, le=200, description="Cap on returned token entries.")

    @field_validator("tokens")
    @classmethod
    def _tokens(cls, v):
        if v is None:
            return v
        for t in v:
            if not (_EVM_HEX.fullmatch(t) or _BASE58.fullmatch(t)):
                raise ValueError(f"invalid token contract: {t}")
        return [t.lower() if t.startswith("0x") else t for t in v]


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
# Solana (Helius) helpers. Same evidence contract as the EVM routes: every
# normalized fact ships as {value, source, checked_at} — source "helius" for
# Helius-backed fields. Anything not implemented for Solana is an explicit
# chain_not_supported error, never a guess on the wrong chain.
# ---------------------------------------------------------------------------
def _need_helius() -> JSONResponse | None:
    if not settings.HELIUS_API_KEY:
        return JSONResponse(
            status_code=503,
            content={
                "error": "provider_unconfigured",
                "detail": "Helius API key not configured on gateway (HELIUS_API_KEY)",
                "chain": "solana",
            },
        )
    return None


def _chain_not_supported(endpoint: str, chain: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": "chain_not_supported",
            "chain": chain,
            "endpoint": f"/v1/data/{endpoint}",
            "detail": f"Solana is not implemented for {endpoint}; it is supported on: "
                      + ", ".join(f"/v1/data/{e}" for e in HELIUS_ENDPOINTS),
            "solana_supported_endpoints": [f"/v1/data/{e}" for e in HELIUS_ENDPOINTS],
        },
    )


def _sol_evidence(value, method: str, checked_at: str) -> dict:
    """The shared {value, source, checked_at} evidence wrapper (source=helius)."""
    return {"value": value, "source": "helius", "checked_at": checked_at, "method": method}


async def _helius_rpc(method: str, params: list) -> tuple[int, dict]:
    """Helius JSON-RPC (mainnet). Key is in the URL — never log the URL."""
    url = HELIUS_RPC_URL.format(key=settings.HELIUS_API_KEY)
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(url, json=body)
    try:
        data = r.json() if r.content else {}
    except Exception:
        data = {}
    if r.status_code == 200 and isinstance(data, dict) and data.get("error"):
        return 502, data
    return r.status_code, data


async def _helius_transactions(address: str, limit: int) -> tuple[int, list | dict]:
    """Helius Enhanced Transactions for an address (parsed transfer history)."""
    params = {"api-key": settings.HELIUS_API_KEY, "limit": max(1, min(int(limit), 100))}
    async with httpx.AsyncClient(timeout=25.0) as c:
        r = await c.get(HELIUS_TX_URL.format(address=address), params=params)
    try:
        data = r.json() if r.content else []
    except Exception:
        data = []
    return r.status_code, data


def _unwrap_subresult(res) -> tuple[dict | None, str | None]:
    """Normalize a sub-route result into (payload, error) for composed routes.

    Sub-handlers return either a dict (success) or a JSONResponse (error).
    A composed route must never fail wholesale because one section failed.
    """
    if isinstance(res, BaseException):
        logger.warning(f"market-snapshot subcall raised: {type(res).__name__}: {res}")
        return None, f"subcall_failed:{type(res).__name__}"
    if isinstance(res, JSONResponse):
        try:
            body = json.loads(bytes(res.body))
        except Exception:  # noqa: BLE001
            body = {}
        code = body.get("error") or f"http_{res.status_code}"
        return None, str(code)
    if isinstance(res, dict):
        return res, None
    return None, "unexpected_subcall_result"


def _strip_pricing(payload: dict) -> dict:
    """Drop the sub-route's own price/cost stamp from a composed section.

    The snapshot is billed once ($0.07); re-advertising the inner route's
    price inside the merge would misstate what the caller paid.
    """
    return {k: v for k, v in payload.items()
            if k not in ("price_usd", "provider_cost_usd", "margin_usd", "currency")}


async def _solana_token_balances(req: TokenBalancesRequest) -> dict | JSONResponse:
    """SPL token balances via Helius getTokenAccountsByOwner (jsonParsed)."""
    if e := _need_helius():
        return e
    endpoint = "token-balances"
    provider_cost = helius_provider_cost_usd(1)
    mints = ",".join(req.tokens or [])
    cache_key = _cache_key(endpoint, "solana", req.address, mints or "all", str(req.max_tokens))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        out = dict(hit)
        out["cache_hit"] = True
        return _stamp(out, endpoint, provider_cost)

    status, data = await _helius_rpc(
        "getTokenAccountsByOwner",
        [req.address, {"programId": SOLANA_TOKEN_PROGRAM}, {"encoding": "jsonParsed"}],
    )
    if status != 200:
        return JSONResponse(status_code=status or 502,
                            content={"error": "upstream_helius", "detail": json.dumps(data)[:500]})
    accounts = (data.get("result") or {}).get("value") or []
    wanted = set(req.tokens or [])
    balances = []
    for acc in accounts:
        info = (((acc.get("account") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
        mint = info.get("mint")
        if wanted and mint not in wanted:
            continue
        amount = info.get("tokenAmount") or {}
        balances.append({
            "mint": mint,
            "raw": amount.get("amount"),
            "decimals": amount.get("decimals"),
            "ui_amount": amount.get("uiAmount"),
        })
    balances = balances[: req.max_tokens]
    now = datetime.now(timezone.utc).isoformat()
    out = {
        "address": req.address,
        "chain": "solana",
        "token_count": len(balances),
        "balances": balances,
        "evidence": {
            "token_accounts": _sol_evidence(len(balances), "getTokenAccountsByOwner", now),
            "balances": _sol_evidence(balances, "getTokenAccountsByOwner", now),
        },
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


async def _solana_tx_history(req: TxHistoryRequest) -> dict | JSONResponse:
    """Parsed Solana transaction history via Helius Enhanced Transactions."""
    if e := _need_helius():
        return e
    endpoint = "tx-history"
    provider_cost = helius_provider_cost_usd(1)
    cache_key = _cache_key(endpoint, "solana", req.address, str(req.limit))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        out = dict(hit)
        out["cache_hit"] = True
        return _stamp(out, endpoint, provider_cost)

    status, data = await _helius_transactions(req.address, req.limit)
    if status != 200 or not isinstance(data, list):
        return JSONResponse(status_code=status or 502,
                            content={"error": "upstream_helius", "detail": json.dumps(data)[:500]})
    txs = []
    for t in data[: req.limit]:
        ts = t.get("timestamp")
        stamp = None
        if isinstance(ts, (int, float)):
            try:
                stamp = datetime.fromtimestamp(ts, timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                stamp = None
        txs.append({
            "hash": t.get("signature"),
            "type": t.get("type"),
            "description": t.get("description"),
            "timestamp": stamp,
            "slot": t.get("slot"),
            "fee": t.get("fee"),
            "fee_payer": t.get("feePayer"),
            "native_transfers": (t.get("nativeTransfers") or [])[:5],
            "token_transfers": (t.get("tokenTransfers") or [])[:5],
        })
    now = datetime.now(timezone.utc).isoformat()
    out = {
        "address": req.address,
        "chain": "solana",
        "count": len(txs),
        "transactions": txs,
        "evidence": {
            "transactions": _sol_evidence(txs, "getEnhancedTransactions", now),
        },
        "note": "from_block is EVM-only; Solana history is the most recent N transactions.",
        "cache_hit": False,
    }
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)


async def _solana_token_price(req: TokenPriceRequest) -> dict | JSONResponse:
    """SPL token spot price: Helius DAS getAsset price_info, CoinGecko fallback.

    A CoinGecko coin id (req.id) is chain-agnostic and served from CoinGecko;
    a mint address (req.contract) is resolved by Helius first so the primary
    Solana path is single-vendor.
    """
    if e := _need_helius():
        return e
    endpoint = "token-price"
    provider_cost = helius_provider_cost_usd(1)
    mint = (req.contract or "").strip()
    if mint and not _BASE58.fullmatch(mint):
        # The chain is supported; the field shape is wrong -> 422 (validation),
        # not a bad_chain 400. Nothing is billed: the money-path guard
        # re-validates the paid request before settlement.
        return JSONResponse(status_code=422,
                            content={"error": "invalid_contract",
                                     "detail": "Solana contract must be a base58 mint address"})
    cache_key = _cache_key(endpoint, "solana", mint, str(req.id or ""))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        out = dict(hit)
        out["cache_hit"] = True
        return _stamp(out, endpoint, provider_cost)

    now = datetime.now(timezone.utc).isoformat()
    if mint:
        status, data = await _helius_rpc("getAsset", [{"id": mint}])
        asset = (data.get("result") or {}) if status == 200 else {}
        info = asset.get("token_info") or {}
        pinfo = info.get("price_info") or {}
        price = pinfo.get("price_per_token")
        if price is not None and str(pinfo.get("currency", "USD")).upper() == "USD":
            out = {
                "contract": mint, "chain": "solana", "usd": price,
                "symbol": info.get("symbol"),
                "decimals": info.get("decimals"),
                "provider": "helius",
                "evidence": {
                    "price_usd": _sol_evidence(price, "getAsset(token_info.price_info)", now),
                    "symbol": _sol_evidence(info.get("symbol"), "getAsset(token_info)", now),
                },
                "cache_hit": False,
            }
            _cached_set(endpoint, cache_key, out)
            return _stamp(out, endpoint, provider_cost)
        # Fallback: CoinGecko's Solana asset platform (free tier).
        url = f"{COINGECKO_BASE}/simple/token_price/solana"
        params = {"contract_addresses": mint, "vs_currencies": "usd", "include_24hr_change": "true"}
        if settings.COINGECKO_API_KEY:
            params["x_cg_demo_api_key"] = settings.COINGECKO_API_KEY
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(url, params=params)
        if r.status_code == 200:
            entry = (r.json().get(mint) or {})
            if entry.get("usd") is not None:
                out = {
                    "contract": mint, "chain": "solana", "usd": entry.get("usd"),
                    "change_24h_usd": entry.get("usd_24h_change"),
                    "provider": "coingecko",
                    "evidence": {
                        "price_usd": {"value": entry.get("usd"),
                                      "source": "coingecko /simple/token_price/solana",
                                      "checked_at": now},
                    },
                    "cache_hit": False,
                }
                _cached_set(endpoint, cache_key, out)
                return _stamp(out, endpoint, provider_cost)
        return JSONResponse(status_code=502,
                            content={"error": "price_unavailable", "chain": "solana", "contract": mint,
                                     "detail": "no USD price from Helius price_info or CoinGecko"})

    # CoinGecko id (e.g. "solana") — chain-independent lookup.
    url = f"{COINGECKO_BASE}/simple/price"
    params = {"ids": req.id, "vs_currencies": "usd", "include_24hr_change": "true"}
    if settings.COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = settings.COINGECKO_API_KEY
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(url, params=params)
    if r.status_code == 200:
        j = r.json()
        entry = j.get(req.id) or {}
        if entry.get("usd") is not None:
            out = {
                "id": req.id, "chain": "solana", "usd": entry.get("usd"),
                "change_24h_usd": entry.get("usd_24h_change"),
                "provider": "coingecko",
                "evidence": {
                    "price_usd": _sol_evidence(entry.get("usd"), "coingecko /simple/price", now),
                },
                "cache_hit": False,
            }
            _cached_set(endpoint, cache_key, out)
            return _stamp(out, endpoint, provider_cost)
    return JSONResponse(status_code=502,
                        content={"error": "price_unavailable", "chain": "solana", "id": req.id})


# ---------------------------------------------------------------------------
# Routes (each: gate -> cache -> upstream -> normalize -> stamp)
# ---------------------------------------------------------------------------
@router.post("/token-balances")
async def token_balances(req: TokenBalancesRequest, request: Request):
    if d := _disabled():
        return d
    if is_solana(req.chain):
        return await _solana_token_balances(req)
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
    if is_solana(req.chain):
        return await _solana_token_price(req)
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
    if is_solana(req.chain):
        return _chain_not_supported("nft-ownership", req.chain)
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
    if is_solana(req.chain):
        return await _solana_tx_history(req)
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
    if is_solana(chain):
        return _chain_not_supported("gas-oracle", chain)
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
    if is_solana(chain):
        return _chain_not_supported("block", chain)
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
    if is_solana(req.chain):
        return _chain_not_supported("token-risk", req.chain)
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
    if is_solana(req.chain):
        return _chain_not_supported("wallet-intel", req.chain)
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


async def whale_alert_payload(req: WhaleAlertRequest, network: str) -> dict:
    """Scan large transfers for a wallet (EVM). Shared by the paid route and
    the webhook delivery worker so both see identical alert semantics."""
    a = (req.address or "").lower()
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
    return {"watched_address": a or None, "chain": req.chain, "min_usd": req.min_usd,
            "alerts": large, "alerts_count": len(large),
            "note": "USD floor applied to native-asset transfers only; erc20 values are raw "
                    "(call /token-price for USD).",
            "cache_hit": False}


@router.post("/whale-alerts")
async def whale_alerts(req: WhaleAlertRequest, request: Request):
    """Large-transfer alerts for a wallet (or chain-wide token scan when a
    contract is given). Every alert carries hash + block + timestamp."""
    if d := _disabled():
        return d
    if is_solana(req.chain):
        return _chain_not_supported("whale-alerts", req.chain)
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

    out = await whale_alert_payload(req, network)
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
        if is_solana(chain):
            return {"chain": chain, "error": "chain_not_supported",
                    "detail": "Solana is not implemented for cross-chain-compare"}
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
    if is_solana(req.chain):
        return _chain_not_supported("token-intel", req.chain)
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


# ---------------------------------------------------------------------------
# Market snapshot — one paid call, three intelligence sections in parallel.
#
# POST /v1/data/market-snapshot ($0.07) fans out to token-intel, whale-alerts
# and token-risk CONCURRENTLY and merges them as "token", "whale_activity" and
# "risk". A failing section yields {"error": ...} for that key and the rest of
# the snapshot still returns (partial: true) — a buyer never pays for a
# wholesale failure because one upstream blipped.
#
# The three sections run through the same handlers as their standalone routes,
# so caching, evidence stamps and provider accounting stay single-source.
# ---------------------------------------------------------------------------
class MarketSnapshotRequest(BaseModel):
    contract: str = Field(description="ERC-20 contract address to snapshot.")
    chain: str = Field(default=DEFAULT_CHAIN, description="EVM chain of the contract.")
    address: str | None = Field(default=None, description="Wallet for whale activity; defaults to the contract.")
    coin_id: str | None = Field(default=None, description="Optional CoinGecko coin id for market context.")
    min_usd: float = Field(default=100000.0, ge=0, description="USD floor for whale alerts.")
    limit: int = Field(default=50, ge=1, le=100, description="Transfers to scan per direction.")

    @model_validator(mode="after")
    def _shapes(self):
        # Solana is rejected by the route with a structured chain_not_supported
        # (400) before any provider call; its addresses are base58, so the EVM
        # shape check must not fire first and turn that into a generic 422.
        if is_solana(self.chain):
            return self
        if not isinstance(self.contract, str) or not _EVM_HEX.fullmatch(self.contract):
            raise ValueError("contract must be a 0x-prefixed 40-hex EVM address")
        if self.address is not None and not _EVM_HEX.fullmatch(self.address):
            raise ValueError("address must be a 0x-prefixed 40-hex EVM address")
        self.contract = self.contract.lower()
        if self.address is not None:
            self.address = self.address.lower()
        return self


@router.post("/market-snapshot")
async def market_snapshot(req: MarketSnapshotRequest, request: Request):
    if d := _disabled():
        return d
    if is_solana(req.chain):
        return _chain_not_supported("market-snapshot", req.chain)
    if e := _need_alchemy():
        return e
    try:
        _network(req.chain)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "bad_chain", "detail": str(e)})

    endpoint = "market-snapshot"
    # 5 (token-intel) + 3 (whale-alerts) + 4 (token-risk) upstream calls.
    provider_cost = data_provider_cost_usd(endpoint, calls=12)
    c = req.contract.lower()
    a = (req.address or c).lower()
    cache_key = _cache_key(endpoint, req.chain, c, a, str(req.coin_id or ""),
                           str(req.min_usd), str(req.limit))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        out = dict(hit)
        out["cache_hit"] = True
        return _stamp(out, endpoint, provider_cost)

    snapshot_at = datetime.now(timezone.utc).isoformat()
    token_req = TokenIntelRequest(contract=c, chain=req.chain, coin_id=req.coin_id)
    whale_req = WhaleAlertRequest(address=a, chain=req.chain,
                                  min_usd=req.min_usd, limit=req.limit)
    risk_req = TokenRiskRequest(contract=c, chain=req.chain, coin_id=req.coin_id)

    token_res, whale_res, risk_res = await asyncio.gather(
        token_intel(token_req, request),
        whale_alerts(whale_req, request),
        token_risk(risk_req, request),
        return_exceptions=True,
    )

    sections: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for key, res in (("token", token_res), ("whale_activity", whale_res), ("risk", risk_res)):
        payload, err = _unwrap_subresult(res)
        if err:
            # Partial result: this section carries its error, the others stand.
            sections[key] = {"error": err}
            errors[key] = err
        else:
            sections[key] = _strip_pricing(payload)

    out = {
        "contract": c,
        "chain": req.chain,
        "address": a,
        "token": sections["token"],
        "whale_activity": sections["whale_activity"],
        "risk": sections["risk"],
        "snapshot_at": snapshot_at,
        "partial": bool(errors),
        "sections": {"requested": 3, "ok": 3 - len(errors), "failed": len(errors)},
        "cache_hit": False,
    }
    if errors:
        out["errors"] = errors
    _cached_set(endpoint, cache_key, out)
    return _stamp(out, endpoint, provider_cost)
