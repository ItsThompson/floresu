"""The Typst-invocation seam and its in-process typst-py binding.

Typst invocation is hidden behind the narrow :class:`TypstCompiler` port so the
render module never depends on a concrete compiler and tests substitute a fake. The
production binding, :class:`TypstPyCompiler`, uses the in-process typst-py compiler:
it compiles with only the embedded fonts (``ignore_system_fonts``) so output is
deterministic across hosts, and it passes the resume data as a JSON string through
``sys.inputs`` (never as Typst source) so arbitrary user text is data, not markup.
A compile failure is surfaced as a :class:`RenderError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import typst

from floresu.rendering.errors import RenderError

if TYPE_CHECKING:
    from pathlib import Path

# The ``sys.inputs`` key the template decodes its resume data from (a JSON string).
_DATA_INPUT_KEY = "data"


class TypstCompiler(Protocol):
    """Compile a Typst entrypoint, with JSON resume data, into PDF bytes."""

    def compile(self, entrypoint: Path, root: Path, data_json: str) -> bytes: ...


class TypstPyCompiler:
    """The production compiler: the in-process typst-py binding."""

    def compile(self, entrypoint: Path, root: Path, data_json: str) -> bytes:
        """Compile ``entrypoint`` (rooted at ``root``) with the resume data as JSON."""
        try:
            return typst.compile(
                input=str(entrypoint),
                root=str(root),
                sys_inputs={_DATA_INPUT_KEY: data_json},
                ignore_system_fonts=True,
            )
        except typst.TypstError as exc:
            raise RenderError(_failure_detail(exc)) from exc


def _failure_detail(exc: typst.TypstError) -> str:
    """A recoverable, non-leaky message from a Typst compile failure."""
    message = getattr(exc, "message", "") or str(exc)
    return f"This resume could not be rendered: {message}"
