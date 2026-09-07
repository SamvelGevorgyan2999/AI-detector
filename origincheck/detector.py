from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import numpy as np  # type: ignore[import-not-found]
from PIL import Image, ImageOps, UnidentifiedImageError  # type: ignore[import-not-found]

from origincheck.pdf_io import extract_pdf_metadata, render_pdf_pages
from origincheck.scoring import (
    AI_SOFTWARE_MARKERS,
    CAMERA_MAKES,
    ScoreResult,
    score_features,
)

try:
    cpp_forensics = importlib.import_module("origincheck._forensics")
except Exception:  # pragma: no cover - compiled module is optional
    cpp_forensics = None

from origincheck import python_forensics


def _load_engine():
    if cpp_forensics is not None:
        return cpp_forensics.extract_features, "C++"
    return python_forensics.extract_features, "Python"


extract_visual_features, ENGINE_NAME = _load_engine()


@dataclass
class AnalyzedImage:
    name: str
    image: Image.Image
    result: ScoreResult
    features: dict[str, float]


@dataclass
class DetectionReport:
    file_path: str
    file_type: str
    engine: str
    result: ScoreResult
    preview: Image.Image | None
    pages: list[AnalyzedImage] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _as_rgb(image: Image.Image) -> Image.Image:
    transposed = ImageOps.exif_transpose(image)
    if transposed is not None:
        image = transposed
    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, 0xFFFFFF)
        background.paste(image, mask=image.split()[-1])
        return background
    return image.convert("RGB").copy()


def _resize_for_analysis(image: Image.Image, max_side: int = 768) -> Image.Image:
    w, h = image.size
    longest = max(w, h)
    if longest <= max_side:
        return image
    scale = max_side / float(longest)
    return image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR)


def _ela_mean(image: Image.Image, quality: int = 90) -> float:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    recompressed = Image.open(buffer).convert("RGB")
    original = np.asarray(image, dtype=np.int16)
    recomputed = np.asarray(recompressed, dtype=np.int16)
    diff = np.abs(original - recomputed).astype(np.float64)
    return float(np.mean(diff))


def _white_ratio_and_colors(image: Image.Image) -> tuple[float, int]:
    arr = np.asarray(_resize_for_analysis(image, 320))
    white = np.all(arr > 245, axis=2)
    quantized = (arr.astype(np.uint16) // 16) * 16
    packed = (
        quantized[:, :, 0].astype(np.int32) * 256 * 256
        + quantized[:, :, 1].astype(np.int32) * 256
        + quantized[:, :, 2].astype(np.int32)
    )
    return float(np.mean(white)), int(np.unique(packed).size)


def _metadata_from_image(image: Image.Image) -> tuple[bool, bool, str]:
    text_blobs: list[str] = []
    info = getattr(image, "info", {}) or {}
    for key in ("software", "Software", "description", "comment", "parameters"):
        value = info.get(key)
        if value:
            text_blobs.append(str(value))

    try:
        exif = image.getexif()
    except Exception:
        exif = None

    make = ""
    model = ""
    if exif:
        make = str(exif.get(271, "") or "")
        model = str(exif.get(272, "") or "")
        software = str(exif.get(305, "") or "")
        artist = str(exif.get(315, "") or "")
        text_blobs.extend([make, model, software, artist])
        for value in exif.values():
            if isinstance(value, str):
                text_blobs.append(value)

    blob = " ".join(text_blobs).lower()
    if any(marker in blob for marker in AI_SOFTWARE_MARKERS):
        return True, False, "Image metadata names a generative tool"

    if make.lower().strip() in CAMERA_MAKES or any(brand in make.lower() for brand in CAMERA_MAKES):
        label = " ".join(part for part in (make, model) if part).strip()
        return False, True, f"Camera EXIF: {label}" if label else "Camera EXIF present"

    if not blob.strip():
        return False, False, "No camera EXIF (weak signal; many real files also strip it)"
    return False, False, "Metadata present but not camera-identifying"


def _metadata_from_pdf(meta: dict[str, str]) -> tuple[bool, bool, str]:
    blob = " ".join(meta.values()).lower()
    if any(marker in blob for marker in AI_SOFTWARE_MARKERS):
        return True, False, "PDF metadata names a generative tool"
    producer = meta.get("Producer") or meta.get("Creator") or ""
    if producer:
        return False, False, f"PDF producer: {producer}"
    return False, False, "No distinctive PDF producer tag"


def analyze_image(image: Image.Image, name: str, extra_meta: tuple[bool, bool, str] | None = None) -> AnalyzedImage:
    rgb = _as_rgb(image)
    analysis = _resize_for_analysis(rgb)
    array = np.ascontiguousarray(np.asarray(analysis, dtype=np.uint8))
    features = dict(extract_visual_features(array))
    ela = _ela_mean(analysis)
    white_ratio, unique_colors = _white_ratio_and_colors(analysis)
    meta_ai, meta_cam, meta_note = extra_meta if extra_meta is not None else _metadata_from_image(rgb)
    result = score_features(
        features,
        ela_mean=ela,
        metadata_ai=meta_ai,
        metadata_camera=meta_cam,
        metadata_note=meta_note,
        white_ratio=white_ratio,
        unique_colors=unique_colors,
    )
    return AnalyzedImage(name=name, image=rgb, result=result, features=features)


def _combine_results(pages: list[AnalyzedImage]) -> ScoreResult:
    visual_pages = [page for page in pages if not page.result.document_only]
    if not visual_pages:
        return pages[0].result if pages else ScoreResult(0.5, "Not enough visual evidence", "No pages could be analyzed.")

    # The strongest AI-like visual page drives the file-level call.
    chosen = max(visual_pages, key=lambda page: page.result.ai_probability)
    if chosen.result.ai_probability >= 0.65:
        summary = f"{chosen.name} is the strongest AI-like page ({chosen.result.ai_probability:.0%})."
    else:
        summary = chosen.result.summary
    return ScoreResult(
        ai_probability=chosen.result.ai_probability,
        label=chosen.result.label,
        summary=summary,
        signals=chosen.result.signals,
        document_only=False,
    )


def analyze_file(path: str | Path, file_type: str) -> DetectionReport:
    path = Path(path)
    kind = file_type.upper()
    notes: list[str] = []

    if kind in {"JPG", "IMAGE", "IMAGE FILE"}:
        try:
            with Image.open(path) as img:
                analyzed = analyze_image(img, path.name)
        except UnidentifiedImageError as exc:
            raise ValueError("This file is not a readable image.") from exc
        return DetectionReport(
            file_path=str(path),
            file_type="IMAGE",
            engine=ENGINE_NAME,
            result=analyzed.result,
            preview=analyzed.image,
            pages=[analyzed],
            notes=notes,
        )

    if kind == "PDF":
        pages = render_pdf_pages(path)
        if not pages:
            raise ValueError("The PDF has no pages to analyze.")
        meta = extract_pdf_metadata(path)
        extra = _metadata_from_pdf(meta)
        analyzed_pages = [analyze_image(page.image, page.label, extra_meta=extra) for page in pages]
        combined = _combine_results(analyzed_pages)
        if extra[2]:
            notes.append(extra[2])
        return DetectionReport(
            file_path=str(path),
            file_type="PDF",
            engine=ENGINE_NAME,
            result=combined,
            preview=analyzed_pages[0].image,
            pages=analyzed_pages,
            notes=notes,
        )

    raise ValueError("Choose an image or PDF before analyzing.")


