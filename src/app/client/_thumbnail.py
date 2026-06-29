from __future__ import annotations

from pathlib import Path

import fitz

# src/app/client/_thumbnail.py → four parents up to project root
_DEFAULT_THUMB_DIR = Path(__file__).parent.parent.parent.parent / "resource-thumb"
_DEFAULT_THUMB_WIDTH = 200


def _make_thumb(pdf_bytes: bytes, width: int, out_path: Path) -> None:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    zoom = width / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(out_path))
