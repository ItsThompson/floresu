"""In-memory test doubles and factories for the OAuth AS.

The service layer is tested sociably: real config, real signing keys (ephemeral),
real access-token codec, real PKCE, with this in-memory repository substituted at
the only true external boundary (Postgres). The fake mirrors the SQLAlchemy
semantics the services rely on (one active grant per user+client, refresh-token
revocation, one-time codes, last-active stamping).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from floresu.oauth.config import OAuthConfig
from floresu.oauth.injection import Clock, utcnow
from floresu.oauth.keys import SigningKeySet, load_signing_key_set
from floresu.oauth.models import (
    OAuthAuthorizationCode,
    OAuthAuthRequest,
    OAuthClient,
    OAuthGrant,
    OAuthRefreshToken,
)
from floresu.oauth.pkce import compute_s256_challenge
from floresu.oauth.tokens import AccessTokenCodec

if TYPE_CHECKING:
    from collections.abc import Sequence

TEST_ISSUER = "https://api.floresu.app"
TEST_APP_URL = "https://floresu.app"
TEST_RESOURCE = "https://mcp.floresu.app"


def build_test_config(
    *,
    access_ttl: timedelta = timedelta(minutes=15),
    refresh_ttl: timedelta = timedelta(days=30),
    auth_request_ttl: timedelta = timedelta(minutes=10),
    code_ttl: timedelta = timedelta(minutes=1),
) -> OAuthConfig:
    """An OAuth config with pinned test URLs and overridable TTLs (expiry tests)."""
    return OAuthConfig(
        issuer=TEST_ISSUER,
        consent_base_url=TEST_APP_URL,
        resource=TEST_RESOURCE,
        key_path="",
        key_id="test-kid",
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        auth_request_ttl=auth_request_ttl,
        code_ttl=code_ttl,
    )


def build_test_keyset(config: OAuthConfig) -> SigningKeySet:
    """An ephemeral in-memory signing key set (no PEM on disk)."""
    return load_signing_key_set(config, is_dev=True)


def build_test_codec(
    config: OAuthConfig, keyset: SigningKeySet, *, clock: Clock = utcnow
) -> AccessTokenCodec:
    return AccessTokenCodec(keyset, config, clock=clock)


class MutableClock:
    """A pinned, advanceable clock for expiry tests (no ``sleep``/negative TTL)."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def make_pkce_pair() -> tuple[str, str]:
    """A (code_verifier, code_challenge) S256 pair for the token exchange."""
    verifier = uuid.uuid4().hex + uuid.uuid4().hex
    return verifier, compute_s256_challenge(verifier)


class InMemoryOAuthRepository:
    """A dict-backed :class:`OAuthRepository` with the semantics the services need."""

    def __init__(self) -> None:
        self._clients: dict[str, OAuthClient] = {}
        self._requests: dict[str, OAuthAuthRequest] = {}
        self._codes: dict[str, OAuthAuthorizationCode] = {}
        self._refresh: dict[str, OAuthRefreshToken] = {}
        self._grants: dict[tuple[str, str], OAuthGrant] = {}
        self.commits = 0

    # --- clients ------------------------------------------------------------

    async def add_client(self, client: OAuthClient) -> None:
        self._clients[client.client_id] = client

    async def get_client(self, client_id: str) -> OAuthClient | None:
        return self._clients.get(client_id)

    async def get_clients(self, client_ids: Sequence[str]) -> dict[str, str]:
        return {cid: self._clients[cid].client_name for cid in client_ids if cid in self._clients}

    async def delete_client(self, client_id: str) -> None:
        """Test-support: drop a client row, orphaning any grant that referenced it."""
        self._clients.pop(client_id, None)

    async def delete_stale_registrations(self, cutoff: datetime) -> list[str]:
        active = {grant.client_id for grant in self._grants.values() if grant.revoked_at is None}
        stale = [
            cid
            for cid, client in self._clients.items()
            if client.created_at < cutoff and cid not in active
        ]
        for cid in stale:
            del self._clients[cid]
        return stale

    # --- parked authorize requests ------------------------------------------

    async def add_auth_request(self, request: OAuthAuthRequest) -> None:
        self._requests[request.id] = request

    async def get_auth_request(self, request_id: str) -> OAuthAuthRequest | None:
        return self._requests.get(request_id)

    async def delete_auth_request(self, request_id: str) -> None:
        self._requests.pop(request_id, None)

    # --- authorization codes ------------------------------------------------

    async def add_code(self, code: OAuthAuthorizationCode) -> None:
        if code.used is None:
            code.used = False
        self._codes[code.code] = code

    async def get_code(self, code: str) -> OAuthAuthorizationCode | None:
        return self._codes.get(code)

    async def consume_code(self, code: str) -> bool:
        stored = self._codes.get(code)
        if stored is None or stored.used:
            return False
        stored.used = True
        return True

    async def delete_expired_codes(self, now: datetime) -> None:
        expired = [key for key, code in self._codes.items() if code.expires_at < now]
        for key in expired:
            del self._codes[key]

    # --- refresh tokens -----------------------------------------------------

    async def add_refresh_token(self, token: OAuthRefreshToken, *, now: datetime) -> None:
        token.created_at = now
        if token.revoked is None:
            token.revoked = False
        self._refresh[token.token_hash] = token

    async def get_refresh_token(self, token_hash: str) -> OAuthRefreshToken | None:
        return self._refresh.get(token_hash)

    async def consume_refresh_token(self, token_hash: str) -> bool:
        token = self._refresh.get(token_hash)
        if token is None or token.revoked:
            return False
        token.revoked = True
        return True

    async def revoke_refresh_token(self, token_hash: str) -> None:
        token = self._refresh.get(token_hash)
        if token is not None:
            token.revoked = True

    async def revoke_grant_refresh_tokens(self, grant_id: str) -> None:
        for token in self._refresh.values():
            if token.grant_id == grant_id:
                token.revoked = True

    # --- grants -------------------------------------------------------------

    async def upsert_grant(
        self, *, user_id: str, client_id: str, scope: str, now: datetime, grant_id: str
    ) -> str:
        key = (user_id, client_id)
        existing = self._grants.get(key)
        if existing is not None:
            existing.scope = scope
            existing.authorized_at = now
            existing.last_active_at = now
            existing.revoked_at = None
            return existing.id
        grant = OAuthGrant(
            id=grant_id,
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            authorized_at=now,
            last_active_at=now,
        )
        self._grants[key] = grant
        return grant.id

    async def get_grant(self, user_id: str, client_id: str) -> OAuthGrant | None:
        return self._grants.get((user_id, client_id))

    async def touch_grant_activity(self, grant_id: str, *, now: datetime) -> None:
        for grant in self._grants.values():
            if grant.id == grant_id:
                grant.last_active_at = now
                return

    async def list_active_grants(self, user_id: str) -> list[OAuthGrant]:
        active = [
            grant
            for (uid, _), grant in self._grants.items()
            if uid == user_id and grant.revoked_at is None
        ]
        return sorted(active, key=lambda grant: grant.authorized_at, reverse=True)

    async def revoke_grant(
        self, user_id: str, client_id: str, *, now: datetime
    ) -> OAuthGrant | None:
        grant = self._grants.get((user_id, client_id))
        if grant is None or grant.revoked_at is not None:
            return None
        grant.revoked_at = now
        await self.revoke_grant_refresh_tokens(grant.id)
        return grant

    async def commit(self) -> None:
        self.commits += 1
