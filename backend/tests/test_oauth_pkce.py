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


def test_wrong_verifier_of_valid_length_fails_verification() -> None:
    # Both verifiers sit within the RFC 7636 43-128 window, so this exercises the
    # S256 challenge mismatch rather than the length guard.
    challenge = compute_s256_challenge("the-real-verifier-padded-to-a-valid-length-0000")
    assert is_valid_s256("a-different-verifier-padded-to-a-valid-length-0", challenge) is False


def test_verifier_outside_the_rfc_length_bounds_is_rejected() -> None:
    # RFC 7636 §4.1: the verifier is 43-128 chars. A too-short or too-long verifier
    # fails even when paired with its own matching challenge.
    too_short = "x" * 42
    too_long = "x" * 129
    assert is_valid_s256(too_short, compute_s256_challenge(too_short)) is False
    assert is_valid_s256(too_long, compute_s256_challenge(too_long)) is False
    minimum = "x" * 43
    assert is_valid_s256(minimum, compute_s256_challenge(minimum)) is True


def test_empty_inputs_fail_closed() -> None:
    assert is_valid_s256("", "challenge") is False
    assert is_valid_s256("verifier", "") is False
