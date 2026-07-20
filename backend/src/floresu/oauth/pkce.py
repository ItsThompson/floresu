"""PKCE (RFC 7636) challenge transform and verification, S256 only.

The AS requires the ``S256`` challenge method. The transform is the RFC 7636
definition: ``BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))`` with padding
stripped. Verification recomputes the challenge from the presented
``code_verifier`` and compares it in constant time, so a token exchange proves
possession of the original verifier.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

# RFC 7636 §4.1: the code_verifier is 43-128 characters.
_VERIFIER_MIN_LENGTH = 43
_VERIFIER_MAX_LENGTH = 128


def compute_s256_challenge(code_verifier: str) -> str:
    """The RFC 7636 S256 code challenge for ``code_verifier`` (base64url, unpadded)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def is_valid_s256(code_verifier: str, code_challenge: str) -> bool:
    """True if ``code_verifier`` hashes (S256) to the stored ``code_challenge``."""
    if not code_verifier or not code_challenge:
        return False
    if not _VERIFIER_MIN_LENGTH <= len(code_verifier) <= _VERIFIER_MAX_LENGTH:
        return False
    computed = compute_s256_challenge(code_verifier)
    return secrets.compare_digest(computed, code_challenge)
