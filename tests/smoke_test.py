"""Create sample files and run a headless detector smoke test."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from origincheck.detector import ENGINE_NAME, analyze_file
from origincheck.pdf_io import render_pdf_pages


def _write_smooth_jpg(path: Path) -> None:
    w, h = 640, 480
    pixels = [
        (
            min(255, int(40 + y * 0.35 + x * 0.08)),
            max(40, int(180 - abs(x - 320) * 0.2)),
            max(30, int(220 - y * 0.3)),
        )
        for y in range(h)
        for x in range(w)
    ]
    image = Image.new("RGB", (w, h))
    image.putdata(pixels)
    image.save(path, quality=95)


def _write_noisy_jpg(path: Path) -> None:
    import random

    rng = random.Random(7)
    pixels = []
    for _ in range(480 * 640):
        base = [rng.randrange(70, 190) for _ in range(3)]
        pixels.append(
            tuple(max(0, min(255, int(value + rng.gauss(0, 18)))) for value in base)
        )
    image = Image.new("RGB", (640, 480))
    image.putdata(pixels)
    image.save(path, quality=92)


def _write_png(path: Path) -> None:
    Image.new("RGBA", (32, 32), (40, 120, 200, 180)).save(path)


def _write_text_pdf(path: Path) -> None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument.new()
    pdf.new_page(width=595, height=842)
    pdf.save(path)
    pdf.close()


def main() -> None:
    samples = Path(__file__).resolve().parent.parent / "samples"
    samples.mkdir(exist_ok=True)
    smooth = samples / "smooth.jpg"
    noisy = samples / "noisy.jpg"
    png = samples / "sample.png"
    pdf_path = samples / "blank.pdf"
    _write_smooth_jpg(smooth)
    _write_noisy_jpg(noisy)
    _write_png(png)
    _write_text_pdf(pdf_path)

    print(f"engine={ENGINE_NAME}")
    for path, kind in ((smooth, "JPG"), (noisy, "JPG"), (png, "IMAGE"), (pdf_path, "PDF")):
        report = analyze_file(path, kind)
        print(f"{path.name}: {report.result.label} ({report.result.ai_probability:.0%}) — {report.result.summary}")

    pages = render_pdf_pages(pdf_path, max_pages=1)
    assert pages, "PDF render failed"
    print("pdf render ok", pages[0].image.size)


if __name__ == "__main__":
    main()


