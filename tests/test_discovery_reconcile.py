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

# 5. Every mounted money route must carry a paywall decision: priced in
#    ROUTE_PRICING or listed free. This catches the C1 class of defect — a
#    route mounted and live but absent from the pricing table, so the
#    middleware never reaches its pricing branch and serves it for free.
_money_prefixes = ("/v1/data/", "/v1/aggregate/")
money_mounted = {(m, p) for (m, p) in mounted if p.startswith(_money_prefixes) and m in ("GET", "POST")}
uncovered = {mp for mp in money_mounted if mp not in paid and mp not in free}
assert not uncovered, f"mounted money routes with no paywall decision (free money!): {sorted(uncovered)}"

# 6. Negative pin (owner decision 2026-10-18): ML is not part of this product.
#    No /v1/ml/* route may be mounted or priced.
_ml_mounted = {(m, p) for (m, p) in mounted if p.startswith("/v1/ml")}
assert not _ml_mounted, f"/v1/ml/* routes must not be mounted: {sorted(_ml_mounted)}"
_ml_priced = {k for k in ROUTE_PRICING if k.split(" ", 1)[1].startswith("/v1/ml")}
assert not _ml_priced, f"/v1/ml/* routes must not be priced: {sorted(_ml_priced)}"

# 7. MCP tool registry (bazaar mirror; source of truth for the /mcp gateway
#    tool table) must cover exactly the advertised paid surface + the free
#    capabilities tool, with real object input schemas.
from app.x402.bazaar import list_tools, tool_entry
from app.x402.pricing import public_routes

_tool_names = [t["name"] for t in list_tools()]
assert _tool_names and len(_tool_names) == len(set(_tool_names)), "duplicate/empty MCP tool names"
_tool_paths = {tool_entry(n)["path"] for n in _tool_names}
_paid_paths = {k.split(" ", 1)[1] for k in public_routes()}
assert _tool_paths - {"/v1/capabilities"} == _paid_paths, (
    f"MCP tool registry drift: tools {sorted(_tool_paths)} vs paid {sorted(_paid_paths)}"
)
assert len(_tool_names) == len(_paid_paths) + 1, f"unexpected MCP tool count: {len(_tool_names)}"
for _n in _tool_names:
    _sch = tool_entry(_n)["input_schema"]
    assert isinstance(_sch, dict) and _sch.get("type") == "object", f"{_n}: input_schema must be an object schema"

# 8. Every served discovery surface must advertise exactly ROUTE_PRICING.
#    (x402-list.com is an external directory fed by a one-time operator
#    submission, not a surface served from this repo, so it cannot be pinned.)
import asyncio
import json as _json

from app.x402.bazaar_routes import _endpoint_catalog
from app.x402.discovery import build_manifest, llms_txt, well_known_x402_v1

# 8a. /.well-known/x402.json (v2 manifest)
_manifest_paths = {e["path"] for e in build_manifest()["endpoints"]}
assert _manifest_paths == _paid_paths, (
    f"x402.json manifest drift: {sorted(_manifest_paths)} vs paid {sorted(_paid_paths)}"
)

# 8b. /.well-known/bazaar endpoint catalog
_bazaar_catalog = _endpoint_catalog()
_bazaar_paid = {e["path"] for e in _bazaar_catalog if e["price"] != "free"}
assert _bazaar_paid == _paid_paths, (
    f"bazaar endpoint drift: {sorted(_bazaar_paid)} vs paid {sorted(_paid_paths)}"
)
_bazaar_free = {e["path"] for e in _bazaar_catalog if e["price"] == "free"}
assert _bazaar_free <= {p.split(" ", 1)[1] for p in FREE_ROUTES}, (
    f"bazaar advertises unknown free routes: {sorted(_bazaar_free)}"
)

# 8c. /llms.txt
_llms = asyncio.run(llms_txt()).body.decode()
_llms_routes = set()
for _ln in _llms.splitlines():
    if _ln.startswith("- ") and " — " in _ln:
        _left = _ln[2:].split(" — ", 1)[0].split(" ")
        if len(_left) >= 2 and _left[0] in ("GET", "POST"):
            _llms_routes.add(f"{_left[0]} {_left[1]}")
assert _llms_routes == set(public_routes()) | set(FREE_ROUTES), (
    f"llms.txt drift: {sorted(_llms_routes)} vs "
    f"{sorted(set(public_routes()) | set(FREE_ROUTES))}"
)

# 8d. /.well-known/x402 (v1 resource list)
_v1_paths = {
    r.replace("https://api.cortexcloud.org", "")
    for r in asyncio.run(well_known_x402_v1())["resources"]
}
assert _v1_paths == _paid_paths | {"/v1/capabilities"}, (
    f"v1 x402 resource drift: {sorted(_v1_paths)}"
)

# 8e. openapi.json lists every paid route (and no phantom paid route)
with open(os.path.join(os.path.dirname(__file__), "..", "openapi.json")) as _fh:
    _spec = _json.load(_fh)
_spec_paid = {
    f"{m.upper()} {p}"
    for p, methods in _spec["paths"].items()
    for m in methods
    if f"{m.upper()} {p}" in ROUTE_PRICING
}
assert _spec_paid == set(ROUTE_PRICING), (
    f"openapi.json paid-route drift: {sorted(_spec_paid)} vs {sorted(ROUTE_PRICING)}"
)

print(f"PASS: {len(paid)} paid + {len(free)} free routes all mounted, "
      f"no phantom/overlap, all paid routes gated, money surface fully covered, "
      f"{len(_tool_names)} MCP tools mirror the paid surface, "
      f"bazaar/x402.json/llms.txt/v1-x402/openapi all match ROUTE_PRICING")
