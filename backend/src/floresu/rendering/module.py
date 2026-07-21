"""The render module: a resolved resume document plus a template to PDF bytes.

A deep module with a small surface (:meth:`list_templates`, :meth:`render`) hiding
template selection, the pure input mapping, and Typst invocation. It writes nothing
to storage: callers decide whether the bytes are streamed (preview) or persisted
(export/finalize), which keeps it pure and testable (given a document and template
it returns bytes). The document it receives must already be resolved (references
inlined, identity snapshotted); the resume render service performs that resolution.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from floresu.rendering.config import TEMPLATES_DIR
from floresu.rendering.mapper import to_template_inputs
from floresu.rendering.registry import list_templates, resolve_template

if TYPE_CHECKING:
    from pathlib import Path

    from floresu.rendering.schemas import TemplateInfo
    from floresu.rendering.typst import TypstCompiler
    from floresu.resumes.document import ResumeDocument


class RenderModule:
    """Resume document + template id to PDF bytes; owns selection, mapping, invocation."""

    def __init__(self, compiler: TypstCompiler, *, templates_dir: Path = TEMPLATES_DIR) -> None:
        self._compiler = compiler
        self._templates_dir = templates_dir

    def list_templates(self) -> list[TemplateInfo]:
        """The registry entries the selector lists."""
        return list_templates()

    async def render(self, document: ResumeDocument, template_id: str) -> bytes:
        """Compile the resolved document with the selected template into PDF bytes.

        An unknown ``template_id`` falls back to the single P0 template (with a
        logged notice). Typst compilation is CPU-bound and synchronous, so it runs
        off the event loop; it still completes in milliseconds.
        """
        spec = resolve_template(template_id)
        inputs = to_template_inputs(document)
        template_root = self._templates_dir / spec.directory
        entrypoint = template_root / spec.entrypoint
        data_json = inputs.model_dump_json()
        return await asyncio.to_thread(self._compiler.compile, entrypoint, template_root, data_json)
