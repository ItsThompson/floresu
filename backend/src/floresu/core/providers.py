"""Shared FastAPI provider factories and the dependency-injection type aliases.

Two factories collapse the near-identical per-domain provider closures into one
strategy-injected shape:

- :func:`publishing_provider` backs a write-path service. It reads the
  process-wide :class:`WriteEventPublisher` off the app through
  :func:`get_events` and hands it, with the request-scoped session, to a
  ``build`` strategy. This is the single call site of :func:`get_events`, so the
  seam is read and type-checked in exactly one place.
- :func:`session_provider` backs a read-only service. It hands only the
  request-scoped session to a ``build`` strategy.

The factories inject strategy rather than branch on context: a domain's
``wiring.py`` declares how to build its service in a ``build`` closure (which
captures any extra dependencies, such as a render module or object store), and
the factory stays generic.

The aliases are the DI contract each router binds through ``Depends``. They
replace the opaque ``Callable[..., Any]`` a router used to redeclare, so the
resolver and provider shapes are documented at the type level.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Depends
from starlette.requests import Request

from floresu.core.actor import Actor
from floresu.core.db import get_session
from floresu.core.events import get_events

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.events import WriteEventPublisher

# Resolves the caller's ``user_id`` at the trust boundary. Async on the web app
# (``require_user``), sync on the internal app (``require_internal_user``); the
# union return absorbs both boundaries. The argument list stays open because a
# FastAPI dependency may take the request or take nothing.
Identity = Callable[..., "str | Awaitable[str]"]

# Resolves the write provenance :class:`Actor`. ``resolve_web_actor`` takes no
# arguments and ``resolve_internal_actor`` takes the request, so the argument
# list stays open; only the concrete return type is fixed.
ActorResolver = Callable[..., Actor]


# A FastAPI dependency that builds a request-scoped service ``S``. FastAPI fills
# the inner provider's own parameters, so the call site passes nothing; the
# argument list stays open and only the built type is fixed.
type ServiceProvider[S] = Callable[..., S]


def publishing_provider[S](
    build: Callable[[AsyncSession, WriteEventPublisher], S],
) -> ServiceProvider[S]:
    """Build a write-path service dependency: read the events seam, bind the service."""

    def provider(request: Request, session: AsyncSession = Depends(get_session)) -> S:
        return build(session, get_events(request.app))

    return provider


def session_provider[S](build: Callable[[AsyncSession], S]) -> ServiceProvider[S]:
    """Build a read-only service dependency over the caller's session."""

    def provider(session: AsyncSession = Depends(get_session)) -> S:
        return build(session)

    return provider
