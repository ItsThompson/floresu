"""Unit tests for the PKCE S256 transform and constant-time verification."""

from __future__ import annotations

from floresu.oauth.pkce import compute_s256_challenge, is_valid_s256


def test_s256_challenge_matches_the_rfc_7636_test_vector() -> None:
    # RFC 7636 Appendix B: this verifier hashes to this exact base64url challenge.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert compute_s256_challenge(verifier) == expected


def test_valid_verifier_passes_verification() -> None:
    verifier = "a-high-entropy-code-verifier-value-1234567890"
    challenge = compute_s256_challenge(verifier)
    assert is_valid_s256(verifier, challenge) is True


def test_wrong_verifier_fails_verification() -> None:
    challenge = compute_s256_challenge("the-real-verifier")
    assert is_valid_s256("a-different-verifier", challenge) is False


def test_empty_inputs_fail_closed() -> None:
    assert is_valid_s256("", "challenge") is False
    assert is_valid_s256("verifier", "") is False
