"""S3: provider health + rolling p95 latency for GET /health.

Reads the ModelRouter class-level sliding windows (latency + result per
(model, provider)) and provider availability from settings keys. Cheap, no DB.
"""
import time
from collections import deque

from app.core.config import settings
from app.routing.router import ModelRouter, _PROVIDER_INSTANCES

_PROVIDER_LABELS = {
    "openai": "openai", "anthropic": "anthropic", "gemini": "gemini",
    "groq": "groq", "nvidia": "nvidia", "openrouter": "openrouter",
}
_KEY_MAP = {
    "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY",
    "nvidia": "NVIDIA_API_KEY", "openrouter": "OPENROUTER_API_KEY",
}


def _configured(provider: str) -> bool:
    return bool(getattr(settings, _KEY_MAP.get(provider, ""), None))


def provider_health():
    """Return {provider: healthy|degraded|configured|unconfigured, latency_p95_ms}."""
    out = {}
    # Aggregate latency/error windows across all (model, provider) pairs.
    windows = {p: {"lat": [], "status": []} for p in _PROVIDER_LABELS}
    now = time.time()
    for (model_name, provider) in list(ModelRouter._latency_window.keys()):
        if provider not in _PROVIDER_LABELS:
            continue
        lat_dq: deque = ModelRouter._latency_window[(model_name, provider)]
        res_dq: deque = ModelRouter._result_window[(model_name, provider)]
        vals = [v for (t, v) in list(lat_dq) if now - t <= ModelRouter._window_duration]
        stat = [(t, ok) for (t, ok) in list(res_dq) if now - t <= ModelRouter._window_duration]
        windows[provider]["lat"].extend(vals)
        windows[provider]["status"].extend([ok for (_, ok) in stat])

    for provider in _PROVIDER_LABELS:
        lat = windows[provider]["lat"]
        ok = windows[provider]["status"]
        if not _configured(provider):
            out[provider] = {"status": "unconfigured", "latency_p95_ms": 0}
            continue
        if not lat:
            out[provider] = {"status": "healthy", "latency_p95_ms": 0}  # configured, idle
            continue
        err_rate = (1 - sum(ok) / len(ok)) if ok else 0.0
        lat.sort()
        p95 = lat[min(int(0.95 * len(lat)), len(lat) - 1)] * 1000.0
        status = "degraded" if err_rate > 0.5 else ("error" if err_rate >= 0.8 else "healthy")
        out[provider] = {"status": status, "latency_p95_ms": round(p95, 1), "error_rate": round(err_rate, 3)}
    return out