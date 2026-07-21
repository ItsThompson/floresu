"""The render module: template selection, pure mapping, and Typst invocation.

Two layers of coverage: the module wiring over a fake compiler (right entrypoint,
root, and mapped JSON; template fallback), and a real end-to-end render through the
in-process typst-py compiler proving the ATS-safe construction guarantee (a valid
PDF with real, selectable text), plus a Typst failure surfacing as a RenderError.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from floresu.rendering.errors import RenderError
from floresu.rendering.module import RenderModule
from floresu.rendering.typst import TypstPyCompiler
from tests.rendering_fakes import FakeTypstCompiler, build_resolved_document


def _extract_text(pdf: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf))
    return "\n".join(page.extract_text() for page in reader.pages)


async def test_render_passes_the_selected_template_and_mapped_json_to_the_compiler() -> None:
    compiler = FakeTypstCompiler()
    module = RenderModule(compiler, templates_dir=Path("/tmpl"))

    pdf = await module.render(build_resolved_document(), "classic")

    assert pdf == b"%PDF-1.7 fake"
    entrypoint, root, data_json = compiler.calls[0]
    assert root == Path("/tmpl/classic")
    assert entrypoint == Path("/tmpl/classic/main.typ")
    payload = json.loads(data_json)
    assert payload["full_name"] == "Ada Lovelace"
    assert payload["sections"][0]["title"] == "Summary"


async def test_an_unknown_template_id_renders_with_the_p0_default_directory() -> None:
    compiler = FakeTypstCompiler()
    module = RenderModule(compiler, templates_dir=Path("/tmpl"))

    await module.render(build_resolved_document(), "no-such-template")

    _, root, _ = compiler.calls[0]
    assert root == Path("/tmpl/classic")


def test_list_templates_exposes_the_registry() -> None:
    module = RenderModule(FakeTypstCompiler())
    assert any(info.id == "classic" for info in module.list_templates())


async def test_real_render_produces_a_pdf_with_selectable_text() -> None:
    # The real typst-py compiler + the committed classic template. Proves the ATS-safe
    # construction guarantee: a valid PDF whose text extracts (never text-in-image).
    module = RenderModule(TypstPyCompiler())

    pdf = await module.render(build_resolved_document(), "classic")

    assert pdf.startswith(b"%PDF")
    assert b"/ToUnicode" in pdf  # a unicode CMap: text is selectable / extractable
    text = _extract_text(pdf)
    assert "Ada Lovelace" in text
    assert "EXPERIENCE" in text  # section heading, uppercased by the template
    assert "algorithm" in text  # a bullet line


async def test_special_characters_in_user_text_are_content_not_typst_markup() -> None:
    # Data passed via sys.inputs is never Typst source, so markup characters render
    # literally rather than injecting formatting or breaking compilation.
    from tests.rendering_fakes import build_snapshot, local_section

    section = local_section("s", "work", "Experience", ["Used #hash, *stars*, [brackets], $x$."])
    module = RenderModule(TypstPyCompiler())

    pdf = await module.render(
        build_resolved_document(snapshot=build_snapshot(), sections=[section]), "classic"
    )

    text = _extract_text(pdf)
    assert "#hash" in text
    assert "*stars*" in text
    assert "[brackets]" in text


async def test_a_typst_compile_failure_becomes_a_render_error(tmp_path: Path) -> None:
    bad_template = tmp_path / "broken"
    bad_template.mkdir()
    (bad_template / "main.typ").write_text('#panic("boom")', encoding="utf-8")
    compiler = TypstPyCompiler()

    with pytest.raises(RenderError):
        compiler.compile(bad_template / "main.typ", bad_template, "{}")
