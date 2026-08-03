"""S4: Data marketplace expansion — news, ETH/SOL balances, DeFi yields, gas.

Extends the existing /x402/v1/data/* set. Upstreams: Exa (news), public RPCs
for ETH (mainnet) + Solana, DeFi Llama yields, and ETH-based gas proxy.
Cache: news 300s, balances 60s, yields 300s, gas 15s (spec).
Prices in app/x402/pricing.py ROUTE_PRICING.
"""
import logging
import httpx
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.cache import cached_json
from app.core.config import settings
from app.core.http import shared_client

logger = logging.getLogger("cortexcloud.x402.data2")
router = APIRouter()

_H = {"Content-Type": "application/json", "User-Agent": "CortexCloud/1.0"}

ETH_RPC = ["https://ethereum-rpc.publicnode.com", "https://eth.llamarpc.com", "https://1rpc.io/eth"]
SOL_RPC = "https://api.mainnet-beta.solana.com"


def _hex_int(v: str) -> int:
    return int(v, 16)


async def _eth_rpc(method: str, params: list):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    c = shared_client("eth_rpc", 10.0, _H)
    last = None
    for url in ETH_RPC:
        try:
            r = await c.post(url, json=payload)
            if r.status_code == 200:
                j = r.json()
                if "result" in j:
                    return j
        except Exception as e:
            last = e
            continue
    if last:
        logging.getLogger("cortexcloud.x402.data2").warning(f"eth rpc failed: {last}")
    return None


# ---- News (Exa AI) ---------------------------------------------------------
@router.get("/data/news")
async def data_news(q: str = Query(...), limit: int = Query(10, ge=1, le=30)):
    """Recent news via Exa AI filtered to news sources. Price $0.02/call."""
    if not settings.EXA_API_KEY:
        return JSONResponse(status_code=503, content={"error": "EXA_API_KEY not configured"})
    h = {"x-api-key": settings.EXA_API_KEY, "Content-Type": "application/json", "User-Agent": "CortexCloud/1.0"}
    c = shared_client("exa2", 20, h)
    body = {"query": q, "numResults": limit, "category": "news", "type": "auto"}
    try:
        r = await c.post("https://api.exa.ai/search", json=body)
        if r.status_code != 200:
            return JSONResponse(status_code=502, content={"error": "exa_upstream", "detail": r.text[:300]})
        res = [{"title": it.get("title"), "url": it.get("url"), "published": it.get("publishedDate"),
                "text": (it.get("text") or "")[:500]} for it in r.json().get("results", [])]
        return JSONResponse({"query": q, "count": len(res), "results": res})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "exa_upstream", "detail": str(e)})


# ---- ETH balance (mainnet) -------------------------------------------------
@router.get("/data/eth/balance")
async def eth_balance(address: str = Query(...)):
    """Native ETH balance on Ethereum mainnet (wei + human). $0.001/call."""
    try:
        res, _ = await cached_json(f"x402:eth:balance:{address}", 60,
                                   lambda: _eth_rpc("eth_getBalance", [address, "latest"]))
        if res is None or "result" not in res:
            return JSONResponse(status_code=503, content={"error": "upstream_eth_rpc"})
        wei = _hex_int(res["result"])
        return JSONResponse({"address": address, "network": "ethereum", "chain_id": "eip155:1",
                             "wei": str(wei), "eth": wei / 1e18})
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": "upstream_eth_rpc", "detail": str(e)})


# ---- SOL balance (mainnet) -------------------------------------------------
@router.get("/data/solana/balance")
async def solana_balance(address: str = Query(...)):
    """Native SOL balance (lamports) on Solana mainnet. $0.001/call."""
    async def _sol():
        c = shared_client("solana", 10.0, _H)
        r = await c.post(SOL_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]})
        if r.status_code != 200:
            raise RuntimeError(r.text[:300])
        return r.json()
    try:
        res, _ = await cached_json(f"x402:sol:balance:{address}", 60, _sol)
        lamports = (res.get("result") or {}).get("value")
        if lamports is None:
            return JSONResponse(status_code=503, content={"error": "upstream_solana_rpc"})
        return JSONResponse({"address": address, "network": "solana", "lamports": str(lamports), "sol": lamports / 1e9})
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": "upstream_solana_rpc", "detail": str(e)})


# ---- DeFi yields (DeFi Llama) ----------------------------------------------
@router.get("/data/defi/yields")
async def defi_yields(protocol: str = Query(None)):
    """Current APY/TVL from DeFi Llama, optionally filtered by project slug. $0.005/call."""
    async def _fetch():
        c = shared_client("defi", 20.0, {"User-Agent": "CortexCloud/1.0"})
        r = await c.get("https://yields.llama.fi/pools")
        if r.status_code != 200:
            raise RuntimeError(r.text[:300])
        return r.json()
    try:
        data, _ = await cached_json("x402:defi:yields", 300, _fetch)
        pools = data.get("data", [])
        if protocol:
            pools = [p for p in pools if protocol.lower() in (p.get("project") or "").lower()]
        out = [{"project": p.get("project"), "symbol": p.get("symbol"), "chain": p.get("chain"),
                "apy": p.get("apy"), "tvlUsd": p.get("tvlUsd")} for p in pools[:50]]
        return JSONResponse({"count": len(out), "protocol": protocol, "pools": out})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "upstream_defillama", "detail": str(e)})


# ---- Gas (Base + ETH mainnet) ----------------------------------------------
@router.get("/data/gas")
async def gas_prices():
    """Current gas (gwei) for Ethereum mainnet (proxy for Base L1 data gas). 15s cache. $0.001/call."""
    async def _gas():
        # Use eth_feeHistory latest baseFee + maxPriority as a pragmatic read.
        res = await _eth_rpc("eth_feeHistory", [1, "latest", [25, 50, 75]])
        if res is None or "result" not in res:
            raise RuntimeError("gas upstream unavailable")
        rh = res["result"]
        recent = rh.get("reward", [[]])[-1]
        base = _hex_int(rh["baseFeePerGas"][-1])
        return {"suggested_base_fee_gwei": base / 1e9,
                "priority_gwei": [int(x, 16) / 1e9 for x in recent] if recent else None}
    try:
        data, _ = await cached_json("x402:gas:prices", 15, _gas)
        return JSONResponse({"network": "ethereum_mainnet", "ethereum_gas_gwei": data, "base_gas_gwei": data})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "upstream_gas", "detail": str(e)})