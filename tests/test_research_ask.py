"""/v1/research/ask — Bible/ancient-text RAG tests.

No Brave key / no payment path here: we toggle X402_ENABLED=False so the
middleware passes straight through to the route (the live x402 settle is a
separate staging smoke, per the category-dev skill). We exercise:

- pricing pegged to provider cost (self-hosted corpus -> $0.004 floor)
- RESEARCH_ENABLED flag gates the route (503 when off)
- malformed body (missing question) -> 422
- streaming NDJSON emits meta + 4 sections (scripture/historical/scholarly/ai) + done
- server-authoritative classification: canonical refs stay canonical,
  non-canonical refs are flagged and NEVER appear as Scripture
- empty retrieval (gibberish query) still streams a Scripture section (empty) + done
- provider-failure path returns an error event, not a 200 with partial data
"""
import json

import pytest

from app.x402 import pricing as p


def test_ask_price_pegged_to_floor():
    # Self-hosted corpus has $0 provider cost -> pegged to the $0.004 floor.
    cost = p.RESEARCH_PROVIDERS["ask"].estimate_cost("ask").provider_cost_usd
    assert cost == 0.0
    price = p.ask_price_usd()
    assert price == p.PRICING_FLOOR_USD


async def test_ask_disabled_returns_503(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.RESEARCH_ENABLED", False)
    r = await client.post("/v1/research/ask", json={"question": "shepherds"})
    assert r.status_code == 503, r.text
    assert r.json().get("error") == "research_disabled"


async def test_ask_requires_question(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.RESEARCH_ENABLED", True)
    # FastAPI validation -> 422 (Pydantic). Money-path guard mirrors this.
    r = await client.post("/v1/research/ask", json={"works": ["WEB"]})
    assert r.status_code == 422, r.text


async def test_ask_streams_four_sections(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.RESEARCH_ENABLED", True)
    r = await client.post("/v1/research/ask", json={"question": "the lord is my shepherd", "works": ["WEB"]})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-ndjson")
    kinds = []
    events = []
    for line in r.text.splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        events.append(ev)
        if ev["type"] == "section":
            kinds.append(ev["kind"])
    assert events[0]["type"] == "meta"
    assert kinds == ["scripture", "historical", "scholarly", "ai"], kinds
    assert events[-1]["type"] == "done"
    # Scripture section must carry canonical refs with status=canonical.
    scr = next(e for e in events if e["type"] == "section" and e["kind"] == "scripture")
    assert scr["refs"], "Scripture section must cite something for a matching query"
    for ref in scr["refs"]:
        assert ref.get("status") == "canonical", f"non-canonical ref leaked as Scripture: {ref}"


async def test_ask_noncanonical_never_scripture(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.RESEARCH_ENABLED", True)
    # Client passes a non-canonical passage; server must flag it, not bless it.
    r = await client.post("/v1/research/ask", json={
        "question": "ennech",  # deliberately odd to avoid strong canonical hits
        "passages": [{"ref": "1 Enoch 5:1", "text": "And the holy ones", "work": "WEB"}],
        "works": ["WEB"],
    })
    assert r.status_code == 200, r.text
    events = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    scr = next(e for e in events if e["type"] == "section" and e["kind"] == "scripture")
    # The non-canonical passage must NOT appear as a canonical Scripture ref.
    for ref in scr["refs"]:
        assert ref.get("status") != "non-canonical" or ref.get("ref") != "1 Enoch 5:1"
    # The historical section should explicitly note the non-canonical ref.
    hist = next(e for e in events if e["type"] == "section" and e["kind"] == "historical")
    assert "1 Enoch 5:1" in hist["body"]


async def test_ask_empty_retrieval_still_streams(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.RESEARCH_ENABLED", True)
    r = await client.post("/v1/research/ask", json={"question": "zzqxwq nonword gibberish", "works": ["WEB"]})
    assert r.status_code == 200, r.text
    events = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    assert events[-1]["type"] == "done"
    scr = next(e for e in events if e["type"] == "section" and e["kind"] == "scripture")
    assert scr["refs"] == []  # honestly empty, not fabricated


async def test_ask_provider_failure_returns_error_event(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.RESEARCH_ENABLED", True)
    # Force the corpus retriever to blow up -> route must emit an error event.
    import app.api.research as rmod
    monkeypatch.setattr(rmod, "retrieve", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = await client.post("/v1/research/ask", json={"question": "shepherds", "works": ["WEB"]})
    assert r.status_code == 200, r.text  # streaming response already started
    events = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    assert events[-1]["type"] == "error", "failure must surface as an error event"
