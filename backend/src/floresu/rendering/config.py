"""Rendering domain constants.

The output MIME type of every rendered resume, the single global template id P0
ships (also the fallback for an unknown id), and the Typst templates directory. The
templates live at the repo root (``templates/``) per the architecture; the path is
resolved from this file's location so it works whether the process runs from the
repo root or ``backend/``. The deployed backend image must include that directory
(see ``backend/Dockerfile``).
"""

from __future__ import annotations

from pathlib import Path

# The output MIME type of every rendered resume. Shared by the object-store put
# (content type) and the preview stream (response media type), so it is single-sourced.
PDF_MEDIA_TYPE = "application/pdf"

# The one global template P0 ships; also the fallback an unknown template id resolves
# to. Real templates are defined here (the resumes domain seeds a placeholder id).
DEFAULT_TEMPLATE_ID = "classic"

# Repo-root Typst templates directory: backend/src/floresu/rendering/config.py ->
# parents[4] is the repo root, matching how settings anchors the root .env file.
TEMPLATES_DIR = Path(__file__).resolve().parents[4] / "templates"
