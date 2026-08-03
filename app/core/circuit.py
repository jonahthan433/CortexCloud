"""Per-provider circuit breaker. If a provider's error rate exceeds 20% over
a rolling 30s window, the circuit opens for 30s: requests to it fail fast
with 503 + Retry-After instead of piling onto a dying upstream.
ponytail: in-process state; if we ever run multiple uvicorn workers the
breaker is per-worker (acceptable — worst case one worker keeps probing)."""
import time

from fastapi import HTTPException, status

WINDOW = 30.0
THRESHOLD = 0.20
MIN_SAMPLES = 10
COOLDOWN = 30.0

_state: dict[str, dict] = {}


class CircuitOpenError(HTTPException):
    """Raised when a provider's circuit is open. Never retried."""


def _get(name: str) -> dict:
    s = _state.setdefault(name, {"events": [], "open_until": 0.0})
    now = time.time()
    # trim events outside the window
    s["events"] = [(t, ok) for t, ok in s["events"] if t > now - WINDOW]
    return s


def circuit_open_until(name: str) -> float:
    return _get(name)["open_until"]


def circuit_check(name: str) -> None:
    """Raise CircuitOpenError (503 + Retry-After) if the breaker is open."""
    open_until = circuit_open_until(name)
    if open_until > time.time():
        raise CircuitOpenError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Provider '{name}' circuit open (error rate exceeded {THRESHOLD:.0%} over {WINDOW:.0f}s)",
            headers={"Retry-After": str(int(open_until - time.time()) + 1)},
        )


def circuit_record(name: str, ok: bool) -> None:
    s = _get(name)
    now = time.time()
    s["events"].append((now, ok))
    if len(s["events"]) < MIN_SAMPLES:
        return
    errors = sum(1 for _, ok in s["events"] if not ok)
    if errors / len(s["events"]) > THRESHOLD:
        s["open_until"] = now + COOLDOWN


def circuit_health() -> dict:
    """Provider error counts for /metrics."""
    return {
        name: {
            "events": len(_get(name)["events"]),
            "open_until": _get(name)["open_until"],
        }
        for name in _state
    }
