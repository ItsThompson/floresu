"""Integration tests: the OAuth migration and repository against real Postgres.

Applies Alembic to head on a containerized pgvector Postgres and drives the AS
services through the SQLAlchemy repository so the parking store, one-time codes,
and refresh-token rotation/replay run against the real driver (not just the
in-memory fake). Also proves the ORM models match the migrated schema (no
structural autogenerate diff). Skipped automatically when Docker is unavailable.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Connection

# Importing the models attaches every domain's tables to Base.metadata, which is
# what env.py does at migration time and what autogenerate diffs against.
from floresu.accounts import models as _accounts_models  # noqa: F401
from floresu.core.db import create_database, create_db_engine
from floresu.core.errors import NotFound
from floresu.core.orm import Base
from floresu.oauth import models as _oauth_models  # noqa: F401
from floresu.oauth.authorization import AuthorizationService
from floresu.oauth.cleanup import build_stale_client_sweep
from floresu.oauth.errors import OAuthError
from floresu.oauth.repository import SqlAlchemyOAuthRepository
from floresu.oauth.schemas import AuthorizeParams, ClientRegistrationRequest, TokenRequest
from floresu.oauth.token_exchange import TokenService
from tests.oauth_fakes import build_test_codec, build_test_config, build_test_keyset, make_pkce_pair

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_USER = "user-tay"
_REDIRECT = "http://127.0.0.1:8765/callback"

_STRUCTURAL_OPS = frozenset(
    {"add_table", "remove_table", "add_column", "remove_column", "add_index", "remove_index"}
)

_OAUTH_TABLES = {
    "oauth_clients",
    "oauth_auth_requests",
    "oauth_authorization_codes",
    "oauth_refresh_tokens",
    "oauth_grants",
}


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


@pytest.fixture(scope="session")
def migrated_postgres_url(postgres_url: str) -> Iterator[str]:
    """Apply Alembic to head against the container.

    Runs ``command.upgrade`` here (sync; env.py drives its own ``asyncio.run``) so
    the async flow tests below never call it from inside a running event loop.
    """
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url
    try:
        command.upgrade(_alembic_config(), "head")
        yield postgres_url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def test_migration_creates_the_oauth_tables(migrated_postgres_url: str) -> None:
    async def _tables() -> set[str]:
        engine = create_db_engine(migrated_postgres_url)
        try:
            async with engine.connect() as conn:
                rows = await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
                return {row[0] for row in rows}
        finally:
            await engine.dispose()

    assert asyncio.run(_tables()) >= _OAUTH_TABLES


def test_autogenerate_emits_no_structural_diff(migrated_postgres_url: str) -> None:
    # The ORM models must match the migrated schema, so autogenerate on a head DB
    # produces no add/remove of any oauth table, column, or index.
    def _diff(sync_conn: Connection) -> list[object]:
        context = MigrationContext.configure(sync_conn)
        return list(compare_metadata(context, Base.metadata))

    async def _run() -> list[object]:
        engine = create_db_engine(migrated_postgres_url)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(_diff)
        finally:
            await engine.dispose()

    diffs = asyncio.run(_run())
    structural = [d for d in diffs if isinstance(d, tuple) and d and d[0] in _STRUCTURAL_OPS]
    assert structural == [], f"autogenerate would change the schema: {structural}"


async def test_oauth_flow_persists_rotation_revocation_end_to_end(
    migrated_postgres_url: str,
) -> None:
    database = create_database(migrated_postgres_url)
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))

    @asynccontextmanager
    async def auth() -> AsyncIterator[AuthorizationService]:
        async with database.sessionmaker() as session:
            yield AuthorizationService(SqlAlchemyOAuthRepository(session), config)

    @asynccontextmanager
    async def tokens() -> AsyncIterator[TokenService]:
        async with database.sessionmaker() as session:
            yield TokenService(SqlAlchemyOAuthRepository(session), config, codec)

    def _refresh_request(refresh_token: str) -> TokenRequest:
        return TokenRequest(
            grant_type="refresh_token", client_id=client_id, refresh_token=refresh_token
        )

    try:
        async with auth() as auth_service:
            registration = await auth_service.register_client(
                ClientRegistrationRequest(redirect_uris=[_REDIRECT], client_name="Persist Agent")
            )
        client_id = registration.client_id

        verifier, challenge = make_pkce_pair()
        async with auth() as auth_service:
            consent_url = await auth_service.start_authorization(
                AuthorizeParams(
                    client_id=client_id,
                    redirect_uri=_REDIRECT,
                    response_type="code",
                    code_challenge=challenge,
                    code_challenge_method="S256",
                    state="xyz",
                )
            )
        request_id = _query(consent_url)["auth_request_id"]

        async with auth() as auth_service:
            redirect = await auth_service.decide(
                auth_request_id=request_id, user_id=_USER, approve=True
            )
        code = _query(redirect)["code"]

        async with tokens() as token_service:
            issued = await token_service.exchange(
                TokenRequest(
                    grant_type="authorization_code",
                    client_id=client_id,
                    code=code,
                    code_verifier=verifier,
                    redirect_uri=_REDIRECT,
                )
            )
        # The access token is audience-bound to the MCP resource and verifies.
        verified = codec.verify(issued.access_token)
        assert verified is not None and verified.audience == config.resource

        # The connected-client list reflects the persisted grant with both times.
        async with tokens() as token_service:
            connected = await token_service.list_connected_clients(_USER)
        assert [c.client_id for c in connected] == [client_id]
        assert connected[0].connected_at is not None
        assert connected[0].last_active_at is not None

        # Rotate the refresh token; the old one is now persisted as revoked.
        async with tokens() as token_service:
            rotated = await token_service.exchange(_refresh_request(issued.refresh_token))
        assert rotated.refresh_token != issued.refresh_token

        # Explicitly revoking the connected client (while the grant is still
        # active) persists the grant + chain revocation, so the list empties.
        async with tokens() as token_service:
            await token_service.revoke_connected_client(_USER, client_id)
        async with tokens() as token_service:
            assert await token_service.list_connected_clients(_USER) == []
        # Revoking an already-revoked grant is a 404 against the real DB.
        async with tokens() as token_service:
            with pytest.raises(NotFound):
                await token_service.revoke_connected_client(_USER, client_id)
        # Both the rotated and the rotated-out refresh tokens are now dead.
        async with tokens() as token_service:
            with pytest.raises(OAuthError):
                await token_service.exchange(_refresh_request(rotated.refresh_token))
        async with tokens() as token_service:
            with pytest.raises(OAuthError):
                await token_service.exchange(_refresh_request(issued.refresh_token))
    finally:
        await database.engine.dispose()


async def test_cleanup_reaps_grantless_clients_but_keeps_active_ones(
    migrated_postgres_url: str,
) -> None:
    # The reaper reaps abandoned (no-active-grant) registrations by age but must
    # never reap an actively-granted client, which would disconnect a live agent.
    database = create_database(migrated_postgres_url)
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))

    @asynccontextmanager
    async def auth() -> AsyncIterator[AuthorizationService]:
        async with database.sessionmaker() as session:
            yield AuthorizationService(SqlAlchemyOAuthRepository(session), config)

    @asynccontextmanager
    async def tokens() -> AsyncIterator[TokenService]:
        async with database.sessionmaker() as session:
            yield TokenService(SqlAlchemyOAuthRepository(session), config, codec)

    try:
        # A never-consented client and an actively-granted client.
        async with auth() as auth_service:
            grantless = (
                await auth_service.register_client(
                    ClientRegistrationRequest(redirect_uris=[_REDIRECT], client_name="Abandoned")
                )
            ).client_id
        async with auth() as auth_service:
            active = (
                await auth_service.register_client(
                    ClientRegistrationRequest(redirect_uris=[_REDIRECT], client_name="Active")
                )
            ).client_id

        verifier, challenge = make_pkce_pair()
        async with auth() as auth_service:
            consent_url = await auth_service.start_authorization(
                AuthorizeParams(
                    client_id=active,
                    redirect_uri=_REDIRECT,
                    response_type="code",
                    code_challenge=challenge,
                    code_challenge_method="S256",
                )
            )
        request_id = _query(consent_url)["auth_request_id"]
        async with auth() as auth_service:
            redirect = await auth_service.decide(
                auth_request_id=request_id, user_id=_USER, approve=True
            )
        code = _query(redirect)["code"]
        async with tokens() as token_service:
            issued = await token_service.exchange(
                TokenRequest(
                    grant_type="authorization_code",
                    client_id=active,
                    code=code,
                    code_verifier=verifier,
                    redirect_uri=_REDIRECT,
                )
            )

        # Sweep everything old: the grantless client is reaped; the active one stays.
        sweep = build_stale_client_sweep(
            database.sessionmaker, config, codec, max_age=timedelta(seconds=-1)
        )
        assert await sweep() >= 1
        async with database.sessionmaker() as session:
            repo = SqlAlchemyOAuthRepository(session)
            assert await repo.get_client(grantless) is None
            assert await repo.get_client(active) is not None

        # The active client's refresh still rotates: it was not disconnected.
        async with tokens() as token_service:
            rotated = await token_service.exchange(
                TokenRequest(
                    grant_type="refresh_token",
                    client_id=active,
                    refresh_token=issued.refresh_token,
                )
            )
        assert rotated.refresh_token
    finally:
        await database.engine.dispose()
