"""In-process caches — Redis is gone.

Everything here is single-worker safe; the service runs one uvicorn
worker. If we ever scale to N workers these move to PostgreSQL (nonce
dedup already lives there — see middleware/x402.py).

ponytail: single-process TTL dicts; if multi-worker is ever needed,
swap `PROOF_CACHE`/`RATE_WINDOWS` for a PG-backed store.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable, Optional

_lock = threading.Lock()

PROOF_CACHE: dict[str, tuple[float, str]] = {}        # proof hash -> (expiry, result)
PROOF_TTL_S = 60.0

RATE_WINDOWS: dict[str, deque[float]] = defaultdict(deque)  # payer -> timestamps
RATE_LOCK = threading.Lock()


def proof_get(proof_hash: str) -> Optional[str]:
    with _lock:
        hit = PROOF_CACHE.get(proof_hash)
        if hit is None:
            return None
        expiry, result = hit
        if time.time() > expiry:
            PROOF_CACHE.pop(proof_hash, None)
            return None
        return result


def proof_set(proof_hash: str, result: str) -> None:
    with _lock:
        PROOF_CACHE[proof_hash] = (time.time() + PROOF_TTL_S, result)
        if len(PROOF_CACHE) > 5000:  # ponytail: cap, evict oldest when big
            oldest = min(PROOF_CACHE, key=lambda k: PROOF_CACHE[k][0])
            PROOF_CACHE.pop(oldest, None)


def rate_check(payer_key: str, limit: int, window_s: float = 60.0) -> bool:
    """True if within limit, False if over. Sliding window per key."""
    with RATE_LOCK:
        dq = RATE_WINDOWS[payer_key]
        now = time.time()
        while dq and now - dq[0] > window_s:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True


# -- async compat wrappers (same names the x402 middleware imports) --------
async def cache_proof(payment_signature: str) -> None:
    proof_set(payment_signature, "settled")


async def proof_is_cached(payment_signature: str) -> bool:
    return proof_get(payment_signature) is not None


async def rate_allow(payer_key: str) -> int:
    """Increment the window counter for this payer and return the count."""
    with RATE_LOCK:
        dq = RATE_WINDOWS[payer_key]
        now = time.time()
        while dq and now - dq[0] > 60.0:
            dq.popleft()
        dq.append(now)
        return len(dq)


class TTLCache:
    """Minimal TTL dict (used by /v1/backends availability caching etc.)."""

    def __init__(self, ttl_s: float = 30.0):
        self._ttl = ttl_s
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            expiry, val = hit
            if time.time() > expiry:
                self._data.pop(key, None)
                return None
            return val

    def set(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = (time.time() + self._ttl, value)
