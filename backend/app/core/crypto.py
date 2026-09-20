import json
import hashlib
import os
from typing import Any, Dict, Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from app.core.config import settings
from app.core.demo_gate import demo_mode_enabled


# The keypair below is published in this repository and has been since it was
# first added, so it is not a secret. Anything it signs is a demonstration
# artefact: a verifier who accepts it is accepting the repository, not a
# person, and it cannot establish who signed anything. It is used only while
# ENABLE_DEMO_MODE is on. Outside demo mode a keypair must come from
# configuration, and no default exists.
DEMO_ED25519_PRIVATE_KEY_HEX = "7a4d9526786c2e36b3df516147bb0630b9101d2d3a37c92b23c2a382c40c1110"
DEMO_ED25519_PUBLIC_KEY_HEX = "c5b6fd159a947bcebb906d54f23429f01c4f1767209d6fcd984228ede284fbe7"

_PROD_ENVIRONMENTS = {"production", "prod"}


class SigningKeyNotConfigured(RuntimeError):
    """Raised when signing is attempted with no keypair and no demo gate."""


def _is_production() -> bool:
    return settings.ENVIRONMENT.lower() in _PROD_ENVIRONMENTS


def _resolve_private_key_hex() -> str:
    configured = settings.ED25519_PRIVATE_KEY_HEX
    if configured:
        if _is_production() and configured == DEMO_ED25519_PRIVATE_KEY_HEX:
            raise SigningKeyNotConfigured(
                "ED25519_PRIVATE_KEY_HEX is still the published demonstration "
                "key. Generate a real keypair before serving production traffic."
            )
        return configured
    if demo_mode_enabled():
        return DEMO_ED25519_PRIVATE_KEY_HEX
    raise SigningKeyNotConfigured(
        "No signing key configured. Set ED25519_PRIVATE_KEY_HEX and "
        "ED25519_PUBLIC_KEY_HEX, or enable ENABLE_DEMO_MODE to sign "
        "demonstration records with the published keypair."
    )


def _resolve_public_key_hex() -> str:
    configured = settings.ED25519_PUBLIC_KEY_HEX
    if configured:
        if _is_production() and configured == DEMO_ED25519_PUBLIC_KEY_HEX:
            raise SigningKeyNotConfigured(
                "ED25519_PUBLIC_KEY_HEX is still the published demonstration "
                "key. Generate a real keypair before serving production traffic."
            )
        return configured
    if demo_mode_enabled():
        return DEMO_ED25519_PUBLIC_KEY_HEX
    raise SigningKeyNotConfigured(
        "No verification key configured. Set ED25519_PUBLIC_KEY_HEX, or enable "
        "ENABLE_DEMO_MODE to verify demonstration records with the published "
        "keypair."
    )



def canonicalize_json(data: Any) -> str:
    """
    Produces deterministic, canonical JSON string representation.
    Keys are sorted, no unnecessary whitespace, UTF-8 encoded.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hash(data: Any) -> str:
    """Computes hexadecimal SHA-256 digest of string or bytes."""
    if isinstance(data, str):
        content = data.encode("utf-8")
    elif isinstance(data, (bytes, bytearray)):
        content = data
    else:
        content = canonicalize_json(data).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def sign_canonical_record(record_payload: Dict[str, Any], private_key_hex: str = None) -> Tuple[str, str]:
    """
    Canonicalizes record, computes SHA-256 fingerprint, and signs with Ed25519 private key.
    Returns (fingerprint_hex, signature_hex).
    """
    key_hex = private_key_hex or _resolve_private_key_hex()
    private_key_bytes = bytes.fromhex(key_hex)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    
    canonical_str = canonicalize_json(record_payload)
    fingerprint = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
    
    signature = private_key.sign(fingerprint.encode("utf-8"))
    return fingerprint, signature.hex()


def verify_record_signature(record_payload: Dict[str, Any], signature_hex: str, public_key_hex: str = None) -> bool:
    """
    Verifies Ed25519 signature over canonicalized record payload fingerprint.

    A missing or unusable keypair is a deployment fault, not a bad signature,
    so key resolution happens outside the try: a misconfigured deployment must
    not report every record as unverified and hide the reason.
    """
    pub_hex = public_key_hex or _resolve_public_key_hex()
    try:
        public_key_bytes = bytes.fromhex(pub_hex)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        
        canonical_str = canonicalize_json(record_payload)
        fingerprint = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
        
        sig_bytes = bytes.fromhex(signature_hex)
        public_key.verify(sig_bytes, fingerprint.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError, Exception):
        return False
