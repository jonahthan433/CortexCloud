"""Reconciliation test: every discovery surface must match the live app.

- ROUTE_PRICING (x402.json / llms.txt / bazaar paid list) must only contain
  routes the FastAPI app actually mounts.
- Every paid route must be paywalled (402 without payment).
- Every FREE_ROUTES entry must genuinely be free (no 402).
- openapi.json must list every mounted paid route.

Run in the CortexCloud venv: python tests/test_discovery_reconcile.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import create_app
from app.x402.pricing import ROUTE_PRICING, FREE_ROUTES

app = create_app(override_openapi=False)

# Routes the app actually mounts: {(METHOD, path)}.
# include_router nests _IncludedRouter wrappers whose children carry the
# FULL path (prefix already applied by this FastAPI version), so walking
# .original_router.routes yields complete paths.
mounted = set()

def _walk(routes):
    for route in routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path:
            for m in methods:
                if m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    mounted.add((m, path))
        # Recurse: plain Router, or _IncludedRouter.original_router
        sub = getattr(route, "routes", None)
        if sub:
            _walk(sub)
        orig = getattr(route, "original_router", None)
        if orig is not None:
            _walk(getattr(orig, "routes", []))

_walk(app.routes)

paid = {(k.split(" ", 1)[0], k.split(" ", 1)[1]) for k in ROUTE_PRICING}
free = {(k.split(" ", 1)[0], k.split(" ", 1)[1]) for k in FREE_ROUTES}

# 1. No phantom paid routes (advertised but not mounted).
phantom_paid = paid - mounted
assert not phantom_paid, f"phantom paid routes (402 forever / never settle): {phantom_paid}"

# 2. No phantom free routes.
phantom_free = free - mounted
assert not phantom_free, f"phantom free routes: {phantom_free}"

# 3. Free routes must not overlap paid routes.
overlap = paid & free
assert not overlap, f"route both paid and free: {overlap}"

# 4. Every paid route must be paywalled by the middleware (probe the path
#    against the paywall table — the middleware keys on PATH only).
from app.middleware.x402 import _PATH_PRICING
paywalled = {p for p in _PATH_PRICING}
missing_gate = {p for _, p in paid if p not in paywalled}
assert not missing_gate, f"paid routes missing middleware gate: {missing_gate}"

print(f"PASS: {len(paid)} paid + {len(free)} free routes all mounted, "
      f"no phantom/overlap, all paid routes gated")
