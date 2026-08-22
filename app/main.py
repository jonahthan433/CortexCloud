"""CortexCloud Optimization Network — FastAPI assembly.

Agent-facing surface: /v1/estimate (free), /v1/optimize (x402-paid),
/v1/jobs/{id}, /v1/backends, /v1/capabilities (free) + discovery
(/.well-known/x402.json, /.well-known/bazaar, /llms.txt, /openapi.json)
and the MCP gateway at /x402/v1/mcp. Health/metrics/static unchanged.
"""
import json as _json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import setup_logging

logger = logging.getLogger("cortexcloud.main")

SITE_DIR = "/opt/CortexCloudAPI/site"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Initializing CortexCloud Optimization Network...")
    try:
        from app.optimizer.runner import requeue_stale_jobs
        n = await requeue_stale_jobs()
        if n:
            logger.info(f"Requeued {n} stale job(s) left by a previous worker")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Startup requeue failed (continuing): {e}")
    # Pre-warm provider availability off-loop so the first /health after boot
    # is fast instead of triggering 15-45s of cloud discovery in-band.
    try:
        import asyncio as _asyncio
        from app.solvers import registry as _registry

        _asyncio.get_event_loop().create_task(
            _asyncio.to_thread(_registry.availability_summary)
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Startup availability pre-warm failed (continuing): {e}")
    yield
    logger.info("Shutting down CortexCloud Optimization Network...")


def create_app(override_openapi: bool = True) -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        description="Optimization infrastructure for AI agents — discover, pay for, and execute classical, hybrid, or quantum optimization through a single API.",
        version="2.0.0",
        lifespan=lifespan,
    )

    if override_openapi:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.json")) as _f:
            _OPENAPI_SPEC = _json.load(_f)

        application.openapi = lambda: _OPENAPI_SPEC

    # CORS. No cookies/sessions in this API (payment is x402-signed headers,
    # never bearer), so credentials are never needed — wildcard + credentials
    # would be an invalid combo browsers reject anyway.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request correlation tracing
    from app.middleware.trace import TracingMiddleware
    application.add_middleware(TracingMiddleware)

    # AHEAD/OPTIONS handling for scanners (before routing)
    from app.middleware.probe import ProbeMiddleware
    application.add_middleware(ProbeMiddleware)

    # Agent surface + discovery routers
    from app.api.optimization import router as optimization_router
    from app.x402.audit_routes import router as audit_router
    from app.x402.bazaar_routes import router as bazaar_router
    from app.x402.discovery import router as discovery_router

    application.include_router(optimization_router, tags=["Optimization"])

    # Additive /v1/quantum/* namespace — aliases of the optimization handlers.
    # Keeps /v1/optimize etc. intact for backward compatibility.
    from app.api.quantum import router as quantum_router
    application.include_router(quantum_router)
    from app.api.track import router as track_router
    from app.api.trial import router as trial_router
    application.include_router(trial_router, tags=["Trial"])
    from app.api.benchmarks import router as benchmarks_router
    application.include_router(benchmarks_router, tags=["Benchmarks"])
    from app.models.referral import Referral  # noqa: F401 (table auto-create)
    application.include_router(track_router, tags=["Tracking"])

    # AI + Research expansion (agent-native platform). Routes self-gate on
    # AI_ENABLED / RESEARCH_ENABLED; pricing + discovery always advertise them.
    from app.api.ai import router as ai_router
    from app.api.research import router as research_router
    application.include_router(ai_router, tags=["AI"])
    application.include_router(research_router, tags=["Research"])

    application.include_router(discovery_router, tags=["Discovery"])
    application.include_router(bazaar_router, tags=["Bazaar / MCP"])

    # Free domain presets + dry-run simulation (v1.3)
    from app.api.presets import router as presets_router
    application.include_router(presets_router)
    from app.api.simulate import router as simulate_router
    application.include_router(simulate_router)

    # Internal-only metrics (revenue). 503 unless INTERNAL_TOKEN is set.
    from app.api.internal import router as internal_router
    application.include_router(internal_router, tags=["Internal"])

    if (settings.X402_ENABLED and settings.WALLET_ADDRESS) or settings.PRIVATE_API_KEY:
        try:
            from app.middleware.x402 import X402Middleware
            from app.middleware.x402_rate_limit import X402RateLimitMiddleware

            application.include_router(audit_router, tags=["x402 Audit & Trust"])

            # Inner -> outer: rate limit, payment gate, headers, input validation.
            application.add_middleware(X402Middleware)
            from app.middleware.headers import CortexHeadersMiddleware
            application.add_middleware(CortexHeadersMiddleware)
            from app.middleware.validate import InputValidationMiddleware
            application.add_middleware(InputValidationMiddleware)
            application.add_middleware(X402RateLimitMiddleware)
            logger.info("x402 payment gateway enabled (POST /v1/optimize)")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to initialize x402 payment gateway: {e}")
    else:
        logger.warning("x402 disabled or WALLET_ADDRESS unset — /v1/optimize will not be payable")

    # ---- system / static ---------------------------------------------------
    @application.get("/metrics", include_in_schema=False, tags=["System"])
    async def metrics():
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @application.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        p = os.path.join(SITE_DIR, "favicon.jpg")
        if not os.path.exists(p):
            p = "static/favicon.jpg"
        return FileResponse(p, media_type="image/jpeg")

    @application.get("/", include_in_schema=False)
    async def home():
        return FileResponse(os.path.join(SITE_DIR, "index.html"))

    @application.get("/og.svg", include_in_schema=False)
    async def _og():
        return FileResponse(os.path.join(SITE_DIR, "og.svg"), media_type="image/svg+xml")

    @application.get("/robots.txt", include_in_schema=False)
    async def _robots():
        return FileResponse(os.path.join(SITE_DIR, "robots.txt"), media_type="text/plain")

    @application.get("/sitemap.xml", include_in_schema=False)
    async def _sitemap():
        return FileResponse(os.path.join(SITE_DIR, "sitemap.xml"), media_type="application/xml")

    @application.get("/benchmarks.html", include_in_schema=False, tags=["System"])
    async def benchmarks_page():
        return FileResponse(os.path.join(SITE_DIR, "benchmarks.html"), media_type="text/html")

    @application.get("/changelog", include_in_schema=False, tags=["System"])
    async def changelog_page():
        return FileResponse(os.path.join(SITE_DIR, "changelog.html"), media_type="text/html")

    @application.get("/health", status_code=status.HTTP_200_OK, tags=["System"])
    async def health_check():
        db_status = "unhealthy"
        try:
            from sqlalchemy import text

            from app.database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
            db_status = "healthy"
        except Exception:  # noqa: BLE001
            pass
        from app.solvers import registry
        import asyncio as _asyncio
        # availability_summary() probes cloud providers (IBM/Braket discovery
        # can take 15s+) — never run it on the event loop or /health becomes
        # a self-DoS that blocks every other request.
        backends = await _asyncio.to_thread(registry.availability_summary)
        return {
            "status": "healthy" if db_status == "healthy" else "degraded",
            "database": db_status,
            "mcp": "running" if _mcp_alive() else "down",
            "backends": backends,
        }

    def _mcp_alive() -> bool:
        """True when the MCP server (separate process, :3100) answers.
        urllib raises HTTPError for 4xx; any <500 response proves life."""
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen("http://127.0.0.1:3100/mcp", timeout=2) as r:
                return r.status < 500
        except urllib.error.HTTPError as e:
            return e.code < 500
        except Exception:
            return False

    # Root-level static assets (Next export leftovers kept for compatibility)
    @application.get("/{asset}", include_in_schema=False)
    async def _site_asset(asset: str):
        allowed = (".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp", ".txt", ".xml", ".json", ".woff2", ".woff")
        if not asset.lower().endswith(allowed):
            raise HTTPException(status_code=404)
        path = os.path.join(SITE_DIR, asset)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404)
        return FileResponse(path)

    if os.path.isdir(os.path.join(SITE_DIR, "_next")):
        application.mount("/_next", StaticFiles(directory=os.path.join(SITE_DIR, "_next")), name="next-assets")

    return application


app = create_app(True)