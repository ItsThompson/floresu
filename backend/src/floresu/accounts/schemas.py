"""Wire schemas and domain objects for the accounts domain.

Request bodies are validated at the boundary (FastAPI/Pydantic); the response
model deliberately never carries the password hash. :class:`Session` is a domain
object the service returns: it bundles the authenticated user with the freshly
minted token pair so the transport adapter can both set cookies and return the
user body, without the service knowing about HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, EmailStr

if TYPE_CHECKING:
    from floresu.accounts.tokens import TokenPair


class RegisterRequest(BaseModel):
    """Registration input. ``email`` is validated as an address; the password's
    strength is enforced in the service for a specific, field-level message."""

    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    """Login input. ``email`` is a plain string (not ``EmailStr``) so a malformed
    address takes the same generic 401 path as a wrong password, never leaking
    whether the address is even well-formed vs. registered."""

    email: str
    password: str


class AuthenticatedUser(BaseModel):
    """The authenticated user's own view, returned by register/login/refresh/me.

    Carries the private ``email`` (the caller is the account owner) but never the
    password hash.
    """

    id: int
    email: str
    created_at: datetime
    has_completed_onboarding: bool


@dataclass(frozen=True)
class Session:
    """A resolved session: the authenticated user plus its minted token pair."""

    user: AuthenticatedUser
    tokens: TokenPair
