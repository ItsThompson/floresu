"""The template registry: listing and lookup with fallback to the P0 default."""

from __future__ import annotations

from floresu.rendering.config import DEFAULT_TEMPLATE_ID
from floresu.rendering.registry import list_templates, resolve_template


def test_list_templates_returns_the_registry_entries() -> None:
    infos = list_templates()
    ids = [info.id for info in infos]
    assert DEFAULT_TEMPLATE_ID in ids
    classic = next(info for info in infos if info.id == DEFAULT_TEMPLATE_ID)
    assert classic.name
    assert classic.description


def test_resolve_returns_the_requested_template() -> None:
    spec = resolve_template(DEFAULT_TEMPLATE_ID)
    assert spec.id == DEFAULT_TEMPLATE_ID
    assert spec.directory == "classic"
    assert spec.entrypoint == "main.typ"


def test_an_unknown_template_id_falls_back_to_the_p0_default() -> None:
    # The legacy placeholder id "default" (and any unknown id) resolves to the single
    # P0 template rather than erroring, so an old or mistyped id still renders.
    assert resolve_template("default").id == DEFAULT_TEMPLATE_ID
    assert resolve_template("does-not-exist").id == DEFAULT_TEMPLATE_ID
