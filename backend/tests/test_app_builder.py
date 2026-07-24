"""Composition-root factories and the shared router block builder.

Sociable tests: build the real router block and the real apps. Their providers,
render module, and lazy object store are constructed, and no network call is
made. The tests assert the block's shape and mount order, that each factory
returns a fresh app, and that each factory mounts its own out-of-block surface
around the shared block.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI

from floresu.api.app_builder import build_shared_router_block
from floresu.api.main import app as external_app
from floresu.api.main import create_external_app
from floresu.api_internal.main import app as internal_app
from floresu.api_internal.main import create_internal_app
from floresu.core.actor import resolve_internal_actor, resolve_web_actor
from floresu.core.identity import require_internal_user, require_user
from floresu.core.providers import ActorResolver, Identity
from floresu.core.route_registry import mounted_product_routes
from floresu.core.settings import AppSettings
from floresu.resumes.cow import EditChannel
from tests.embedding_fakes import FakeEmbeddingProvider

MakeSettings = Callable[..., AppSettings]

# The eleven domains the shared block wires, in mount order.
_SHARED_ROUTER_COUNT = 11

_RESUME_TEMPLATES = "/resumes/templates"
_RESUME_BY_ID = "/resumes/{resume_id}"

# A representative prefix from each of the eleven shared domains.
_SHARED_PREFIXES = (
    "/sources",
    "/worklog",
    "/bullets",
    "/skills",
    "/identity-variants",
    "/job-applications",
    "/search",
    "/resumes",
)


def _paths(app: FastAPI) -> list[str]:
    return [key.path for key in mounted_product_routes(app)]


def _has_prefix(paths: list[str], prefix: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for path in paths)


def test_shared_block_wires_eleven_routers(make_settings: MakeSettings) -> None:
    block = build_shared_router_block(
        make_settings(),
        identity=require_user,
        actor=resolve_web_actor,
        channel=EditChannel.WEB,
        search_provider=FakeEmbeddingProvider(),
    )
    assert len(block) == _SHARED_ROUTER_COUNT


@pytest.mark.parametrize(
    ("identity", "actor", "channel"),
    [
        (require_user, resolve_web_actor, EditChannel.WEB),
        (require_internal_user, resolve_internal_actor, EditChannel.MCP),
    ],
)
def test_shared_block_wires_eleven_routers_for_both_axis_sets(
    make_settings: MakeSettings,
    identity: Identity,
    actor: ActorResolver,
    channel: EditChannel,
) -> None:
    block = build_shared_router_block(
        make_settings(),
        identity=identity,
        actor=actor,
        channel=channel,
        search_provider=FakeEmbeddingProvider(),
    )
    assert len(block) == _SHARED_ROUTER_COUNT


def test_shared_block_mounts_resume_templates_before_resume_id(
    make_settings: MakeSettings,
) -> None:
    app = FastAPI()
    for router in build_shared_router_block(
        make_settings(),
        identity=require_user,
        actor=resolve_web_actor,
        channel=EditChannel.WEB,
        search_provider=FakeEmbeddingProvider(),
    ):
        app.include_router(router)
    paths = _paths(app)
    # A bare GET /resumes/{resume_id} would otherwise capture "templates" as an id.
    assert paths.index(_RESUME_TEMPLATES) < paths.index(_RESUME_BY_ID)


def test_factories_return_fresh_distinct_apps() -> None:
    external = create_external_app()
    internal = create_internal_app()
    assert isinstance(external, FastAPI)
    assert isinstance(internal, FastAPI)
    assert external is not internal
    assert external.state.settings.service == "floresu-external"
    assert internal.state.settings.service == "floresu-internal"


def test_both_apps_mount_their_expected_routes_in_one_process() -> None:
    external_paths = _paths(external_app)
    internal_paths = _paths(internal_app)
    # The shared block is present on both apps.
    for prefix in _SHARED_PREFIXES:
        assert _has_prefix(external_paths, prefix), f"external missing {prefix}"
        assert _has_prefix(internal_paths, prefix), f"internal missing {prefix}"
    # The external app adds its own boundary: feed, accounts, and OAuth.
    assert _has_prefix(external_paths, "/feed")
    assert any(path.startswith("/account") for path in external_paths)
    # The internal app adds the worker-facing embed surface; the external app has none.
    assert _has_prefix(internal_paths, "/embed")
    assert not _has_prefix(external_paths, "/embed")


def test_both_apps_preserve_resume_template_mount_order() -> None:
    for paths in (_paths(external_app), _paths(internal_app)):
        assert paths.index(_RESUME_TEMPLATES) < paths.index(_RESUME_BY_ID)
