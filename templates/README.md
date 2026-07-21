# templates

Typst resume templates and shared partials. The rendering module compiles a
resume document plus a template into PDF bytes.

## Layout

Each template is a directory with an `main.typ` entry point and a `template.typ`
of layout functions. The render module invokes `main.typ`, passing the resolved
resume document as a JSON string on `sys.inputs.data` (never as Typst source), so
user text is always content and can never inject markup.

| Template | Description |
|----------|-------------|
| `classic/` | The P0 global template: a single-page, ATS-safe layout (bold name header, ruled section headings, tight bullet lists, standard serif font). Original work authored for Floresu, inspired by the common single-column technical-resume layout. |

Output is deterministic across hosts: the compiler runs with only its embedded
fonts, so no system fonts or font mounts are required.
