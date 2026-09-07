"""OriginCheck desktop GUI."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import cast

import customtkinter as ctk  # pyright: ignore[reportMissingImports]
from PIL import Image, ImageDraw, ImageFont, ImageOps  # pyright: ignore[reportMissingImports]

from origincheck.detector import ENGINE_NAME, DetectionReport, analyze_file

ACCENT = "#5EEAD4"
BG = "#0B1220"
CARD = "#121A2B"
CARD_ALT = "#182338"
MUTED = "#8B97A8"
TEXT = "#E8EEF7"
DANGER = "#FB7185"
OK = "#34D399"
WARN = "#FBBF24"


class OriginCheckApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OriginCheck — AI Content Detector")
        self.geometry("1120x720")
        self.minsize(960, 640)
        self.configure(fg_color=BG)

        self.file_type = ctk.StringVar(value="IMAGE")
        self.file_path: Path | None = None
        self.preview_image: ctk.CTkImage | None = None
        self.busy = False

        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color=BG, height=78)
        header.pack(fill="x", padx=24, pady=(18, 8))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="OriginCheck",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=TEXT,
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="Local forensic detector for image files and PDF pages",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=MUTED,
        ).pack(side="left", padx=(14, 0), pady=(8, 0))

        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_sidebar(body)
        self._build_workspace(body)
        self.type_toggle.configure(command=self._on_type_change)

    def _build_sidebar(self, parent: ctk.CTkFrame) -> None:
        side = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=18, width=300)
        side.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        side.grid_propagate(False)

        pad = {"padx": 20, "pady": (18, 6)}
        ctk.CTkLabel(side, text="FILE TYPE", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", **pad
        )
        self.type_toggle = ctk.CTkSegmentedButton(
            side,
            values=["IMAGE", "PDF"],
            variable=self.file_type,
            fg_color=CARD_ALT,
            selected_color="#0F766E",
            selected_hover_color="#0D9488",
            unselected_color=CARD_ALT,
            unselected_hover_color="#223049",
            text_color=TEXT,
            height=36,
        )
        self.type_toggle.pack(fill="x", padx=20, pady=(0, 12))
        self.type_toggle.set("IMAGE")

        ctk.CTkLabel(side, text="UPLOAD", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", padx=20, pady=(8, 6)
        )
        self.browse_btn = ctk.CTkButton(
            side,
            text="Choose file…",
            command=self._browse,
            fg_color="#134E4A",
            hover_color="#0F766E",
            text_color=TEXT,
            height=40,
            corner_radius=10,
        )
        self.browse_btn.pack(fill="x", padx=20)

        self.file_label = ctk.CTkLabel(
            side,
            text="No file selected",
            text_color=MUTED,
            wraplength=240,
            justify="left",
            font=ctk.CTkFont(size=13),
        )
        self.file_label.pack(anchor="w", padx=20, pady=12)

        self.analyze_btn = ctk.CTkButton(
            side,
            text="Analyze origin",
            command=self._analyze,
            fg_color=ACCENT,
            hover_color="#2DD4BF",
            text_color="#042F2E",
            height=44,
            corner_radius=10,
            font=ctk.CTkFont(size=15, weight="bold"),
            state="disabled",
        )
        self.analyze_btn.pack(fill="x", padx=20, pady=(8, 10))

        self.progress = ctk.CTkProgressBar(side, fg_color=CARD_ALT, progress_color=ACCENT, height=8)
        self.progress.pack(fill="x", padx=20, pady=(4, 8))
        self.progress.set(0)

        self.status = ctk.CTkLabel(side, text="Idle", text_color=MUTED, font=ctk.CTkFont(size=12))
        self.status.pack(anchor="w", padx=20)

        help_box = ctk.CTkFrame(side, fg_color=CARD_ALT, corner_radius=12)
        help_box.pack(fill="x", padx=20, pady=18)
        ctk.CTkLabel(
            help_box,
            text="How it works",
            text_color=TEXT,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            help_box,
            text=(
                "Image files are scanned for camera noise, frequency artifacts, "
                "JPEG error levels, and generator tags.\n\n"
                "PDF files are rendered page by page, then each page is scored the same way."
            ),
            text_color=MUTED,
            justify="left",
            wraplength=240,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=14, pady=(0, 14))

        ctk.CTkLabel(
            side,
            text=f"Engine: {ENGINE_NAME} forensics",
            text_color=ACCENT,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="bottom", padx=20, pady=16)

    def _build_workspace(self, parent: ctk.CTkFrame) -> None:
        workspace = ctk.CTkFrame(parent, fg_color=BG)
        workspace.grid(row=0, column=1, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=3)
        workspace.grid_rowconfigure(1, weight=2)
        workspace.grid_columnconfigure(0, weight=1)

        preview_card = ctk.CTkFrame(workspace, fg_color=CARD, corner_radius=18)
        preview_card.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        ctk.CTkLabel(
            preview_card,
            text="PREVIEW",
            text_color=MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(14, 0))
        self.preview_label = ctk.CTkLabel(preview_card, text="", fg_color=CARD_ALT, corner_radius=12)
        self.preview_label.pack(fill="both", expand=True, padx=18, pady=14)
        self._set_placeholder_preview("Select an image or PDF to begin")

        result_card = ctk.CTkFrame(workspace, fg_color=CARD, corner_radius=18)
        result_card.grid(row=1, column=0, sticky="nsew")
        result_card.grid_columnconfigure(1, weight=1)

        self.verdict = ctk.CTkLabel(
            result_card,
            text="Waiting for analysis",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=TEXT,
        )
        self.verdict.grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 4))

        self.summary = ctk.CTkLabel(
            result_card,
            text="Upload a file, then click Analyze origin.",
            text_color=MUTED,
            wraplength=720,
            justify="left",
            font=ctk.CTkFont(size=14),
        )
        self.summary.grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 8))

        self.score_bar = ctk.CTkProgressBar(result_card, fg_color=CARD_ALT, progress_color=WARN, height=12)
        self.score_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(4, 4))
        self.score_bar.set(0)

        self.score_caption = ctk.CTkLabel(result_card, text="AI likelihood —", text_color=MUTED)
        self.score_caption.grid(row=3, column=0, sticky="w", padx=18, pady=(0, 8))

        self.signals = ctk.CTkTextbox(
            result_card,
            fg_color=CARD_ALT,
            text_color=TEXT,
            height=120,
            font=ctk.CTkFont(size=13),
            wrap="word",
            activate_scrollbars=True,
        )
        self.signals.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=18, pady=(0, 16))
        result_card.grid_rowconfigure(4, weight=1)
        self.signals.insert("1.0", "Signals will appear here after a scan.")
        self.signals.configure(state="disabled")

    def _on_type_change(self, _value: str) -> None:
        self.file_path = None
        self.file_label.configure(text="No file selected")
        self.analyze_btn.configure(state="disabled")
        self._set_placeholder_preview(f"Choose a {_value} file")
        self._reset_result()

    def _browse(self) -> None:
        kind = self.file_type.get()
        if kind == "PDF":
            types = [("PDF files", "*.pdf")]
        else:
            types = [
                (
                    "Image files",
                    "*.jpg *.jpeg *.jpe *.png *.webp *.bmp *.gif *.tif *.tiff",
                ),
                ("All files", "*.*"),
            ]
        path = ctk.filedialog.askopenfilename(title=f"Select {kind} file", filetypes=types)
        if not path:
            return
        self.file_path = Path(path)
        self.file_label.configure(text=self.file_path.name)
        self.analyze_btn.configure(state="normal")
        self._show_preview(self.file_path, kind)
        self._reset_result()

    def _show_preview(self, path: Path, kind: str) -> None:
        try:
            if kind == "PDF":
                from origincheck.pdf_io import render_pdf_pages

                pages = render_pdf_pages(path, max_pages=1, scale=1.2)
                if not pages:
                    raise ValueError("empty PDF")
                image = pages[0].image
            else:
                with Image.open(path) as img:
                    transposed = ImageOps.exif_transpose(img)
                    if transposed is None:
                        raise ValueError("unable to transpose image")
                    image = transposed.convert("RGB").copy()
            self._set_preview_image(image)
        except Exception:
            self._set_placeholder_preview("Preview unavailable")

    def _set_placeholder_preview(self, message: str) -> None:
        image = Image.new("RGB", (920, 360), color=0x182338)
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("segoeui.ttf", 22)
        except OSError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), message, font=font)
        x = (image.width - (bbox[2] - bbox[0])) // 2
        y = (image.height - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), message, fill=(139, 151, 168), font=font)
        self._set_preview_image(image)

    def _set_preview_image(self, image: Image.Image) -> None:
        fitted = ImageOps.contain(image, (920, 360))
        canvas = Image.new("RGB", (920, 360), color=0x182338)
        offset = ((canvas.width - fitted.width) // 2, (canvas.height - fitted.height) // 2)
        canvas.paste(fitted, offset)
        photo = ctk.CTkImage(light_image=canvas, dark_image=canvas, size=(920, 360))
        self.preview_image = photo
        self.preview_label.configure(image=photo, text="")

    def _reset_result(self) -> None:
        self.verdict.configure(text="Waiting for analysis", text_color=TEXT)
        self.summary.configure(text="Upload a file, then click Analyze origin.")
        self.score_bar.set(0)
        self.score_caption.configure(text="AI likelihood —")
        self._set_signals("Signals will appear here after a scan.")

    def _set_signals(self, text: str) -> None:
        self.signals.configure(state="normal")
        self.signals.delete("1.0", "end")
        self.signals.insert("1.0", text)
        self.signals.configure(state="disabled")

    def _analyze(self) -> None:
        if self.busy or self.file_path is None:
            return
        self.busy = True
        self.analyze_btn.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        self.status.configure(text="Scanning forensic signals…")
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        path = self.file_path
        kind = self.file_type.get()

        def worker() -> None:
            try:
                report = analyze_file(path, kind)
                self.after(0, lambda: self._on_success(report))
            except Exception as exc:
                self.after(0, lambda: self._on_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _stop_busy(self) -> None:
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1)
        self.browse_btn.configure(state="normal")
        self.analyze_btn.configure(state="normal")

    def _on_error(self, message: str) -> None:
        self._stop_busy()
        self.status.configure(text="Analysis failed")
        self.verdict.configure(text="Could not analyze file", text_color=DANGER)
        self.summary.configure(text=message)
        self.score_bar.set(0)

    def _on_success(self, report: DetectionReport) -> None:
        self._stop_busy()
        self.status.configure(text=f"Done · {report.engine} engine")
        if report.preview is not None:
            self._set_preview_image(report.preview)

        color = WARN
        if report.result.label == "AI generated":
            color = DANGER
        elif report.result.label == "Likely authentic":
            color = OK
        elif report.result.label == "Not enough visual evidence":
            color = MUTED

        self.verdict.configure(text=report.result.label, text_color=color)
        self.summary.configure(text=report.result.summary)
        self.score_bar.configure(progress_color=color)
        self.score_bar.set(report.result.ai_probability)
        self.score_caption.configure(text=f"AI likelihood {report.result.ai_probability:.0%}")

        lines = []
        for signal in report.result.signals:
            lines.append(f"• {signal.name}: {signal.score:.0%} AI-leaning — {signal.detail}")
        if report.notes:
            lines.append("")
            lines.extend(f"• {note}" for note in report.notes)
        if len(report.pages) > 1:
            lines.append("")
            lines.append("Page scores:")
            for page in report.pages:
                lines.append(f"  {page.name}: {page.result.label} ({page.result.ai_probability:.0%})")
        lines.append("")
        lines.append("This is a local forensic estimate, not a courtroom-grade proof.")
        self._set_signals("\n".join(lines))


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = OriginCheckApp()
    app.mainloop()


if __name__ == "__main__":
    main()


