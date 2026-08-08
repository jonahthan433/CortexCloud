"""API surface: estimate (free), 402 challenge on optimize, jobs, backends, capabilities."""

import base64
import json

import pytest


async def test_estimate_free(client, qb_small):
    r = await client.post("/v1/estimate", json=qb_small)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["problem"]["n"] == 4
    assert body["recommendation"]["mode"] in ("classical", "hybrid", "quantum")
    assert "estimated_price_usd" in body["recommendation"]
    # n=4 must NEVER recommend simulated-annealing over brute-force
    assert body["recommendation"]["solver_id"] == "brute-force"
    assert body["evidence"]["basis"] in ("model", "measured")


async def test_estimate_keeps_quantum_unpromoted(client):
    # Without Origin token + benchmark rows, quantum must not appear
    # as a recommendation or alternative.
    prob = {"problem_type": "qubo", "n": 6,
            "data": {"linear": [float(i) for i in range(1, 7)],
                     "quadratic": {"0,1": -1.0, "1,2": -1.0, "2,3": -1.0, "3,4": -1.0, "4,5": -1.0}}}
    r = await client.post("/v1/estimate", json=prob)
    body = r.json()
    rec_modes = {body["recommendation"]["mode"]}
    alt_modes = {alt["mode"] for alt in body["alternatives"]}
    assert "quantum" not in rec_modes | alt_modes, body
    assert any("token" in c for c in body["caveats"]) or body["evidence"]["benchmark_rows"] == 0


async def test_optimize_requires_payment(client, qb_small):
    r = await client.post("/v1/optimize", json={"mode": "auto", "problem": qb_small})
    assert r.status_code == 402, r.text
    assert "payment-required" in r.headers
    pr = json.loads(base64.b64decode(r.headers["payment-required"]))
    assert pr["x402Version"] in ("1.0", 2)
    opts = pr.get("accepts") or pr.get("paymentOptions") or [pr]
    payee = opts[0].get("payTo") or pr.get("recipient")
    assert payee and str(payee).startswith("0x")
    assert pr["resource"]["url"].endswith("/v1/optimize")
    # classical mode = $0.05 = 50000 atomic USDC (6 decimals); amount is a string
    assert opts[0]["amount"] == "50000"
    exts = pr.get("extensions", {})
    assert "bazaar" in exts


async def test_optimize_bad_signature_rejected(client, qb_small):
    r = await client.post(
        "/v1/optimize",
        json={"mode": "classical", "problem": qb_small},
        headers={"payment-signature": base64.b64encode(b"junk").decode(), "payment-message-prefix": "fa466156121e4a7ab38a5a225c78f3b0"},
    )
    assert r.status_code == 402, r.text


async def test_backends_and_capabilities(client):
    for path in ("/v1/backends", "/v1/capabilities"):
        r = await client.get(path)
        assert r.status_code == 200, r.text
    backends = (await client.get("/v1/backends")).json()["backends"]
    ids = {b["id"] for b in backends}
    assert {"brute-force", "simulated-annealing", "qaoa-local"} <= ids
    for b in backends:
        assert "available" in b
    caps = (await client.get("/v1/capabilities")).json()
    assert caps["payments"]["scheme"] == "x402"
    assert "POST /v1/optimize" in caps["discovery"][1] or "/v1/optimize" in json.dumps(caps)


async def test_job_lifecycle(client, qb_small):
    import asyncio

    from app.optimizer.problem import ProblemInput
    from app.optimizer.runner import create_job, schedule

    job_id = await create_job(ProblemInput(**qb_small), "classical", 0.02)
    schedule(job_id)
    for _ in range(50):
        r = await client.get(f"/v1/jobs/{job_id}")
        assert r.status_code == 200, r.text
        if r.json()["status"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.1)
    body = r.json()
    assert body["status"] == "succeeded", body
    assert "result" in body
    assert body["result"]["objective"] <= 8.0  # sane bound for the sample
    assert body["result"]["solution"] is not None


async def test_job_404(client):
    r = await client.get("/v1/jobs/nonexistent-id")
    assert r.status_code == 404


async def test_nonce_replay_rejected(client):
    """EIP-3009 single-use nonce: second claim is a replay."""
    from app.core.nonce import nonce_seen

    n = "0x" + "deadbeef" * 4 + str(id(client))
    assert await nonce_seen(n) is False
    assert await nonce_seen(n) is True  # replayed


# --- abuse controls -------------------------------------------------
async def test_oversized_problem_rejected(client):
    prob = {"problem_type": "qubo", "n": 5001, "data": {"linear": [0.0] * 5001}}
    r = await client.post("/v1/estimate", json=prob)
    assert r.status_code == 422, r.text


async def test_invalid_mode_rejected(client, qb_small):
    # Unpaid requests to the paid route get the 402 challenge first (x402
    # contract); after payment the route itself rejects bad modes with 422.
    r = await client.post("/v1/optimize", json={"mode": "neural", "problem": qb_small})
    assert r.status_code in (402, 422), r.text


async def test_invalid_quadratic_key_rejected(client):
    prob = {"problem_type": "qubo", "n": 3,
            "data": {"linear": [0.0, 0.0, 0.0], "quadratic": {"7,9": 1.0}}}  # keys out of range
    r = await client.post("/v1/estimate", json=prob)
    assert r.status_code == 422, r.text


async def test_quantum_job_fails_honestly_without_backend(client, qb_small):
    # quantum requested but no backend configured -> failed, never fake
    import asyncio

    from app.optimizer.problem import ProblemInput
    from app.optimizer.runner import create_job, schedule

    job_id = await create_job(ProblemInput(**qb_small), "quantum", 0.85)
    schedule(job_id)
    for _ in range(50):
        r = await client.get(f"/v1/jobs/{job_id}")
        if r.json()["status"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.1)
    body = r.json()
    assert body["status"] == "failed", body
    # honest failure, never fake: either no solver or the live-execution gate
    assert (
        "no available solver" in body["error"].lower()
        or "quantum" in body["error"].lower()
    )