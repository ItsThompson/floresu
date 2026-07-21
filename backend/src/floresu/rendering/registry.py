"""The template registry: the global P0 templates and lookup with fallback.

Templates are global in P0 and the registry ships exactly one, but the structure is
ready for growth: adding a global template is a new entry plus a Typst directory,
and later user templates reuse the same lookup seam. A :class:`TemplateSpec` carries
both the listing info the selector shows and where the template's Typst source lives.
"""

from __future__ import annotations

from dataclasses import dataclass

from floresu.core.logging import get_logger
from floresu.rendering.config import DEFAULT_TEMPLATE_ID
from floresu.rendering.schemas import TemplateInfo

_log = get_logger("floresu-rendering")


@dataclass(frozen=True)
class TemplateSpec:
    """A registered template: its listing info plus its Typst source location."""

    id: str
    name: str
    description: str
    directory: str
    entrypoint: str = "main.typ"

    @property
    def info(self) -> TemplateInfo:
        return TemplateInfo(id=self.id, name=self.name, description=self.description)


_CLASSIC = TemplateSpec(
    id=DEFAULT_TEMPLATE_ID,
    name="Classic",
    description=(
        "A single-page, ATS-safe resume: a bold name header, ruled section headings, "
        "and tight bullet lists in a standard serif font."
    ),
    directory="classic",
)

# The ordered registry. P0 ships one global template; adding another is an entry
# plus a Typst directory, and user templates later reuse this same seam.
_REGISTRY: dict[str, TemplateSpec] = {_CLASSIC.id: _CLASSIC}


def list_templates() -> list[TemplateInfo]:
    """The registry entries, in registration order."""
    return [spec.info for spec in _REGISTRY.values()]


def resolve_template(template_id: str) -> TemplateSpec:
    """The spec for ``template_id``, falling back to the P0 default for an unknown id.

    A template not found is not an error: it resolves to the single global P0
    template and logs a notice, so an old, mistyped, or placeholder id still renders.
    """
    spec = _REGISTRY.get(template_id)
    if spec is not None:
        return spec
    _log.info("template_fallback", requested=template_id, fell_back_to=DEFAULT_TEMPLATE_ID)
    return _REGISTRY[DEFAULT_TEMPLATE_ID]
