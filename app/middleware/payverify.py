"""Local x402 payment-proof verification (Section 1 hardening).

All verification that used to be delegated to the CDP facilitator /validate
round-trip now runs IN-PROCESS first: ECDSA recovery of the signer from the
EIP-712 TransferAuthorization, amount >= required, chainId == 8453, asset ==
canonical USDC on Base, payTo == WALLET_ADDRESS, and the validBefore expiry
window (30s skew / 5min max future). CDP /settle still broadcasts the
on-chain transfer (covers gas) — that is the only remaining RPC.

Every failure returns (False, reason). Caller MUST answer 402 and never fall
through to the upstream call.
"""
import base64
import hmac
import json
import time

from eth_account import Account
from eth_account.messages import encode_typed_data

from app.core.config import settings
from app.x402.pricing import usd_to_usdc_atomic

# Canonical USDC on Base mainnet (6 decimals). Mirrors app/middleware/x402.py.
USDC_ON_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CHAIN_ID_BASE = 8453

# EIP-3009 TransferAuthorization (EIP-712). The client (CDP SDK) signs exactly
# this struct; the domain is built from the accepted asset's extra.name/version
# ("USD Coin" / "2") + verifyingContract == USDC, chainId == 8453.
_AUTH_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "TransferAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ],
}


def _ct_eq(a: str, b: str) -> bool:
    """Constant-time hex comparison (lowercased)."""
    return hmac.compare_digest(a.lower(), b.lower())


def _chain_id_from_network(network: str) -> int | None:
    """Parse 'eip155:8453' (or bare int) -> 8453. None if unparseable."""
    if not network:
        return None
    s = str(network).strip()
    if s.isdigit():
        return int(s)
    if s.startswith("eip155:"):
        try:
            return int(s.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
    return None


def _extract_sig(auth: dict) -> bytes | None:
    """65-byte (r||s||v) from authorization 'signature' (0x-hex) or v/r/s."""
    sig = auth.get("signature") or auth.get("sig")
    if sig:
        s = str(sig)
        if s.startswith("0x"):
            s = s[2:]
        try:
            raw = bytes.fromhex(s)
            if len(raw) == 65:
                return raw
        except ValueError:
            return None
    # v/r/s split form
    if auth.get("r") and auth.get("s"):
        try:
            r = str(auth["r"]).removeprefix("0x")
            s = str(auth["s"]).removeprefix("0x")
            v = int(auth.get("v", 27))
            rid = 0 if v in (27, 28) else (v - 27 if v >= 27 else v)
            if 0 <= rid <= 3:
                return bytes.fromhex(r.zfill(64) + s.zfill(64) + format(rid, "02x"))
        except (ValueError, TypeError):
            return None
    return None


def verify_proof(payment_signature: str, price_str: str, path: str) -> tuple[bool, str, dict]:
    """Verify the decoded x402 v2 payload in-process. Returns (ok, reason, auth).

    auth carries the caller-facing fields (from/nonce/value/validBefore) for
    rate limiting and audit logging. Raises nothing: any parse error is a
    (False, reason) — fail closed.
    """
    try:
        payload = json.loads(base64.b64decode(payment_signature).decode())
    except Exception:
        return False, "malformed payment signature", {}

    accepted = payload.get("accepted") or (payload.get("accepts") or [{}])[0] or {}
    auth = (payload.get("payload") or {}).get("authorization") or {}

    # 1. Amount: never trust the caller's stated price — compare against OUR
    #    price table (the same required the 402 challenge carried).
    required = usd_to_usdc_atomic(price_str)
    try:
        paid = int(str(accepted.get("amount") or auth.get("value") or 0))
    except (ValueError, TypeError):
        return False, "invalid amount", auth
    if paid < int(required):
        return False, f"amount below required ({paid} < {required})", auth

    # 2. Chain ID: Base mainnet only, never testnets.
    chain = _chain_id_from_network(accepted.get("network"))
    if chain != CHAIN_ID_BASE:
        return False, f"unsupported chain (got {accepted.get('network')})", auth

    # 3. Asset: canonical USDC on Base only.
    asset = str(accepted.get("asset") or "")
    if not _ct_eq(asset, USDC_ON_BASE):
        return False, "unsupported payment asset", auth

    # 4. Recipient: must be OUR wallet, checked before any RPC.
    pay_to = str(accepted.get("payTo") or auth.get("to") or "")
    if not settings.WALLET_ADDRESS or not (
        _ct_eq(pay_to, settings.WALLET_ADDRESS)
        or (settings.WALLET_ADDRESS_2 and _ct_eq(pay_to, settings.WALLET_ADDRESS_2))
    ):
        return False, "recipient mismatch", auth

    # 5. Expiry: reject past (30s skew) and >5min future (proof stockpiling).
    valid_before = auth.get("validBefore")
    if valid_before is None:
        return False, "missing validBefore", auth
    try:
        vb = int(valid_before)
    except (ValueError, TypeError):
        return False, "invalid validBefore", auth
    now = int(time.time())
    if vb < now - 30:
        return False, "proof expired", auth
    if vb > now + 300:
        return False, "proof valid too far in the future", auth

    # 6. Local ECDSA recovery: recover the signer from the EIP-712 typed data
    #    and require it matches authorization.from. Never outsourced.
    sig = _extract_sig(auth)
    if not sig:
        return False, "missing signature", auth
    try:
        domain = {
            "name": (accepted.get("extra") or {}).get("name", "USD Coin"),
            "version": (accepted.get("extra") or {}).get("version", "2"),
            "chainId": CHAIN_ID_BASE,
            "verifyingContract": USDC_ON_BASE,
        }
        message = {
            "from": auth.get("from"),
            "to": auth.get("to"),
            "value": auth.get("value", "0"),
            "validAfter": auth.get("validAfter", "0"),
            "validBefore": str(vb),
            "nonce": auth.get("nonce"),
        }
        typed = {
            "types": _AUTH_TYPES,
            "primaryType": "TransferAuthorization",
            "domain": domain,
            "message": message,
        }
        signable = encode_typed_data(full_message=typed)
        recovered = Account.recover_message(signable, signature=sig)
    except Exception:
        return False, "signature verification error", auth
    if not auth.get("from") or not _ct_eq(recovered, auth["from"]):
        return False, "signature does not match payer", auth

    return True, "", auth
