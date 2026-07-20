"""TokenService: token exchange, rotating refresh, revocation, and grants.

The token endpoint: an ``authorization_code`` exchange verifies the PKCE
``code_verifier`` against the code's stored S256 challenge and mints a short-lived
RS256 access token (``aud`` = the MCP resource) plus a rotating refresh token; a
``refresh_token`` exchange rotates: it revokes the presented refresh and issues a
fresh pair, and a **replay** of an already-rotated refresh revokes the whole grant
chain. ``/oauth/revoke`` (RFC 7009) invalidates a refresh token. ``/me/clients``
list/revoke are the connected-client seam.

Access tokens are stateless JWTs and cannot be individually revoked, so agent
tokens are short-lived and revocation takes effect within the access-token TTL.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from floresu.core.errors import NotFound
from floresu.core.logging import get_logger
from floresu.core.observability import OAUTH_TOKENS_ISSUED, track_failures
from floresu.oauth.config import (
    GRANT_TYPE_AUTHORIZATION_CODE,
    GRANT_TYPE_REFRESH_TOKEN,
    OAuthConfig,
)
from floresu.oauth.errors import OAuthError
from floresu.oauth.injection import Clock, OpaqueIdFactory, utcnow
from floresu.oauth.models import OAuthRefreshToken
from floresu.oauth.pkce import is_valid_s256
from floresu.oauth.schemas import ConnectedClient, TokenRequest, TokenResponse
from floresu.oauth.tokens import AccessTokenCodec, hash_token, mint_refresh_token

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from floresu.oauth.repository import OAuthRepository

_log = get_logger("floresu-oauth")
_BEARER = "Bearer"

# grant_type -> increment. Injected so no business method names the global metric;
# the default keeps the metric name/labels stable.
IssuedCounter = Callable[[str], None]


def _default_issued_counter(grant_type: str) -> None:
    """Default issuance counter: bump the process-global ``OAUTH_TOKENS_ISSUED``."""
    OAUTH_TOKENS_ISSUED.labels(grant_type=grant_type).inc()


@track_failures("oauth")
class TokenService:
    """Token issuance, refresh rotation, revocation, and connected-client grants."""

    def __init__(
        self,
        repo: OAuthRepository,
        config: OAuthConfig,
        codec: AccessTokenCodec,
        *,
        clock: Clock = utcnow,
        new_id: OpaqueIdFactory = mint_refresh_token,
        issued_counter: IssuedCounter = _default_issued_counter,
    ) -> None:
        self._repo = repo
        self._config = config
        self._codec = codec
        # Injected so tests pin expiry and force deterministic ids/counting without
        # patching globals; the defaults reproduce the ambient behavior.
        self._clock = clock
        # Raw refresh-token secret (url-safe).
        self._new_id = new_id
        # Counts issuance post-commit; default binds OAUTH_TOKENS_ISSUED.
        self._issued_counter = issued_counter

    async def exchange(self, request: TokenRequest) -> TokenResponse:
        """Dispatch the token endpoint on ``grant_type`` (RFC 6749)."""
        if request.grant_type == GRANT_TYPE_AUTHORIZATION_CODE:
            return await self._exchange_code(request)
        if request.grant_type == GRANT_TYPE_REFRESH_TOKEN:
            return await self._refresh(request)
        raise OAuthError.unsupported_grant_type(f"Unsupported grant_type: {request.grant_type}")

    async def _exchange_code(self, request: TokenRequest) -> TokenResponse:
        if not request.code or not request.code_verifier or not request.client_id:
            raise OAuthError.invalid_request("code, code_verifier, and client_id are required.")
        code = await self._repo.get_code(request.code)
        if code is None or self._is_expired(code.expires_at):
            raise OAuthError.invalid_grant("Authorization code is invalid or expired.")
        if code.client_id != request.client_id:
            raise OAuthError.invalid_grant("Authorization code was issued to another client.")
        # OAuth 2.1 §4.1.3: the authorization request always carried a redirect_uri,
        # so it is required at the token endpoint and must match.
        if request.redirect_uri is None or request.redirect_uri != code.redirect_uri:
            raise OAuthError.invalid_grant(
                "redirect_uri is required and must match the authorization request."
            )
        if not is_valid_s256(request.code_verifier, code.code_challenge):
            raise OAuthError.invalid_grant("PKCE verification failed.")
        if self._config.canonical_resource(request.resource) != code.resource:
            raise OAuthError.invalid_target("resource does not match the authorization request.")

        # Single-use, race-free: only one exchange flips used=false->true. PKCE has
        # already proven possession, so a caller reaching a False result is a
        # verifier-holding replay -> revoke the tokens issued from this code
        # (OAuth 2.1 §4.1.3) rather than silently reject.
        if not await self._repo.consume_code(code.code):
            await self._repo.revoke_grant(code.user_id, code.client_id, now=self._clock())
            await self._repo.commit()
            raise OAuthError.invalid_grant("Authorization code has already been used.")
        grant = await self._repo.get_grant(code.user_id, code.client_id)
        if grant is None:  # pragma: no cover - decision always upserts the grant
            raise OAuthError.invalid_grant("No active grant for this authorization.")
        if grant.revoked_at is not None:
            # The user revoked the client after this code was minted (within the
            # code TTL): honor the revocation rather than re-establish access.
            raise OAuthError.invalid_grant("The authorization grant has been revoked.")
        tokens = await self._issue_pair(
            grant_id=grant.id,
            user_id=code.user_id,
            client_id=code.client_id,
            scope=code.scope,
            resource=code.resource,
        )
        await self._repo.commit()
        self._issued_counter(GRANT_TYPE_AUTHORIZATION_CODE)
        _log.info("oauth_token_issued", client_id=code.client_id, user_id=code.user_id)
        return tokens

    async def _refresh(self, request: TokenRequest) -> TokenResponse:
        if not request.refresh_token or not request.client_id:
            raise OAuthError.invalid_request("refresh_token and client_id are required.")
        existing = await self._repo.get_refresh_token(hash_token(request.refresh_token))
        if existing is None:
            raise OAuthError.invalid_grant("Refresh token is invalid.")
        if existing.revoked:
            # Replay of a rotated refresh token: revoke the whole grant (its refresh
            # chain and revoked_at) so the chain dies and the client also drops off
            # /me/clients (OAuth 2.1 replay defense).
            await self._repo.revoke_grant(existing.user_id, existing.client_id, now=self._clock())
            await self._repo.commit()
            raise OAuthError.invalid_grant("Refresh token has already been used.")
        if self._is_expired(existing.expires_at):
            raise OAuthError.invalid_grant("Refresh token is expired.")
        if existing.client_id != request.client_id:
            raise OAuthError.invalid_grant("Refresh token was issued to another client.")
        if await self._repo.get_client(existing.client_id) is None:
            # Defense in depth: a deleted client's refresh fails closed even if its
            # grant were somehow left un-revoked (cleanup only reaps grantless ones).
            raise OAuthError.invalid_grant("Refresh token's client no longer exists.")

        # Rotate atomically: exactly one concurrent exchange consumes the presented
        # refresh. Losing the race means the token was already used -> treat as a
        # chain compromise and revoke the grant.
        if not await self._repo.consume_refresh_token(
            existing.token_hash
        ):  # pragma: no cover - race-only; a sequential replay is caught by the revoked check
            await self._repo.revoke_grant(existing.user_id, existing.client_id, now=self._clock())
            await self._repo.commit()
            raise OAuthError.invalid_grant("Refresh token has already been used.")
        tokens = await self._issue_pair(
            grant_id=existing.grant_id,
            user_id=existing.user_id,
            client_id=existing.client_id,
            scope=existing.scope,
            resource=existing.resource,
        )
        await self._repo.commit()
        self._issued_counter(GRANT_TYPE_REFRESH_TOKEN)
        _log.info("oauth_token_refreshed", client_id=existing.client_id, user_id=existing.user_id)
        return tokens

    async def revoke(self, token: str, *, client_id: str | None = None) -> None:
        """RFC 7009: revoke a refresh token. Always succeeds (no token-scanning leak).

        Access tokens are stateless and cannot be revoked here; the request still
        succeeds. When the token is a known refresh token owned by the given
        client, it (and thus the current chain) is marked revoked.
        """
        existing = await self._repo.get_refresh_token(hash_token(token))
        if existing is None:
            return
        if client_id is not None and existing.client_id != client_id:
            return
        await self._repo.revoke_refresh_token(existing.token_hash)
        await self._repo.commit()
        _log.info("oauth_token_revoked", client_id=existing.client_id, user_id=existing.user_id)

    async def list_connected_clients(self, user_id: str) -> list[ConnectedClient]:
        """The user's authorized agents (``GET /me/clients``).

        One batch ``get_clients`` read over the shared session instead of N serial
        ``get_client`` awaits; a grant whose client was deleted (a map miss) is
        skipped.
        """
        grants = await self._repo.list_active_grants(user_id)
        names = await self._repo.get_clients([grant.client_id for grant in grants])
        connected: list[ConnectedClient] = []
        for grant in grants:
            client_name = names.get(grant.client_id)
            if client_name is None:
                continue
            connected.append(
                ConnectedClient(
                    client_id=grant.client_id,
                    client_name=client_name,
                    scopes=grant.scope.split(),
                    connected_at=grant.authorized_at,
                    last_active_at=grant.last_active_at,
                )
            )
        return connected

    async def revoke_connected_client(self, user_id: str, client_id: str) -> None:
        """Revoke a user's grant + its refresh tokens (``DELETE /me/clients/{id}``)."""
        grant = await self._repo.revoke_grant(user_id, client_id, now=self._clock())
        if grant is None:
            raise NotFound("No connected client to revoke.")
        await self._repo.commit()
        _log.info("oauth_client_revoked", client_id=client_id, user_id=user_id)

    async def cleanup_stale_clients(self, older_than: timedelta) -> int:
        """Periodic P0 hook: reap abandoned registrations and expired codes.

        Reaps open-registration clients registered more than ``older_than`` ago
        that have **no active grant** (never-consented DCR rows or clients whose
        grant was revoked), plus expired authorization codes. An actively-granted
        client is never reaped, so a long-lived agent that keeps refreshing stays
        connected; a revoked grant already has its refresh chain dead, so the
        delete leaves no live token. Returns the number of clients reaped.
        """
        now = self._clock()
        cutoff = now - older_than
        deleted = await self._repo.delete_stale_registrations(cutoff)
        await self._repo.delete_expired_codes(now)
        await self._repo.commit()
        return len(deleted)

    async def _issue_pair(
        self,
        *,
        grant_id: str,
        user_id: str,
        client_id: str,
        scope: str,
        resource: str,
    ) -> TokenResponse:
        access = self._codec.mint(
            subject=user_id, client_id=client_id, scope=scope, audience=resource
        )
        now = self._clock()
        refresh_raw = self._new_id()
        await self._repo.add_refresh_token(
            OAuthRefreshToken(
                token_hash=hash_token(refresh_raw),
                grant_id=grant_id,
                client_id=client_id,
                user_id=user_id,
                scope=scope,
                resource=resource,
                expires_at=now + self._config.refresh_ttl,
            ),
            now=now,
        )
        # Stamp the grant's last activity so /me/clients shows a live last-active.
        await self._repo.touch_grant_activity(grant_id, now=now)
        return TokenResponse(
            access_token=access.token,
            token_type=_BEARER,
            expires_in=access.expires_in,
            refresh_token=refresh_raw,
            scope=scope,
        )

    def _is_expired(self, expires_at: datetime) -> bool:
        return expires_at <= self._clock()
