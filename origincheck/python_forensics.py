"""Python fallback for the C++ forensic feature extractor."""

from __future__ import annotations

# pyright: reportMissingImports=false
import numpy as np


def _to_gray(rgb: np.ndarray) -> np.ndarray:
    img = rgb.astype(np.float64)
    return 0.299 * img[:, :, 0] + 0.587 * img[:, :, 1] + 0.114 * img[:, :, 2]


def _laplacian_var(gray: np.ndarray) -> float:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    center = gray[1:-1, 1:-1]
    lap = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4.0 * center
    return float(np.var(lap))


def _fft_metrics(gray: np.ndarray) -> tuple[float, float]:
    size = 256
    yy = (np.linspace(0, gray.shape[0] - 1, size)).astype(int)
    xx = (np.linspace(0, gray.shape[1] - 1, size)).astype(int)
    sampled = gray[np.ix_(yy, xx)]
    spec = np.fft.fftshift(np.fft.fft2(sampled))
    mag = np.abs(spec)
    cy, cx = size // 2, size // 2
    mag[cy, cx] = 0.0
    y, x = np.ogrid[:size, :size]
    dist = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    high = mag[dist > size / 4]
    total = float(np.sum(mag))
    ratio = float(np.sum(high) / total) if total > 1e-9 else 0.0
    mean_mag = float(np.mean(mag) + 1e-9)
    peakiness = float(np.max(mag) / mean_mag)
    return ratio, peakiness


def _saturation_stats(rgb: np.ndarray) -> tuple[float, float]:
    img = rgb.astype(np.float64) / 255.0
    mx = np.max(img, axis=2)
    mn = np.min(img, axis=2)
    sat = np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 1e-9)
    return float(np.mean(sat)), float(np.std(sat))


def _channel_corr(rgb: np.ndarray) -> float:
    r = rgb[:, :, 0].astype(np.float64).ravel()
    g = rgb[:, :, 1].astype(np.float64).ravel()
    b = rgb[:, :, 2].astype(np.float64).ravel()

    def corr(a: np.ndarray, c: np.ndarray) -> float:
        if a.size < 2 or float(np.std(a)) < 1e-9 or float(np.std(c)) < 1e-9:
            return 0.0
        return float(np.corrcoef(a, c)[0, 1])

    values = [corr(r, g), corr(g, b), corr(b, r)]
    return float(np.mean(values))


def _gradient_stats(gray: np.ndarray) -> tuple[float, float]:
    dx = np.diff(gray, axis=1)[:-1, :]
    dy = np.diff(gray, axis=0)[:, :-1]
    mag = np.sqrt(dx * dx + dy * dy)
    hist, _ = np.histogram(mag, bins=64, range=(0.0, 512.0), density=False)
    total = int(np.sum(hist))
    entropy = 0.0
    if total > 0:
        probs = hist[hist > 0] / total
        entropy = float(-np.sum(probs * np.log2(probs)))
    density = float(np.mean(mag > 18.0))
    return entropy, density


def _blockiness(gray: np.ndarray) -> float:
    if gray.shape[0] < 16 or gray.shape[1] < 16:
        return 0.0
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    x_boundary = dx[:, 7::8]
    y_boundary = dy[7::8, :]
    x_interior = np.delete(dx, np.arange(7, dx.shape[1], 8), axis=1)
    y_interior = np.delete(dy, np.arange(7, dy.shape[0], 8), axis=0)
    boundary = np.concatenate([x_boundary.ravel(), y_boundary.ravel()])
    interior = np.concatenate([x_interior.ravel(), y_interior.ravel()])
    b = float(np.mean(boundary)) if boundary.size else 0.0
    i = float(np.mean(interior)) if interior.size else 1.0
    return b / (i + 1e-6)


def extract_features(image: np.ndarray) -> dict[str, float]:
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("expected an RGB array with shape (H, W, 3)")

    # Vectorized 5x5 mean filter instead of the naive nested loop above for speed.
    gray = _to_gray(image)
    padded = np.pad(gray, 2, mode="edge")
    integral = np.pad(padded.cumsum(0).cumsum(1), ((1, 0), (1, 0)), mode="constant")
    win = 5
    rec = (
        integral[win:, win:]
        - integral[win:, :-win]
        - integral[:-win, win:]
        + integral[:-win, :-win]
    )
    blur = rec / 25.0
    noise_std = float(np.std(gray - blur))

    fft_high_ratio, fft_peakiness = _fft_metrics(gray)
    sat_mean, sat_std = _saturation_stats(image)
    grad_entropy, edge_density = _gradient_stats(gray)

    return {
        "laplacian_var": _laplacian_var(gray),
        "noise_residual_std": noise_std,
        "fft_high_ratio": fft_high_ratio,
        "fft_peakiness": fft_peakiness,
        "saturation_mean": sat_mean,
        "saturation_std": sat_std,
        "channel_corr": _channel_corr(image),
        "gradient_entropy": grad_entropy,
        "blockiness": _blockiness(gray),
        "edge_density": edge_density,
    }


