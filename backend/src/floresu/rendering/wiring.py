"""Compose the render module for the composition roots.

The render module is stateless (its only collaborator is the Typst compiler), so one
instance is shared across requests, mirroring the embedding resolver's wiring.
"""

from __future__ import annotations

from floresu.rendering.module import RenderModule
from floresu.rendering.typst import TypstPyCompiler


def build_render_module() -> RenderModule:
    """Build the process-wide render module over the in-process typst-py compiler."""
    return RenderModule(TypstPyCompiler())
