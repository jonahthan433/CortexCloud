"""Per-request structured-logging context + Prometheus metrics (S6)."""
import contextvars

from prometheus_client import Counter, Histogram

_req = contextvars.ContextVar("cortex_req", default={})

LATENCY = Histogram(
    "cortexcloud_request_latency_seconds",
    "x402 request latency per endpoint",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
UPSTREAM_ERRORS = Counter("cortexcloud_upstream_errors_total", "upstream provider errors", ["provider"])
CACHE_HITS = Counter("cortexcloud_proof_cache_hits_total", "x402 payment-proof cache hits")


def set_req(**kw):
    """Router fills upstream_provider / upstream_latency_ms; middleware reads."""
    d = dict(_req.get())
    d.update(kw)
    _req.set(d)


def get_req():
    return _req.get()
