"""In-memory test doubles for the web-only lifecycle domain.

The service is tested sociably: the real :class:`LifecycleService` runs over these
in-memory repositories (substituted at the only true external boundary, Postgres),
the shared in-memory embedding repository (reused from the embedding fakes), the
real :class:`WriteEventPublisher` seam wired with a capturing consumer, and a fake
session recording the ``transaction`` boundary. Cascade correctness is a database
guarantee, so it is proven separately in the integration suite; these doubles
exercise the confirmation gate, 404 mapping, receipts, the vector purge call, the
audit publish, and account revocation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.accounts.models import User
from floresu.core.events import WriteEvent, WriteEventPublisher

if TYPE_CHECKING:
    from collections.abc import Sequence

    from floresu.library.models import Bulletpoint
    from floresu.profile.models import Source, SourceSubtype
    from floresu.profile.skills.models import Skill
    from floresu.profile.variants.models import IdentityVariant
    from floresu.resumes.models import JobApplication, Resume
    from floresu.worklog.models import Tag, WorklogEntry


class FakeSession:
    """A no-op stand-in for ``AsyncSession`` recording the transaction boundary."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.info: dict[str, Any] = {}

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class InMemoryLifecycleRepository:
    """A dict-backed :class:`LifecycleRepository` with user-scoped hard deletes."""

    def __init__(self) -> None:
        self.worklog: dict[tuple[int, int], str] = {}
        self.sources: dict[tuple[int, int], tuple[str, str]] = {}
        self.bullets: dict[tuple[int, int], str] = {}
        self.resumes: dict[tuple[int, int], str] = {}
        self.users: set[int] = set()
        self.active_agents: dict[str, int] = {}
        self.revoked_agents: list[str] = []
        self.cleared_blacklist: list[int] = []

    def seed_worklog(self, user_id: int, worklog_id: int, title: str) -> None:
        self.worklog[(user_id, worklog_id)] = title
        self.users.add(user_id)

    def seed_source(self, user_id: int, source_id: int, kind: str, label: str) -> None:
        self.sources[(user_id, source_id)] = (kind, label)
        self.users.add(user_id)

    def seed_bullet(self, user_id: int, bullet_id: int, text: str) -> None:
        self.bullets[(user_id, bullet_id)] = text
        self.users.add(user_id)

    def seed_resume(self, user_id: int, resume_id: int, title: str) -> None:
        self.resumes[(user_id, resume_id)] = title
        self.users.add(user_id)

    def seed_agents(self, user_id: int, count: int) -> None:
        self.active_agents[str(user_id)] = count
        self.users.add(user_id)

    async def delete_worklog(self, user_id: int, worklog_id: int) -> str | None:
        return self.worklog.pop((user_id, worklog_id), None)

    async def delete_source(self, user_id: int, source_id: int) -> tuple[str, str] | None:
        return self.sources.pop((user_id, source_id), None)

    async def delete_bullet(self, user_id: int, bullet_id: int) -> str | None:
        return self.bullets.pop((user_id, bullet_id), None)

    async def delete_resume(self, user_id: int, resume_id: int) -> str | None:
        return self.resumes.pop((user_id, resume_id), None)

    async def count_active_agents(self, user_id_str: str) -> int:
        return self.active_agents.get(user_id_str, 0)

    async def revoke_agents(self, user_id_str: str) -> None:
        self.revoked_agents.append(user_id_str)
        self.active_agents.pop(user_id_str, None)

    async def clear_session_blacklist(self, user_id: int) -> None:
        self.cleared_blacklist.append(user_id)

    async def delete_user(self, user_id: int) -> bool:
        existed = user_id in self.users
        self.users.discard(user_id)
        return existed


class InMemoryExportRepository:
    """A seedable :class:`ExportRepository` returning ORM rows without a database."""

    def __init__(self, account: User | None = None) -> None:
        self._account = account
        self.worklog_rows: list[WorklogEntry] = []
        self.worklog_tag_map: dict[int, list[str]] = {}
        self.worklog_source_map: dict[int, list[int]] = {}
        self.source_rows: list[Source] = []
        self.source_detail_map: dict[int, SourceSubtype] = {}
        self.bullet_rows: list[Bulletpoint] = []
        self.bullet_source_map: dict[int, list[int]] = {}
        self.bullet_worklog_map: dict[int, list[int]] = {}
        self.skill_rows: list[Skill] = []
        self.variant_rows: list[IdentityVariant] = []
        self.tag_rows: list[Tag] = []
        self.resume_rows: list[Resume] = []
        self.job_application_rows: list[JobApplication] = []

    async def account(self, user_id: int) -> User | None:
        return self._account

    async def worklog(self, user_id: int) -> Sequence[WorklogEntry]:
        return self.worklog_rows

    async def worklog_tags(self, user_id: int) -> dict[int, list[str]]:
        return self.worklog_tag_map

    async def worklog_sources(self, user_id: int) -> dict[int, list[int]]:
        return self.worklog_source_map

    async def sources(self, user_id: int) -> Sequence[Source]:
        return self.source_rows

    async def source_details(self, user_id: int) -> dict[int, SourceSubtype]:
        return self.source_detail_map

    async def bullets(self, user_id: int) -> Sequence[Bulletpoint]:
        return self.bullet_rows

    async def bullet_sources(self, user_id: int) -> dict[int, list[int]]:
        return self.bullet_source_map

    async def bullet_worklogs(self, user_id: int) -> dict[int, list[int]]:
        return self.bullet_worklog_map

    async def skills(self, user_id: int) -> Sequence[Skill]:
        return self.skill_rows

    async def variants(self, user_id: int) -> Sequence[IdentityVariant]:
        return self.variant_rows

    async def tags(self, user_id: int) -> Sequence[Tag]:
        return self.tag_rows

    async def resumes(self, user_id: int) -> Sequence[Resume]:
        return self.resume_rows

    async def job_applications(self, user_id: int) -> Sequence[JobApplication]:
        return self.job_application_rows


def capturing_publisher() -> tuple[WriteEventPublisher, list[WriteEvent]]:
    """The real publisher seam wired with a capturing transactional consumer."""
    captured: list[WriteEvent] = []

    async def consume(_session: Any, event: WriteEvent) -> None:
        captured.append(event)

    return WriteEventPublisher(transactional=[consume]), captured


def build_account(user_id: int = 1, email: str = "owner@example.com") -> User:
    """A detached ``User`` row for seeding the export repository."""
    user = User(email=email, password_hash="x", has_completed_onboarding=True)
    user.id = user_id
    return user
