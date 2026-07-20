"""Password hashing and strength validation."""

from __future__ import annotations

import pytest

from floresu.accounts.passwords import (
    BCRYPT_COST,
    BcryptPasswordHasher,
    validate_password_strength,
)

_PASSWORD = "Str0ngPass"


def test_hash_is_a_bcrypt_string_and_verifies() -> None:
    hasher = BcryptPasswordHasher(cost=4)
    stored = hasher.hash(_PASSWORD)
    # Never the plaintext; a bcrypt hash string.
    assert stored != _PASSWORD
    assert stored.startswith("$2b$")
    assert hasher.verify(_PASSWORD, stored) is True
    assert hasher.verify("WrongPass9", stored) is False


def test_verify_of_a_malformed_hash_is_false_not_an_error() -> None:
    # A rotated/corrupt hash string must fail verification, not raise a 500.
    assert BcryptPasswordHasher(cost=4).verify(_PASSWORD, "not-a-bcrypt-hash") is False


def test_production_cost_is_twelve() -> None:
    assert BCRYPT_COST == 12


def test_strong_password_passes() -> None:
    assert validate_password_strength(_PASSWORD) is None


@pytest.mark.parametrize(
    "weak",
    [
        "short1A",  # < 8 chars
        "alllowercase1",  # no uppercase
        "ALLUPPERCASE1",  # no lowercase
        "NoDigitsHere",  # no digit
    ],
)
def test_weak_passwords_are_rejected_with_a_message(weak: str) -> None:
    message = validate_password_strength(weak)
    assert message is not None
    assert "at least 8 characters" in message


def test_password_over_the_bcrypt_limit_is_rejected() -> None:
    # bcrypt silently truncates past 72 bytes; reject rather than hash a prefix.
    message = validate_password_strength("A1" + "a" * 71)
    assert message is not None
    assert "72 bytes" in message
