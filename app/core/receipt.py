"""Cryptographic execution receipts + shared job payload builder.

Receipts bind result <-> metadata <-> time with an HMAC-SHA256 signature
(RECEIPT_SIGNING_KEY). Built at READ time from stored job state — no DB
schema change. If the key is unset the receipt is emitted unsigned with a
signed:false flag (agents can still hash-verify; signing is the enterprise
upgrade).
"""

from __future__ import annotations

import hashlib
import hmac
import json

from app.core.config import settings


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_hex(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def job_payload(job) -> dict:
    """The canonical job representation shared by GET /v1/jobs/{id} and webhooks."""
    payload = {
        "job_id": job.id,
        "status": job.status,
        "mode": job.mode,
        "problem_type": job.problem_type,
        "n": job.n,
        "backend": job.backend,
        "algorithm": job.algorithm,
        "price_usd": float(job.price_usd) if job.price_usd is not None else None,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    if job.status in ("succeeded", "failed"):
        payload["receipt"] = build_receipt(job)
    return payload


def build_receipt(job) -> dict:
    result = job.result or {}
    meta = result.get("meta") or {} if isinstance(result, dict) else {}
    runtime_ms = None
    if job.started_at and job.finished_at:
        runtime_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)

    fields = {
        "schema_version": 1,
        "job_id": job.id,
        "problem_type": job.problem_type,
        "n": job.n,
        "mode": job.mode,
        "algorithm": job.algorithm,
        "backend": job.backend,
        "runtime_ms": runtime_ms,
        "convergence": {
            "objective": (result or {}).get("objective"),
            "evaluations": meta.get("evaluations") if isinstance(meta, dict) else None,
            "quality_note": (result or {}).get("quality_note"),
        },
        # request JSONB holds the exact submitted problem -> real input binding
        "input_sha256": _sha256_hex((job.request or {}).get("problem", {})),
        "output_sha256": _sha256_hex(result),
        "signed_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    key = settings.RECEIPT_SIGNING_KEY
    if key:
        fields["signature"] = hmac.new(
            key.encode(), canonical_json(fields).encode(), hashlib.sha256
        ).hexdigest()
        fields["signed"] = True
    else:
        fields["signature"] = None
        fields["signed"] = False
    return fields


def verify_receipt(receipt: dict, key: str) -> bool:
    """Independent verification for agents/servers holding the shared key."""
    sig = receipt.pop("signature", None)
    signed = receipt.pop("signed", None)
    if not sig or not signed:
        return False
    expected = hmac.new(key.encode(), canonical_json(receipt).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
