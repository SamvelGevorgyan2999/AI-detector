from __future__ import annotations

from dataclasses import dataclass, field


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _smoothstep(value: float, start: float, end: float) -> float:
    if end == start:
        return 0.0 if value < start else 1.0
    t = _clamp((value - start) / (end - start))
    return t * t * (3.0 - 2.0 * t)


@dataclass
class Signal:
    name: str
    score: float
    detail: str


@dataclass
class ScoreResult:
    ai_probability: float
    label: str
    summary: str
    signals: list[Signal] = field(default_factory=list)
    document_only: bool = False


AI_SOFTWARE_MARKERS = (
    "midjourney",
    "dall-e",
    "dall·e",
    "dalle",
    "stable diffusion",
    "automatic1111",
    "comfyui",
    "firefly",
    "leonardo",
    "ideogram",
    "runway",
    "synthesia",
    "chatgpt",
    "openai",
    "google imagen",
    "imagen",
    "flux.1",
    "flux1",
    "generative fill",
    "generative ai",
    "nightcafe",
    "playgroun",
)

CAMERA_MAKES = (
    "canon",
    "nikon",
    "sony",
    "fujifilm",
    "fuji",
    "apple",
    "samsung",
    "google",
    "huawei",
    "xiaomi",
    "oneplus",
    "leica",
    "panasonic",
    "olympus",
    "om digital",
    "pentax",
    "hasselblad",
    "dji",
    "gopro",
    "kodak",
    "ricoh",
)


def looks_like_text_document(white_ratio: float, unique_colors: int, edge_density: float) -> bool:
    return white_ratio > 0.82 and unique_colors < 48 and edge_density < 0.18


def score_features(
    features: dict[str, float],
    *,
    ela_mean: float,
    metadata_ai: bool,
    metadata_camera: bool,
    metadata_note: str,
    white_ratio: float,
    unique_colors: int,
) -> ScoreResult:
    if looks_like_text_document(white_ratio, unique_colors, features.get("edge_density", 0.0)):
        return ScoreResult(
            ai_probability=0.5,
            label="Not enough visual evidence",
            summary=(
                "This looks like a text or scanned document page rather than a photograph. "
                "Image-forensics cannot reliably judge AI generation here."
            ),
            signals=[
                Signal("Document layout", 0.5, f"White area {white_ratio:.0%}, {unique_colors} unique colors"),
            ],
            document_only=True,
        )

    signals: list[Signal] = []

    noise = features.get("noise_residual_std", 0.0)
    # Low residual noise is common in diffusion/GAN renders.
    noise_ai = _smoothstep(noise, 9.0, 2.2)
    signals.append(Signal("Sensor noise", noise_ai, f"Residual std {noise:.2f}"))

    lap = features.get("laplacian_var", 0.0)
    # Very smooth OR unnaturally over-sharpened both lean synthetic.
    if lap < 80:
        lap_ai = _smoothstep(lap, 80.0, 12.0)
        lap_detail = f"Smooth texture (var {lap:.1f})"
    else:
        lap_ai = _smoothstep(lap, 900.0, 2200.0)
        lap_detail = f"Texture variance {lap:.1f}"
    signals.append(Signal("Texture", lap_ai, lap_detail))

    high = features.get("fft_high_ratio", 0.0)
    freq_ai = _smoothstep(high, 0.28, 0.12)
    peakiness = features.get("fft_peakiness", 0.0)
    if peakiness > 40:
        freq_ai = _clamp(max(freq_ai, _smoothstep(peakiness, 40.0, 90.0)))
    signals.append(Signal("Frequency spectrum", freq_ai, f"High-freq ratio {high:.3f}"))

    sat = features.get("saturation_mean", 0.0)
    sat_ai = _smoothstep(sat, 0.42, 0.62)
    signals.append(Signal("Color saturation", sat_ai, f"Mean saturation {sat:.2f}"))

    corr = features.get("channel_corr", 0.0)
    corr_ai = _smoothstep(abs(corr), 0.92, 0.995)
    signals.append(Signal("Channel coupling", corr_ai, f"RGB correlation {corr:.3f}"))

    entropy = features.get("gradient_entropy", 0.0)
    ent_ai = _smoothstep(entropy, 3.4, 2.2)
    signals.append(Signal("Edge diversity", ent_ai, f"Gradient entropy {entropy:.2f}"))

    ela_ai = _smoothstep(ela_mean, 12.0, 3.0)
    signals.append(Signal("JPEG error level", ela_ai, f"ELA mean {ela_mean:.2f}"))

    weights = {
        "Sensor noise": 1.4,
        "Texture": 1.1,
        "Frequency spectrum": 1.2,
        "Color saturation": 0.6,
        "Channel coupling": 0.7,
        "Edge diversity": 0.9,
        "JPEG error level": 0.8,
    }
    weighted = sum(s.score * weights[s.name] for s in signals)
    total_w = sum(weights.values())
    ai_prob = weighted / total_w

    if metadata_ai:
        ai_prob = _clamp(max(ai_prob, 0.9) + 0.05)
        signals.insert(0, Signal("File metadata", 0.95, metadata_note or "Generator tag found"))
    elif metadata_camera:
        ai_prob = _clamp(ai_prob * 0.45)
        signals.insert(0, Signal("Camera metadata", 0.15, metadata_note or "Camera EXIF present"))
    elif metadata_note:
        signals.append(Signal("File metadata", 0.55, metadata_note))

    ai_prob = _clamp(ai_prob)

    if ai_prob >= 0.65:
        label = "AI generated"
        summary = "Forensic signals suggest this file was produced or heavily synthesized by a generative model."
    elif ai_prob <= 0.38:
        label = "Likely authentic"
        summary = "Natural noise, texture, and metadata are more consistent with a camera or conventional document."
    else:
        label = "Uncertain"
        summary = "Signals disagree. Compression, filters, or screenshots can hide origin — treat this as inconclusive."

    return ScoreResult(ai_probability=ai_prob, label=label, summary=summary, signals=signals)


