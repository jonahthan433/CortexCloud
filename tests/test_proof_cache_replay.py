"""H1 regression: a settled proof may be re-served exactly once (client
timeout retry); every replay after that must be rejected. Run: pytest tests/test_proof_cache_replay.py
"""
import asyncio

from app.core.cache import cache_proof, proof_consume


def test_proof_single_retry_then_reject():
    sig = "proof-abc"

    async def run():
        await cache_proof(sig)
        return [await proof_consume(sig), await proof_consume(sig)]

    first, second = asyncio.run(run())
    assert first is True, "first retry of a settled proof must be served"
    assert second is False, "second replay must fall through to the nonce check"


if __name__ == "__main__":
    test_proof_single_retry_then_reject()
    print("ok")
