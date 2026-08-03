"""S6 auth: ECDSA P-256 server keypair + canonical response signing."""
import os
import base64
import hashlib
import threading

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature

_KEY_PATH = "/opt/CortexCloudAPI/server_ecdsa.key"
_lock = threading.Lock()
_private_key = None


def _get_or_create() -> ec.EllipticCurvePrivateKey:
    global _private_key
    if _private_key is not None:
        return _private_key
    with _lock:
        if _private_key is not None:
            return _private_key
        if os.path.exists(_KEY_PATH):
            with open(_KEY_PATH, "rb") as f:
                _private_key = serialization.load_pem_private_key(f.read(), password=None)
        else:
            _private_key = ec.generate_private_key(ec.SECP256R1())
            with open(_KEY_PATH, "wb") as f:
                f.write(_private_key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ))
            os.chmod(_KEY_PATH, 0o600)
    return _private_key


def get_pubkey_pem() -> str:
    return _get_or_create().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def sign_payload(payload: bytes) -> str:
    der = _get_or_create().sign(hashlib.sha256(payload).digest(), ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(der).decode()


def verify_payload(payload: bytes, sig_b64: str) -> bool:
    try:
        _get_or_create().public_key().verify(
            base64.b64decode(sig_b64), hashlib.sha256(payload).digest(), ec.ECDSA(hashes.SHA256())
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False