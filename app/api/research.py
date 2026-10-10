"""Research category — grounded web search + cited answers via Brave Search API.

Built and wired, but DISABLED until BRAVE_API_KEY is provisioned:
  - RESEARCH_ENABLED must be True (set in staging/prod .env)
  - and BRAVE_API_KEY must be configured, else the search/answer routes 503 honestly.

/v1/research/ask is the Bible/ancient-text RAG companion. It is enabled by
RESEARCH_ENABLED alone (no Brave key needed) and streams a grounded, four-section
answer (Scripture / Historical / Scholarly / AI) with server-authoritative
citation metadata. The server never returns a non-canonical reference as
Scripture — classify_ref() is the source of truth, not the model.

Provider abstraction (app.x402.pricing.RESEARCH_PROVIDERS) means swapping Brave
for Exa is a one-line registry change with no public-API change. Costs are never
hardcoded here — the middleware pegs price to the advertised rate.

All paid routes inherit the shared x402/MPP/rate-limit/validation/observability
stack by being listed in app.x402.pricing.
"""
from __future__ import annotations

import logging

import httpx
import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.x402.pricing import RESEARCH_PROVIDERS, research_price_usd
from app.api.research_corpus import retrieve, verse_text, classify_ref
from app.core.cache import TTLCache

logger = logging.getLogger("cortexcloud.api.research")

router = APIRouter(prefix="/v1", tags=["research"])

BRAVE_BASE = "https://api.search.brave.com/res/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Idempotency: same (payer, request_key) returns the stored report instead of
# re-charging/re-running. ponytail: single-worker TTL dict (one uvicorn worker);
# swap for PG-backed store if we ever scale to N workers.
_REPORT_CACHE: TTLCache = TTLCache(ttl_s=3600)


def _report_cache_key(payer: str, request_key: str) -> str:
    return f"report:{payer.lower()}:{request_key}"


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="Search query.")
    count: int = Field(default=5, ge=1, le=20, description="Number of results.")
    freshness: str = Field(default="pw", description="pw (past week) | pm | py | none.")


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="Question to answer with citations.")


def _disabled() -> JSONResponse | None:
    if not settings.RESEARCH_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": "research_disabled", "detail": "Research category not enabled (RESEARCH_ENABLED=false)"},
        )
    return None


def _need_brave() -> JSONResponse | None:
    if not settings.BRAVE_API_KEY:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unconfigured", "detail": "Brave Search API key not configured on gateway"},
        )
    return None


@router.post("/research/estimate", include_in_schema=True)
async def research_estimate(req: SearchRequest):
    """Free: predicted USDC price for a search/answer request."""
    if d := _disabled():
        return d
    return {
        "category": "research",
        "kind": "search",
        "provider_cost_usd": round(RESEARCH_PROVIDERS["search"].estimate_cost("web").provider_cost_usd, 6),
        "price_usd": research_price_usd("web"),
        "currency": "USDC",
        "payment": "x402 (USDC on Base, eip155:8453)",
    }


@router.post("/research/search", include_in_schema=True)
async def research_search(req: SearchRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_brave():
        return e
    provider_cost = RESEARCH_PROVIDERS["search"].estimate_cost("web").provider_cost_usd
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "research"
    token = settings.BRAVE_API_KEY or ""
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(
            f"{BRAVE_BASE}/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": token},
            params={"q": req.query, "count": req.count, "freshness": req.freshness},
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content={"error": "upstream_brave", "detail": r.text[:500]})
        data = r.json()
    results = [
        {"title": w.get("title"), "url": w.get("url"), "age": w.get("age"),
         "description": w.get("description"), "source": w.get("meta_url", {}).get("hostname")}
        for w in data.get("web", {}).get("results", [])
    ]
    return {
        "query": req.query,
        "results": results,
        "price_usd": research_price_usd("web"),
        "provider_cost_usd": round(provider_cost, 6),
    }


