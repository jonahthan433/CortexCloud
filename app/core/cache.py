"""Redis-backed performance helpers: shared client, payment-proof cache,
nonce dedup, and coalesced JSON caching. All helpers FAIL OPEN — a Redis
outage must never block or break real payments."""
import asyncio
import hashlib
import json
import secrets
import time

from app.core.config import settings

_redis = None


def get_redis():
    """Shared redis.asyncio client (lazy singleton)."""
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis

        url = settings.REDIS_URL or f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
        _redis = aioredis.from_url(url, decode_responses=True)
    return _redis


# ---------------- S1: payment proof cache + nonce dedup ----------------

def _proof_key(payment_signature: str) -> str:
    return f"x402:proof:{hashlib.sha256(payment_signature.encode()).hexdigest()}"


async def proof_is_cached(payment_signature: str) -> bool:
    try:
        return bool(await get_redis().get(_proof_key(payment_signature)))
    except Exception:
        return False


async def cache_proof(payment_signature: str, ttl: int = 60) -> None:
    try:
        await get_redis().set(_proof_key(payment_signature), "1", ex=ttl)
    except Exception:
        pass


async def nonce_seen(nonce: str, valid_before: int | None = None) -> bool:
    """Claim a payment nonce. Returns True if it was ALREADY seen (reject)."""
    try:
        r = get_redis()
        ttl = 60
        if valid_before:
            ttl = max(1, min(3600, valid_before - int(time.time())))
        return not bool(await r.set(f"x402:nonce:{nonce}", "1", ex=ttl, nx=True))
    except Exception:
        return False


# ---------------- S5: sliding-window rate limit ----------------

async def rate_allow(payer: str, limit: int = 60, window: int = 60) -> int:
    """Sliding-window counter for a payer wallet. Returns current window count.
    Fail-open: a Redis outage must never block payments."""
    try:
        r = get_redis()
        now = time.time()
        key = f"x402:rl:{payer}"
        member = f"{now:.6f}:{secrets.token_hex(3)}"
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, window)
        _, _, count, _ = await pipe.execute()
        return count
    except Exception:
        return 0


# ---------------- S4: coalesced JSON response cache ----------------

_inflight: dict[str, asyncio.Future] = {}


async def cached_json(key: str, ttl: int, fetch) -> tuple:
    """Get(key) or fetch+set, with request coalescing: concurrent callers for
    the same key share ONE upstream fetch and all get the result.
    Returns (value, from_cache). Raises the fetch exception to ALL waiters."""
    r = get_redis()
    try:
        hit = await r.get(key)
        if hit is not None:
            return json.loads(hit), True
    except Exception:
        pass
    fut = _inflight.get(key)
    if fut is not None:
        return await fut, False
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _inflight[key] = fut
    try:
        value = await fetch()
        try:
            await r.set(key, json.dumps(value), ex=ttl)
        except Exception:
            pass
        fut.set_result(value)
        return value, False
    except Exception as e:
        fut.set_exception(e)
        raise
    finally:
        _inflight.pop(key, None)
