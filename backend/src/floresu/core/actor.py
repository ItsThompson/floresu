"""Actor descriptor and its resolution at the two trust boundaries.

Provenance (human vs which named agent) is a first-class differentiator, so the
actor is resolved at the boundary and carried into every write alongside the
``user_id``. The reference architecture carried only a bare ``user_id``; Floresu
adds the actor so the audit log and activity feed can show "you" vs a named,
hash-colored agent.

The descriptor is tiny and serializable on purpose: it flows through service
methods into the write-event seam, an audit row (``actor_type``/``actor_label``),
and an SSE frame.

Two resolvers, one per boundary, mirror the identity pair
(:mod:`floresu.core.identity`): inject the matching strategy at each app rather
than branch on context.

- Web boundary  -> :func:`resolve_web_actor`      -> ``Actor(human)`` (no label).
- Internal boundary -> :func:`resolve_internal_actor` -> ``Actor(agent, label=X-Actor)``,
  and only behind a validated internal token so an agent actor can never be forged
  from untrusted headers.
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import Depends
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request

from floresu.core.headers import ACTOR_HEADER
from floresu.core.identity import require_internal_user


class ActorType(StrEnum):
    """Who performed a write."""

    HUMAN = "human"
    AGENT = "agent"


class Actor(BaseModel):
    """The provenance descriptor carried into every write.

    ``label`` names the agent (its OAuth ``client_id``) and is absent for a human,
    whose writes render as "you". Frozen so a resolved actor cannot be mutated as
    it flows through the service and event layers.
    """

    model_config = ConfigDict(frozen=True)

    type: ActorType
    label: str | None = None


def resolve_web_actor() -> Actor:
    """Web boundary: every authenticated write is the human themselves."""
    return Actor(type=ActorType.HUMAN)


def resolve_internal_actor(
    request: Request,
    _user_id: str = Depends(require_internal_user),
) -> Actor:
    """Internal boundary: the named agent behind a validated internal token.

    Depending on :func:`require_internal_user` makes the trust structural: the
    agent actor is produced only after the shared token is verified, so a route
    can never resolve an agent actor from untrusted headers. FastAPI caches the
    dependency, so the token is verified once per request even when the handler
    also injects ``require_internal_user`` for the ``user_id``.
    """
    raw = request.headers.get(ACTOR_HEADER)
    label = raw.strip() if raw else None
    return Actor(type=ActorType.AGENT, label=label or None)
