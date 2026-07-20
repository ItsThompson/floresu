"""AccountService: registration, login/logout, session refresh, and the /me view.

The single source of truth for account business rules. It receives a repository
and collaborators, resolves identity from credentials or tokens (never from
caller-supplied ids), raises ``FloresuError`` subclasses for the adapter to
render, and owns the transaction boundary (commit on success, rollback on
failure) because ``get_session`` is yield-only.

Session model: an access/refresh pair shares one session id (``sid``). Logout and
refresh-rotation revoke the old ``sid`` via the blacklist, so a revoked refresh
cannot mint a new access token and a revoked session's still-unexpired access
token stops resolving.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from floresu.accounts.injection import Clock, utcnow
from floresu.accounts.models import User
from floresu.accounts.passwords import PasswordHasher, validate_password_strength
from floresu.accounts.schemas import AuthenticatedUser, Session
from floresu.core.db import is_unique_violation
from floresu.core.errors import Conflict, Unauthorized, Validation
from floresu.core.logging import get_logger
from floresu.core.observability import track_failures

if TYPE_CHECKING:
    from floresu.accounts.repository import AccountRepository
    from floresu.accounts.tokens import SessionTokenCodec

# One message for both credential failures so login never reveals whether an
# email is registered.
_INVALID_CREDENTIALS = "Invalid email or password."
# A resolved session pointing at a user id that no longer exists (deleted
# mid-session) is a stale session, not a 404.
_STALE_SESSION = "Session expired or revoked; log in again."

_log = get_logger("floresu-accounts")


@track_failures("accounts")
class AccountService:
    """Business rules for human accounts and sessions."""

    def __init__(
        self,
        repo: AccountRepository,
        hasher: PasswordHasher,
        codec: SessionTokenCodec,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self._repo = repo
        self._hasher = hasher
        self._codec = codec
        # Injected so tests pin the created/updated timestamps without patching
        # globals; the default reproduces the prior ambient call.
        self._clock = clock

    async def register(self, email: str, password: str) -> Session:
        """Create a user and start a session, or raise a field-level error.

        Duplicate detection is delegated to the ``users`` unique email constraint
        (the authoritative, race-free source): on the resulting integrity error
        the transaction is rolled back and a field-level 409 is raised. No
        plaintext password is ever logged or returned.
        """
        normalized_email = _normalize_email(email)
        self._reject_weak_password(password)

        now = self._clock()
        user = User(
            email=normalized_email,
            password_hash=await asyncio.to_thread(self._hasher.hash, password),
            created_at=now,
            updated_at=now,
            has_completed_onboarding=False,
        )
        try:
            await self._repo.add_user(user)
            await self._repo.commit()
        except IntegrityError as exc:
            await self._repo.rollback()
            if not is_unique_violation(exc):
                raise
            raise _duplicate_email_conflict() from exc

        _log.info("user_registered", user_id=user.id)
        return self._start_session(user)

    async def login(self, email: str, password: str) -> Session:
        """Authenticate by email + password; generic 401 on any mismatch."""
        user = await self._repo.get_by_email(_normalize_email(email))
        if user is None or not await asyncio.to_thread(
            self._hasher.verify, password, user.password_hash
        ):
            raise Unauthorized(_INVALID_CREDENTIALS)
        _log.info("user_logged_in", user_id=user.id)
        return self._start_session(user)

    async def refresh(self, refresh_token: str) -> Session:
        """Rotate a valid refresh token into a fresh session; revoke the old id."""
        claims = self._codec.verify_refresh(refresh_token)
        if claims is None or await self._repo.is_session_revoked(claims.sid):
            raise Unauthorized(_STALE_SESSION)
        user = await self._repo.get_by_id(claims.user_id)
        if user is None:
            raise Unauthorized(_STALE_SESSION)
        await self._repo.revoke_session(claims)
        await self._repo.commit()
        _log.info("session_refreshed", user_id=user.id)
        return self._start_session(user)

    async def logout(self, refresh_token: str | None) -> None:
        """Revoke the current session's ``sid`` so it cannot be reused.

        Best-effort: a missing or already-invalid refresh token has nothing to
        revoke, so logout still succeeds (the adapter clears the cookies).
        """
        if refresh_token is None:
            return
        claims = self._codec.verify_refresh(refresh_token)
        if claims is None:
            return
        await self._repo.revoke_session(claims)
        await self._repo.commit()
        _log.info("user_logged_out", user_id=claims.user_id)

    async def me(self, user_id: str) -> AuthenticatedUser:
        """Return the session-resolved account's own view.

        ``user_id`` is the identity resolved at the trust boundary, never a
        client-supplied id. A session resolving to a deleted account is a stale
        session, not a 404.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise Unauthorized(_STALE_SESSION)
        return _to_authenticated(user)

    def _start_session(self, user: User) -> Session:
        return Session(user=_to_authenticated(user), tokens=self._codec.mint_pair(str(user.id)))

    def _reject_weak_password(self, password: str) -> None:
        message = validate_password_strength(password)
        if message is not None:
            raise Validation(message, fields={"password": message})


def _duplicate_email_conflict() -> Conflict:
    return Conflict(
        "An account with this email already exists.",
        fields={"email": "This email is already registered."},
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _to_authenticated(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        has_completed_onboarding=user.has_completed_onboarding,
    )
