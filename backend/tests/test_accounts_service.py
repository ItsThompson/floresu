"""AccountService business rules, through its public methods with an in-memory
repository and the real hasher + token codec (sociable)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from floresu.accounts.notifications import UserRegistered
from floresu.accounts.service import AccountService
from floresu.core.errors import Conflict, Unauthorized, Validation
from tests.accounts_fakes import (
    InMemoryAccountRepository,
    MutableClock,
    build_test_codec,
    build_test_hasher,
)

if TYPE_CHECKING:
    from floresu.accounts.models import User
    from floresu.accounts.notifications import EventPublisher
    from floresu.accounts.tokens import SessionTokenCodec

_PASSWORD = "Str0ngPass"


class _RecordingPublisher:
    def __init__(self, repo: InMemoryAccountRepository) -> None:
        self._repo = repo
        self.events: list[UserRegistered] = []
        self.commits_seen: list[int] = []

    def publish(self, event: UserRegistered) -> None:
        self.events.append(event)
        self.commits_seen.append(self._repo.commits)

    async def aclose(self) -> None:
        return


def _service(
    repo: InMemoryAccountRepository | None = None,
    codec: SessionTokenCodec | None = None,
    event_publisher: EventPublisher | None = None,
) -> tuple[AccountService, InMemoryAccountRepository]:
    repo = repo or InMemoryAccountRepository()
    if event_publisher is None:
        service = AccountService(repo, build_test_hasher(), codec or build_test_codec())
    else:
        service = AccountService(
            repo, build_test_hasher(), codec or build_test_codec(), event_publisher=event_publisher
        )
    return service, repo


async def test_register_creates_user_and_starts_a_session() -> None:
    service, repo = _service()
    session = await service.register("Ada@Example.com", _PASSWORD)

    # Email is normalized to lowercase on write.
    assert session.user.email == "ada@example.com"
    # A server-minted id, and the response never carries the password hash.
    assert session.user.id >= 1
    assert not hasattr(session.user, "password_hash")
    assert session.tokens.access_token and session.tokens.refresh_token
    assert repo.commits == 1


async def test_registered_password_is_stored_only_as_a_bcrypt_hash() -> None:
    service, repo = _service()
    await service.register("ada@example.com", _PASSWORD)
    stored = await repo.get_by_email("ada@example.com")
    assert stored is not None
    assert stored.password_hash != _PASSWORD
    assert stored.password_hash.startswith("$2b$")


async def test_register_publishes_the_user_registered_event_after_commit() -> None:
    repo = InMemoryAccountRepository()
    publisher = _RecordingPublisher(repo)
    service, _ = _service(repo=repo, event_publisher=publisher)

    session = await service.register("Ada@Example.com", _PASSWORD)

    assert publisher.events == [UserRegistered(user_id=session.user.id, email="ada@example.com")]
    assert publisher.commits_seen == [1]


async def test_failed_registration_does_not_publish_an_event() -> None:
    repo = InMemoryAccountRepository()
    publisher = _RecordingPublisher(repo)
    service, _ = _service(repo=repo, event_publisher=publisher)

    with pytest.raises(Validation):
        await service.register("ada@example.com", "weak")

    assert publisher.events == []


async def test_new_registrations_start_not_onboarded() -> None:
    service, repo = _service()
    session = await service.register("ada@example.com", _PASSWORD)
    assert session.user.has_completed_onboarding is False
    stored = await repo.get_by_email("ada@example.com")
    assert stored is not None and stored.has_completed_onboarding is False


async def test_complete_onboarding_persists_the_flag_and_commits() -> None:
    service, repo = _service()
    registered = await service.register("ada@example.com", _PASSWORD)
    commits_before = repo.commits

    completed = await service.complete_onboarding(str(registered.user.id))
    assert completed.has_completed_onboarding is True
    stored = await repo.get_by_id(str(registered.user.id))
    assert stored is not None and stored.has_completed_onboarding is True
    assert repo.commits == commits_before + 1


async def test_complete_onboarding_for_a_missing_user_is_unauthorized() -> None:
    service, _ = _service()
    with pytest.raises(Unauthorized):
        await service.complete_onboarding("999")


async def test_duplicate_email_is_a_field_level_conflict_and_creates_no_user() -> None:
    service, repo = _service()
    first = await service.register("ada@example.com", _PASSWORD)

    with pytest.raises(Conflict) as excinfo:
        await service.register("ADA@example.com", _PASSWORD)  # same email, different casing
    assert excinfo.value.fields is not None
    assert "email" in excinfo.value.fields
    # No second user created; the sole account is the first registration.
    stored = await repo.get_by_email("ada@example.com")
    assert stored is not None and stored.id == first.user.id
    assert repo.rollbacks == 1


async def test_weak_password_is_rejected_with_a_field_message_and_no_user() -> None:
    service, repo = _service()
    with pytest.raises(Validation) as excinfo:
        await service.register("ada@example.com", "weak")
    assert excinfo.value.fields is not None
    assert "password" in excinfo.value.fields
    assert await repo.get_by_email("ada@example.com") is None
    assert repo.commits == 0


async def test_login_with_correct_credentials_resolves_the_right_user() -> None:
    service, _ = _service()
    registered = await service.register("ada@example.com", _PASSWORD)
    session = await service.login("ada@example.com", _PASSWORD)
    assert session.user.id == registered.user.id


async def test_login_is_case_insensitive_on_email() -> None:
    service, _ = _service()
    await service.register("ada@example.com", _PASSWORD)
    session = await service.login("ADA@EXAMPLE.COM", _PASSWORD)
    assert session.user.email == "ada@example.com"


async def test_login_wrong_password_is_generic_401() -> None:
    service, _ = _service()
    await service.register("ada@example.com", _PASSWORD)
    with pytest.raises(Unauthorized) as excinfo:
        await service.login("ada@example.com", "WrongPass9")
    assert "Invalid email or password" in excinfo.value.detail


async def test_login_unknown_email_gives_the_same_generic_401() -> None:
    service, _ = _service()
    with pytest.raises(Unauthorized) as excinfo:
        await service.login("nobody@example.com", _PASSWORD)
    # Identical message to the wrong-password case: no account-existence leak.
    assert "Invalid email or password" in excinfo.value.detail


async def test_logout_revokes_the_refresh_session() -> None:
    service, repo = _service()
    session = await service.register("ada@example.com", _PASSWORD)
    await service.logout(session.tokens.refresh_token)
    assert await repo.is_session_revoked(session.tokens.sid) is True


async def test_logout_without_a_token_is_a_noop() -> None:
    service, repo = _service()
    await service.logout(None)
    assert repo.commits == 0


async def test_logout_with_an_invalid_token_is_a_noop() -> None:
    service, repo = _service()
    await service.logout("not-a-token")
    assert repo.commits == 0


async def test_refresh_rotates_and_revokes_the_old_session() -> None:
    service, repo = _service()
    session = await service.register("ada@example.com", _PASSWORD)
    old_sid = session.tokens.sid

    refreshed = await service.refresh(session.tokens.refresh_token)
    # New session id, and the old one is now blacklisted (rotation).
    assert refreshed.tokens.sid != old_sid
    assert await repo.is_session_revoked(old_sid) is True
    assert refreshed.user.id == session.user.id


async def test_a_revoked_refresh_cannot_mint_a_new_access_token() -> None:
    service, _ = _service()
    session = await service.register("ada@example.com", _PASSWORD)
    await service.logout(session.tokens.refresh_token)
    with pytest.raises(Unauthorized):
        await service.refresh(session.tokens.refresh_token)


async def test_a_rotated_refresh_token_cannot_be_replayed() -> None:
    service, _ = _service()
    session = await service.register("ada@example.com", _PASSWORD)
    await service.refresh(session.tokens.refresh_token)
    # Reusing the original (now-rotated) refresh token is rejected.
    with pytest.raises(Unauthorized):
        await service.refresh(session.tokens.refresh_token)


async def test_refresh_with_an_invalid_token_is_401() -> None:
    service, _ = _service()
    with pytest.raises(Unauthorized):
        await service.refresh("not-a-token")


async def test_refresh_for_a_deleted_user_is_401() -> None:
    # A validly signed refresh token whose user no longer exists must not resolve.
    codec = build_test_codec()
    service, _ = _service(codec=codec)
    orphan = codec.mint_pair("9999")
    with pytest.raises(Unauthorized):
        await service.refresh(orphan.refresh_token)


async def test_me_returns_the_session_resolved_user() -> None:
    service, _ = _service()
    registered = await service.register("ada@example.com", _PASSWORD)
    view = await service.me(str(registered.user.id))
    assert view.id == registered.user.id
    assert view.email == "ada@example.com"


async def test_me_for_a_missing_user_is_unauthorized() -> None:
    # A session resolving to a deleted account is a stale session, not a 404.
    service, _ = _service()
    with pytest.raises(Unauthorized):
        await service.me("9999")


async def test_session_expiry_and_rotation_under_a_pinned_clock() -> None:
    clock = MutableClock(datetime(2024, 1, 1, tzinfo=UTC))
    codec = build_test_codec(
        access_ttl=timedelta(minutes=15), refresh_ttl=timedelta(days=14), clock=clock
    )
    service, _ = _service(codec=codec)
    session = await service.register("ada@example.com", _PASSWORD)
    assert codec.verify_access(session.tokens.access_token) is not None  # valid at t0

    clock.advance(timedelta(minutes=16))  # past the access TTL, within the refresh TTL

    # The access token has expired against the pinned clock...
    assert codec.verify_access(session.tokens.access_token) is None
    # ...but the refresh token is still valid, so rotation issues a fresh session.
    rotated = await service.refresh(session.tokens.refresh_token)
    assert rotated.tokens.sid != session.tokens.sid
    assert codec.verify_access(rotated.tokens.access_token) is not None


class _NonUniqueViolationError(Exception):
    """An integrity error that is NOT a unique-constraint breach (e.g. a NOT NULL)."""

    sqlstate = "23502"


async def test_register_reraises_a_non_unique_integrity_error() -> None:
    class _FailingRepo(InMemoryAccountRepository):
        async def add_user(self, user: User) -> None:
            raise IntegrityError("INSERT", {}, _NonUniqueViolationError())

    repo = _FailingRepo()
    service = AccountService(repo, build_test_hasher(), build_test_codec())
    # A non-unique integrity error is unexpected here; it must propagate rather
    # than be misreported as a duplicate Conflict.
    with pytest.raises(IntegrityError):
        await service.register("ada@example.com", _PASSWORD)
    assert repo.rollbacks == 1
