"""Quantum namespace — additive alias layer for the Optimization Network.

Regroups the real optimization endpoints under /v1/quantum/* so the public
architecture (AI / Quantum / Data / Research / ML / Automation) has a clean
home for the flagship. The original /v1/optimize, /v1/estimate, /v1/jobs/{id},
/v1/backends, /v1/capabilities remain as backward-compatible aliases — they are
NOT removed, so existing clients and the live discovery manifest keep working.

No new business logic: each handler is the same function from app.api.optimization,
imported and re-bound. Payment, validation and pricing are untouched.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.optimization import (
    capabilities,
    get_job,
    list_backends,
    optimize,
    v1_estimate,
    v1_examples,
)

router = APIRouter(prefix="/v1/quantum", tags=["quantum (alias)"])

# Discover -> Estimate -> Price -> Pay -> Execute -> Poll -> Result
router.post("/estimate", summary="Analyze a problem (free) — alias of /v1/estimate")(v1_estimate)
router.post("/optimize", summary="Solve a QUBO/Ising problem (x402-paid) — alias of /v1/optimize")(optimize)
router.get("/jobs/{job_id}", summary="Poll an optimization job (free) — alias of /v1/jobs/{id}")(get_job)
router.get("/backends", summary="List solver backends (free) — alias of /v1/backends")(list_backends)
router.get("/capabilities", summary="Capabilities catalog (free) — alias of /v1/capabilities")(capabilities)
router.get("/examples", summary="Canonical examples (free) — alias of /v1/examples")(v1_examples)