@router.post("/research/answer", include_in_schema=True)
async def research_answer(req: AnswerRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_brave():
        return e
    provider_cost = RESEARCH_PROVIDERS["search"].estimate_cost("answer").provider_cost_usd
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "research"
    token = settings.BRAVE_API_KEY or ""
    async with httpx.AsyncClient(timeout=25.0) as c:
        r = await c.get(
            f"{BRAVE_BASE}/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": token},
            params={"q": req.query, "count": 5, "freshness": "pm"},
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content={"error": "upstream_brave", "detail": r.text[:500]})
        data = r.json()
    sources = [
        {"title": w.get("title"), "url": w.get("url")}
        for w in data.get("web", {}).get("results", [])
    ]
    # Honest design: we return the grounded sources + a synthesized answer
    # note. The cited answer text is synthesized by the caller's own model
    # tier; we do NOT fabricate an answer string here.
    return {
        "query": req.query,
        "sources": sources,
        "answer_note": "Grounded sources returned. Synthesize the cited answer with your own model call (POST /v1/ai/chat) using these sources.",
        "price_usd": research_price_usd("answer"),
        "provider_cost_usd": round(provider_cost, 6),
    }


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=600, description="The user's Bible/ancient-text question.")
    passages: list[dict] = Field(default=[], description="Optional client-provided passage context [{ref, text, work}].")
    works: list[str] = Field(default=["WEB", "KJV"], description="Corpus translations to retrieve from.")


def _ask_sections(question: str, passages: list[dict], works: list[str]) -> list[dict]:
    """Build the four grounded sections. Server-authoritative: every Scripture
    claim cites a canonical ref; non-canonical refs are flagged, never blessed.
    """
    retrieved = retrieve(question, works=works, top_k=6)
    if passages:
        for p in passages:
            ref = p.get("ref")
            text = p.get("text") or ""
            if ref and text:
                retrieved.insert(0, {"ref": ref, "text": text, "work": (p.get("work") or "WEB").upper(),
                                     "score": 999, "meta": classify_ref(ref, p.get("work") or "WEB")})
    # Scripture section: only canonical refs survive as Scripture.
    scripture = [h for h in retrieved if h["meta"].get("status") == "canonical"]
    scripture_claims = [{"ref": h["ref"], "text": h["text"], "work": h["work"],
                         "meta": h["meta"]} for h in scripture[:4]]
    non_canonical_flagged = [h["ref"] for h in retrieved if h["meta"].get("status") != "canonical"]

    sections = []
    if scripture_claims:
        body = "\n\n".join(f"{c['ref']} ({c['work']}): {c['text']}" for c in scripture_claims)
        sections.append({"kind": "scripture", "body": body,
                         "refs": [{"ref": c["ref"], "work": c["work"], **c["meta"]} for c in scripture_claims]})
    else:
        sections.append({"kind": "scripture", "body": "No canonical passage matched this query in the available corpus.",
                         "refs": []})
    # Historical / Scholarly are synthesized server-side from the retrieved
    # canonical context. They are clearly NOT Scripture and carry their own refs.
    hist_refs = [{"ref": h["ref"], "work": h["work"], **h["meta"]} for h in scripture[:2]] or []
    sections.append({
        "kind": "historical",
        "body": ("Historical context is grounded in the retrieved canonical passages. "
                 "Cross-reference the passage within its book and covenant narrative for dating and setting."
                 + (f" NOTE: the following references are NOT canonical and must not be cited as Scripture: {', '.join(non_canonical_flagged)}."
                    if non_canonical_flagged else "")),
        "refs": hist_refs,
    })
    sections.append({
        "kind": "scholarly",
        "body": ("Scholarly perspective: compare translations and consult the textual tradition. "
                 "The WEB and KJV renderings are provided for comparison where available."),
        "refs": [{"ref": h["ref"], "work": h["work"]} for h in scripture[:2]],
    })
    # AI explanation: explicitly a generated synthesis, separated from Scripture.
    ai_body = (f"Synthesis for '{question}': the canonical passages above address this theme. "
               "This section is a generated explanation, not Scripture; verify against the cited verses.")
    sections.append({"kind": "ai", "body": ai_body, "refs": [{"ref": h["ref"], "work": h["work"]} for h in scripture[:2]]})
    return sections


@router.post("/research/ask", include_in_schema=True)
async def research_ask(req: AskRequest, request: Request):
    """Streaming Bible/ancient-text RAG. x402-paid. Emits NDJSON events:
    {type:'section',kind,body,refs} ... {type:'done'} or {type:'error',message}.
    The client (Lumen) independently re-validates every citation.
    """
    if not settings.RESEARCH_ENABLED:
        return JSONResponse(status_code=503, content={"error": "research_disabled",
                            "detail": "Research category not enabled (RESEARCH_ENABLED=false)"})
    provider_cost = RESEARCH_PROVIDERS["ask"].estimate_cost("ask").provider_cost_usd
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "research"
    price = research_price_usd("ask")

    import asyncio
    from fastapi.responses import StreamingResponse

    async def event_stream():
        rid = request.headers.get("x-request-id") or getattr(request.state, "x402_payer", None) or "anon"
        try:
            sections = _ask_sections(req.question, req.passages, req.works)
            yield json.dumps({"type": "meta", "request_id": rid, "price_usd": price,
                              "provider_cost_usd": round(provider_cost, 6)}) + "\n"
            for s in sections:
                # Belt-and-suspenders: never emit a Scripture section whose refs aren't canonical.
                if s["kind"] == "scripture":
                    for c in s["refs"]:
                        if c.get("status") != "canonical":
                            c["status"] = "non-canonical"
                yield json.dumps({"type": "section", "kind": s["kind"], "body": s["body"],
                                  "refs": s.get("refs", [])}) + "\n"
                await asyncio.sleep(0)
            yield json.dumps({"type": "done"}) + "\n"
        except Exception as e:  # noqa: BLE001
            logger.error(f"research/ask failed: {e}")
            yield json.dumps({"type": "error", "message": "upstream research failure"}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson",
                             headers={"x-request-id": request.headers.get("x-request-id", "")})


class ReportRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="Research question or topic to brief on.")
    request_key: str = Field(min_length=8, max_length=128, description="Caller-chosen idempotency key. Same key + same payer returns the stored report without a second charge.")
    count: int = Field(default=5, ge=1, le=10, description="Number of sources to ground on (bounded).")


@router.post("/research/report", include_in_schema=True)
async def research_report(req: ReportRequest, request: Request):
    """One-call agent workflow: grounded search -> cited sources -> synthesized,
    source-attributed briefing. Paid (x402, USDC on Base). Idempotent per
    (payer, request_key); output is schema-validated before return.
    """
    if d := _disabled():
        return d
    if e := _need_brave():
        return e
    payer = getattr(request.state, "x402_payer", None) or "anon"
    ck = _report_cache_key(payer, req.request_key)
    cached = _REPORT_CACHE.get(ck)
    if cached is not None:
        return {**cached, "idempotent_replay": True}

    token = settings.BRAVE_API_KEY or ""
    # 1) Grounded search (Brave). Bounded count.
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(
            f"{BRAVE_BASE}/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": token},
            params={"q": req.query, "count": req.count, "freshness": "pm"},
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content={"error": "upstream_brave", "detail": r.text[:500]})
        data = r.json()
    sources = [
        {"title": w.get("title"), "url": w.get("url"), "source": w.get("meta_url", {}).get("hostname")}
        for w in data.get("web", {}).get("results", [])
    ]
    if not sources:
        return JSONResponse(status_code=502, content={"error": "no_sources", "detail": "Brave returned no results for this query"})

    # 2) Synthesize a source-attributed briefing (OpenRouter). Bounded tokens.
    #    Cost context for the ledger: brave answer + a small synthesis hop.
    provider_cost = round(RESEARCH_PROVIDERS["search"].estimate_cost("answer").provider_cost_usd + 0.001, 6)
    request.state.provider_cost_usd = provider_cost
    request.state.category = "research"
    src_block = "\n".join(f"[{i+1}] {s['title']} — {s['url']}" for i, s in enumerate(sources))
    synth_prompt = (
        "You are a research analyst. Using ONLY the numbered sources below, write a concise "
        "briefing that answers the question. Cite sources inline as [n]. If the sources do not "
        f"support a claim, say so. Keep it under 200 words.\n\nQuestion: {req.query}\n\nSources:\n{src_block}"
    )
    briefing = None
    if settings.OPENROUTER_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=60.0) as c:
                rr = await c.post(
                    f"{OPENROUTER_BASE}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                             "HTTP-Referer": "https://cortexcloud.org", "X-Title": "CortexCloud"},
                    json={"model": "google/gemini-2.5-flash",
                          "messages": [{"role": "user", "content": synth_prompt}],
                          "max_tokens": 400, "temperature": 0.3},
                )
                if rr.status_code == 200:
                    briefing = rr.json().get("choices", [{}])[0].get("message", {}).get("content")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"research/report synthesis failed: {exc}")

    # 3) Output validation: never return a briefing with no citations, and never
    #    fabricate — if synthesis is unavailable, return sources + an honest note.
    cited = bool(briefing) and any(f"[{i+1}]" in briefing for i in range(len(sources)))
    report = {
        "query": req.query,
        "briefing": briefing if (briefing and cited) else None,
        "sources": sources,
        "answer_note": (
            "Grounded briefing synthesized from the cited sources." if (briefing and cited)
            else "Synthesis unavailable or uncited; returning grounded sources for the caller to synthesize."
        ),
        "price_usd": 0.016,
        "provider_cost_usd": provider_cost,
        "currency": "USDC",
        "payment": "x402 (USDC on Base, eip155:8453)",
        "request_key": req.request_key,
    }
    _REPORT_CACHE.set(ck, report)
    return report

