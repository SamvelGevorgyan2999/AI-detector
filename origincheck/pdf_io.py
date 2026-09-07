from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Any


@dataclass
class PdfPage:
    index: int
    image: Any
    label: str


pdfium = None


def _require_pdfium():
    global pdfium
    if pdfium is None:
        try:
            pdfium = importlib.import_module("pypdfium2")
        except ModuleNotFoundError as exc:
            raise RuntimeError("pypdfium2 is required to read PDF files") from exc
    return pdfium


def extract_pdf_metadata(path: str | Path) -> dict[str, str]:
    pdf = _require_pdfium().PdfDocument(str(path))
    try:
        raw = pdf.get_metadata_dict(skip_empty=True) or {}
        return {str(key): str(value) for key, value in raw.items() if value}
    finally:
        pdf.close()


def render_pdf_pages(path: str | Path, max_pages: int = 4, scale: float = 1.8) -> list[PdfPage]:
    pdf = _require_pdfium().PdfDocument(str(path))
    pages: list[PdfPage] = []
    try:
        count = min(len(pdf), max_pages)
        for i in range(count):
            page = pdf[i]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil().convert("RGB")
            pages.append(PdfPage(index=i, image=image, label=f"Page {i + 1}"))
    finally:
        pdf.close()
    return pages


