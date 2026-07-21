"""End-to-end search tests over real Postgres (FTS + pgvector + fusion + graph).

Runs the real :class:`SqlAlchemySearchRepository` and :class:`SearchService`
against a live pgvector Postgres, so the lexical ``to_tsvector`` / ``ts_rank_cd``
retrieval, the pgvector cosine-distance ANN retrieval, RRF fusion, the scored
provenance graph, the filters, and the write-then-search fast-path are all
exercised against real SQL. Only the two true external boundaries are faked:
OpenAI (a stub/fake provider, so the query vector is controlled and no OpenAI call
is made) and, for the fast-path test, the write side reuses the real worklog
service and the embedding fast-path consumer.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config

from floresu.accounts.models import User
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.embedding.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL, EmbedItemKind
from floresu.embedding.corpus import CorpusResolver
from floresu.embedding.enqueue import build_sync_embed_fastpath_consumer
from floresu.embedding.models import Embedding
from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.profile.models import Role, Source, SourceKind
from floresu.search.retrieval import SqlAlchemySearchRepository
from floresu.search.schemas import DateRange, SearchFilters, SearchLayer, SearchQuery
from floresu.search.service import SearchService
from floresu.worklog.models import Tag, WorklogEntry, WorklogSource, WorklogTag
from tests.embedding_fakes import FakeEmbeddingProvider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_HUMAN = Actor(type=ActorType.HUMAN)


class StubQueryProvider:
    """A provider that returns one fixed query vector, so semantic order is controlled."""

    model = EMBEDDING_MODEL
    dimension = EMBEDDING_DIMENSION

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector]


class FailingProvider:
    """A provider whose embed always raises, to exercise lexical-only degradation."""

    model = EMBEDDING_MODEL
    dimension = EMBEDDING_DIMENSION

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("provider unavailable")


def _axis(index: int, value: float = 1.0) -> list[float]:
    """A 1536-dim vector with ``value`` at ``index`` (a controllable direction)."""
    vector = [0.0] * EMBEDDING_DIMENSION
    vector[index] = value
    return vector


@pytest.fixture
def sessionmaker(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    return create_sessionmaker(create_db_engine(postgres_url))


async def _insert_user(sessionmaker: async_sessionmaker[AsyncSession], email: str) -> int:
    async with sessionmaker() as session, transaction(session):
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.flush()
        return user.id


async def _add_worklog(
    session: AsyncSession,
    user_id: int,
    title: str,
    description: str,
    *,
    when: date = date(2024, 6, 1),
    archived: bool = False,
) -> int:
    entry = WorklogEntry(
        user_id=user_id,
        title=title,
        entry_date=when,
        description=description,
        content_hash="h",
        archived_at=(when if archived else None),
    )
    session.add(entry)
    await session.flush()
    return entry.id


async def _add_bullet(session: AsyncSession, user_id: int, text: str) -> int:
    bullet = Bulletpoint(user_id=user_id, text=text, content_hash="h")
    session.add(bullet)
    await session.flush()
    return bullet.id


async def _add_role(
    session: AsyncSession,
    user_id: int,
    label: str,
    company: str,
    job_title: str,
    *,
    date_start: date | None = None,
    date_end: date | None = None,
) -> int:
    source = Source(
        user_id=user_id,
        kind=SourceKind.ROLE,
        display_label=label,
        date_start=date_start,
        date_end=date_end,
    )
    session.add(source)
    await session.flush()
    session.add(
        Role(source_id=source.id, kind=SourceKind.ROLE, company=company, job_title=job_title)
    )
    await session.flush()
    return source.id


async def _add_embedding(
    session: AsyncSession, user_id: int, kind: EmbedItemKind, item_id: int, vector: list[float]
) -> None:
    session.add(
        Embedding(
            item_kind=kind,
            item_id=item_id,
            user_id=user_id,
            content_hash="h",
            vector=vector,
            model=EMBEDDING_MODEL,
        )
    )


def _service(session: AsyncSession, provider: object) -> SearchService:
    return SearchService(SqlAlchemySearchRepository(session), provider)  # type: ignore[arg-type]


async def test_lexical_fts_ranks_matching_items_and_ignores_non_matches(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "search-lexical@test.dev")
    async with sessionmaker() as session, transaction(session):
        hit = await _add_worklog(session, user_id, "Kubernetes autoscaling", "Tuned the HPA.")
        await _add_worklog(session, user_id, "Wrote the onboarding guide", "Docs work.")
        bullet = await _add_bullet(session, user_id, "Cut Kubernetes pod restarts to zero.")

    # No embeddings + a failing provider -> lexical-only, so this isolates FTS.
    async with sessionmaker() as session:
        result = await _service(session, FailingProvider()).search(
            str(user_id), SearchQuery(query="kubernetes")
        )

    hit_ids = {(hit.type, hit.id) for hit in result.ranked}
    assert (EmbedItemKind.WORKLOG, hit) in hit_ids
    assert (EmbedItemKind.BULLET, bullet) in hit_ids
    # The unrelated "onboarding guide" entry never matched the query.
    assert all(item[0] is not EmbedItemKind.WORKLOG or item[1] == hit for item in hit_ids)
    assert [notice.code for notice in result.notices] == ["semantic_unavailable"]


async def test_semantic_ann_orders_by_cosine_distance(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "search-semantic@test.dev")
    async with sessionmaker() as session, transaction(session):
        near = await _add_worklog(session, user_id, "Alpha", "one")
        far = await _add_worklog(session, user_id, "Beta", "two")
        await _add_embedding(session, user_id, EmbedItemKind.WORKLOG, near, _axis(0))
        await _add_embedding(session, user_id, EmbedItemKind.WORKLOG, far, _axis(1))

    # A query string that matches neither entry lexically; the fixed query vector
    # points mostly along axis 0, so the axis-0 embedding is nearest.
    query_vector = _axis(0)
    query_vector[1] = 0.1
    async with sessionmaker() as session:
        result = await _service(session, StubQueryProvider(query_vector)).search(
            str(user_id), SearchQuery(query="zzzznolexicalmatch")
        )

    assert [hit.id for hit in result.ranked] == [near, far]


async def test_hybrid_fusion_builds_a_scored_provenance_graph(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "search-hybrid@test.dev")
    async with sessionmaker() as session, transaction(session):
        source = await _add_role(session, user_id, "Staff Eng, Acme", "Acme", "Staff Engineer")
        worklog = await _add_worklog(
            session, user_id, "Latency sharding", "Sharded the write path for latency."
        )
        bullet = await _add_bullet(session, user_id, "Cut p99 latency 40% via sharding.")
        session.add(WorklogSource(worklog_id=worklog, source_id=source))
        session.add(BulletWorklog(bullet_id=bullet, worklog_id=worklog))
        session.add(BulletSource(bullet_id=bullet, source_id=source))
        # The worklog also matches semantically (nearest vector); the bullet matches
        # only lexically. The worklog therefore appears in both retrievers.
        await _add_embedding(session, user_id, EmbedItemKind.WORKLOG, worklog, _axis(0))

    async with sessionmaker() as session:
        result = await _service(session, StubQueryProvider(_axis(0))).search(
            str(user_id), SearchQuery(query="latency")
        )

    ranked = [(hit.type, hit.id) for hit in result.ranked]
    assert (EmbedItemKind.WORKLOG, worklog) in ranked
    assert (EmbedItemKind.BULLET, bullet) in ranked
    # The worklog is in both retrieval lists, so it outranks the lexical-only bullet.
    assert ranked.index((EmbedItemKind.WORKLOG, worklog)) < ranked.index(
        (EmbedItemKind.BULLET, bullet)
    )
    # The role source did not match the query directly but is the parent of both
    # hits, so it appears as a grouping node with no match score and a combined score.
    assert [node.id for node in result.graph.sources] == [source]
    node = result.graph.sources[0]
    assert node.match_score is None
    assert node.label == "Staff Eng, Acme"
    assert node.score > 0
    worklog_node = next(n for n in result.graph.worklog if n.id == worklog)
    assert worklog_node.source_ids == [source]
    bullet_node = next(n for n in result.graph.bullets if n.id == bullet)
    assert bullet_node.worklog_ids == [worklog]
    assert bullet_node.source_ids == [source]


async def test_a_source_is_a_direct_hit_with_a_match_score(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "search-source-hit@test.dev")
    async with sessionmaker() as session, transaction(session):
        source = await _add_role(session, user_id, "Payments role", "Stripe", "Payments Engineer")

    async with sessionmaker() as session:
        result = await _service(session, FailingProvider()).search(
            str(user_id), SearchQuery(query="payments")
        )

    assert [(hit.type, hit.id) for hit in result.ranked] == [(EmbedItemKind.SOURCE, source)]
    node = result.graph.sources[0]
    assert node.match_score is not None
    assert node.score == node.match_score


async def test_filters_narrow_the_result_set(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "search-filters@test.dev")
    async with sessionmaker() as session, transaction(session):
        source = await _add_role(session, user_id, "Reporting role", "Acme", "Reporting Engineer")
        other_source = await _add_role(session, user_id, "Other role", "Beta", "Reporting Analyst")
        tagged = await _add_worklog(
            session,
            user_id,
            "Reporting pipeline",
            "Built the reporting pipeline.",
            when=date(2024, 3, 1),
        )
        old = await _add_worklog(
            session, user_id, "Reporting prototype", "Reporting spike.", when=date(2022, 1, 1)
        )
        bullet = await _add_bullet(session, user_id, "Owned reporting accuracy.")
        session.add(WorklogSource(worklog_id=tagged, source_id=source))
        session.add(BulletSource(bullet_id=bullet, source_id=source))
        tag = Tag(user_id=user_id, label="analytics")
        session.add(tag)
        await session.flush()
        session.add(WorklogTag(worklog_id=tagged, tag_id=tag.id))

    async def search(filters: SearchFilters) -> set[tuple[EmbedItemKind, int]]:
        async with sessionmaker() as session:
            result = await _service(session, FailingProvider()).search(
                str(user_id), SearchQuery(query="reporting", filters=filters)
            )
            return {(hit.type, hit.id) for hit in result.ranked}

    # layer=library keeps only the bullet.
    assert await search(SearchFilters(layer=SearchLayer.LIBRARY)) == {
        (EmbedItemKind.BULLET, bullet)
    }
    # source_ids keeps items attached to that source (the worklog + the bullet + the
    # source itself), excluding the unrelated source.
    attached = await search(SearchFilters(source_ids=[source]))
    assert (EmbedItemKind.WORKLOG, tagged) in attached
    assert (EmbedItemKind.BULLET, bullet) in attached
    assert (EmbedItemKind.SOURCE, other_source) not in attached
    # tags keeps only the tagged worklog entry (sources and bullets are dropped).
    assert await search(SearchFilters(tags=["analytics"])) == {(EmbedItemKind.WORKLOG, tagged)}
    # kinds keeps only sources.
    kinds_hits = await search(SearchFilters(kinds=[SourceKind.ROLE]))
    assert kinds_hits == {(EmbedItemKind.SOURCE, source), (EmbedItemKind.SOURCE, other_source)}
    # date_range keeps only the recent worklog entry, dropping the 2022 one.
    dated = await search(
        SearchFilters(
            date_range=DateRange.model_validate(
                {"from": date(2024, 1, 1), "to": date(2024, 12, 31)}
            )
        )
    )
    assert (EmbedItemKind.WORKLOG, tagged) in dated
    assert (EmbedItemKind.WORKLOG, old) not in dated
    # A one-sided window (upper bound only) still excludes the newer entry.
    upper_only = await search(
        SearchFilters(date_range=DateRange.model_validate({"to": date(2022, 6, 1)}))
    )
    assert (EmbedItemKind.WORKLOG, old) in upper_only
    assert (EmbedItemKind.WORKLOG, tagged) not in upper_only
    # A one-sided window (lower bound only) keeps only the newer entry.
    lower_only = await search(
        SearchFilters(date_range=DateRange.model_validate({"from": date(2023, 1, 1)}))
    )
    assert (EmbedItemKind.WORKLOG, tagged) in lower_only
    assert (EmbedItemKind.WORKLOG, old) not in lower_only


async def test_a_filter_matching_nothing_returns_an_empty_result(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "search-empty-filter@test.dev")
    async with sessionmaker() as session, transaction(session):
        await _add_worklog(session, user_id, "Reporting pipeline", "Built it.")

    async with sessionmaker() as session:
        result = await _service(session, FailingProvider()).search(
            str(user_id),
            SearchQuery(query="reporting", filters=SearchFilters(source_ids=[999999])),
        )
    assert result.ranked == []
    assert result.graph.sources == []
    assert result.graph.worklog == []
    assert result.graph.bullets == []


async def test_archived_items_never_appear(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "search-archived@test.dev")
    async with sessionmaker() as session, transaction(session):
        active = await _add_worklog(session, user_id, "Caching layer", "Added a cache.")
        archived = await _add_worklog(
            session, user_id, "Caching spike", "Old cache work.", archived=True
        )
        # Even with a stored vector, an archived item is excluded from retrieval.
        await _add_embedding(session, user_id, EmbedItemKind.WORKLOG, archived, _axis(0))

    async with sessionmaker() as session:
        result = await _service(session, StubQueryProvider(_axis(0))).search(
            str(user_id), SearchQuery(query="caching")
        )

    ids = {hit.id for hit in result.ranked}
    assert active in ids
    assert archived not in ids


async def test_empty_query_returns_nothing(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "search-empty-query@test.dev")
    async with sessionmaker() as session, transaction(session):
        await _add_worklog(session, user_id, "Something", "content")

    async with sessionmaker() as session:
        result = await _service(session, FakeEmbeddingProvider()).search(
            str(user_id), SearchQuery(query="   ")
        )
    assert result.ranked == []


async def test_write_then_search_fast_path_finds_the_just_embedded_item(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # The internal app embeds inline on write (the fast-path). After a write, an
    # immediate search must find the item semantically. The fake provider embeds
    # every text to the same direction, so a query that does not match lexically
    # still retrieves the freshly-embedded item purely via the semantic vector.
    provider = FakeEmbeddingProvider()
    publisher = build_write_event_publisher(
        post_commit=[build_sync_embed_fastpath_consumer(sessionmaker, CorpusResolver(), provider)]
    )
    user_id = await _insert_user(sessionmaker, "search-fastpath@test.dev")

    from floresu.worklog.repository import SqlAlchemyWorklogRepository
    from floresu.worklog.service import WorklogService
    from tests.worklog_fakes import build_worklog_write

    async with sessionmaker() as session:
        service = WorklogService(session, SqlAlchemyWorklogRepository(session), publisher)
        record = await service.create(
            str(user_id),
            _HUMAN,
            build_worklog_write(title="Deployed canary rollout", description="Progressive."),
        )

    async with sessionmaker() as session:
        result = await _service(session, provider).search(
            str(user_id), SearchQuery(query="zzzznolexicalmatch")
        )

    assert record.id in {hit.id for hit in result.ranked}
