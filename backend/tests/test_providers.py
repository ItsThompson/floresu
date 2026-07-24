"""The shared provider factories inject strategy and preserve the FastAPI shape.

Confirms :func:`publishing_provider` reads the write-event seam through
:func:`get_events` and hands the session plus publisher to the ``build`` strategy,
that it fails loud when the seam is unset, and that :func:`session_provider` hands
only the session. Also pins the inner providers' signatures so FastAPI resolves
``Request`` and ``Depends(get_session)`` exactly as the hand-written closures did.
"""

from __future__ import annotations

from inspect import signature
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from floresu.core.db import get_session
from floresu.core.events import WriteEventPublisher
from floresu.core.providers import publishing_provider, session_provider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_publishing_provider_passes_the_session_and_the_seam_publisher() -> None:
    publisher = WriteEventPublisher()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(events=publisher)))
    session = object()  # the strategy only stores the reference

    def build(s: AsyncSession, p: WriteEventPublisher) -> tuple[object, WriteEventPublisher]:
        return (s, p)

    provider = publishing_provider(build)
    result = provider(request, session)

    assert result == (session, publisher)


def test_publishing_provider_fails_loud_when_the_seam_is_unset() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    session = object()

    def build(s: AsyncSession, p: WriteEventPublisher) -> object:
        return s

    provider = publishing_provider(build)

    with pytest.raises(RuntimeError):
        provider(request, session)


def test_session_provider_passes_only_the_session() -> None:
    session = object()

    def build(s: AsyncSession) -> object:
        return s

    provider = session_provider(build)

    assert provider(session) is session


def test_publishing_provider_exposes_request_and_the_session_dependency() -> None:
    def build(s: AsyncSession, p: WriteEventPublisher) -> object:
        return s

    params = signature(publishing_provider(build)).parameters

    assert list(params) == ["request", "session"]
    assert params["session"].default.dependency is get_session


def test_session_provider_exposes_only_the_session_dependency() -> None:
    def build(s: AsyncSession) -> object:
        return s

    params = signature(session_provider(build)).parameters

    assert list(params) == ["session"]
    assert params["session"].default.dependency is get_session
