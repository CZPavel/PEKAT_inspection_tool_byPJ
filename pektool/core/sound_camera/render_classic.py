from __future__ import annotations

from typing import Dict, Literal, Tuple

import cv2
import numpy as np

try:
    from scipy import signal as sps
except Exception:  # pragma: no cover - optional runtime dependency
    sps = None


ClassicPreset = Literal["none", "classic_fhd", "classic_impulse"]
ClassicDetailMode = Literal["off", "highpass", "edgesobel"]
ClassicColormap = Literal["none", "gray", "turbo", "viridis", "magma"]
ClassicFreqInterp = Literal["auto", "area", "linear", "nearest"]
ClassicAxisMode = Literal["linear", "log", "mel"]
ClassicScaleMode = Literal["top_db", "percentile"]
_SCIPY_ERROR = "Classic renderer requires scipy. Install scipy>=1.10."


def classic_dependencies_status() -> Dict[str, str | bool]:
    return {
        "scipy_available": bool(sps is not None),
        "error": "" if sps is not None else _SCIPY_ERROR,
    }


def _require_classic_dependencies() -> None:
    if sps is None:
        raise RuntimeError(_SCIPY_ERROR)


def _to_mono(samples: np.ndarray) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        return arr.mean(axis=1, dtype=np.float32)
    raise ValueError(f"Unsupported audio shape: {arr.shape}")


def _interp_flag(mode: ClassicFreqInterp, width: int) -> int:
    if mode == "area":
        return cv2.INTER_AREA
    if mode == "linear":
        return cv2.INTER_LINEAR
    if mode == "nearest":
        return cv2.INTER_NEAREST
    # auto
    return cv2.INTER_AREA if width > 1200 else cv2.INTER_LINEAR


def _apply_colormap(gray_u8: np.ndarray, colormap: ClassicColormap) -> np.ndarray:
    if colormap in {"none", "gray"}:
        return cv2.cvtColor(gray_u8, cv2.COLOR_GRAY2BGR)
    if colormap == "turbo":
        return cv2.applyColorMap(gray_u8, cv2.COLORMAP_TURBO)
    if colormap == "viridis":
        return cv2.applyColorMap(gray_u8, cv2.COLORMAP_VIRIDIS)
    if colormap == "magma":
        return cv2.applyColorMap(gray_u8, cv2.COLORMAP_MAGMA)
    return cv2.cvtColor(gray_u8, cv2.COLOR_GRAY2BGR)


def _hz_to_mel(freq_hz: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + np.asarray(freq_hz, dtype=np.float32) / 700.0)


def _mel_to_hz(mel_value: np.ndarray) -> np.ndarray:
    return 700.0 * (np.power(10.0, np.asarray(mel_value, dtype=np.float32) / 2595.0) - 1.0)


def _scale_to_norm(
    db: np.ndarray,
    *,
    scale_mode: ClassicScaleMode,
    top_db: float,
    p_lo: float,
    p_hi: float,
) -> np.ndarray:
    if scale_mode == "percentile":
        lo = float(np.percentile(db, p_lo))
        hi = float(np.percentile(db, p_hi))
        if hi <= lo:
            hi = lo + 1e-6
        return np.clip((db - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)

    db = np.clip(db, -float(top_db), 0.0)
    return np.clip((db + float(top_db)) / float(top_db), 0.0, 1.0).astype(np.float32)


def _remap_frequency_axis(
    norm: np.ndarray,
    freqs_hz: np.ndarray,
    *,
    axis_mode: ClassicAxisMode,
    fmax_hz: float,
) -> Tuple[np.ndarray, float]:
    if axis_mode == "linear":
        return norm, 0.0

    rows, cols = norm.shape
    if rows < 2:
        return norm, 0.0

    freqs = np.asarray(freqs_hz, dtype=np.float32)
    f_hi = float(min(max(fmax_hz, 1.0), float(freqs[-1])))
    if axis_mode == "log":
        if len(freqs) > 1:
            f_floor = float(max(20.0, freqs[1]))
        else:
            f_floor = 20.0
        if f_hi <= f_floor:
            f_hi = f_floor + 1.0
        target_hz = np.geomspace(f_floor, f_hi, rows, dtype=np.float32)
    elif axis_mode == "mel":
        mel_lo = float(_hz_to_mel(np.array([max(0.0, freqs[0])], dtype=np.float32))[0])
        mel_hi = float(_hz_to_mel(np.array([f_hi], dtype=np.float32))[0])
        target_hz = _mel_to_hz(np.linspace(mel_lo, mel_hi, rows, dtype=np.float32))
        f_floor = float(target_hz[0]) if target_hz.size else 0.0
    else:
        raise ValueError(f"Unsupported axis_mode: {axis_mode}")

    remapped = np.empty_like(norm, dtype=np.float32)
    for col in range(cols):
        remapped[:, col] = np.interp(
            target_hz,
            freqs,
            norm[:, col],
            left=float(norm[0, col]),
            right=float(norm[-1, col]),
        )
    return remapped, float(f_floor)


def render_classic_image(
    samples: np.ndarray,
    source_sr: int,
    *,
    width: int,
    height: int,
    preset: ClassicPreset = "none",
    n_fft: int = 4096,
    win_ms: float = 25.0,
    hop_ms: float = 1.0,
    top_db: float = 80.0,
    fmax: float = 24000.0,
    colormap: ClassicColormap = "gray",
    gamma: float = 1.0,
    detail_mode: ClassicDetailMode = "off",
    detail_sigma: float = 1.2,
    detail_gain: float = 70.0,
    detail_p: float = 99.5,
    freq_interp: ClassicFreqInterp = "auto",
    axis_mode: ClassicAxisMode = "linear",
    scale_mode: ClassicScaleMode = "top_db",
    p_lo: float = 1.0,
    p_hi: float = 99.0,
) -> Tuple[np.ndarray, Dict[str, float | int | str]]:
    _require_classic_dependencies()
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if source_sr <= 0:
        raise ValueError("source_sr must be positive")
    if float(win_ms) <= 0:
        raise ValueError("win_ms must be > 0")
    if float(hop_ms) <= 0:
        raise ValueError("hop_ms must be > 0")
    if float(hop_ms) > float(win_ms):
        raise ValueError("hop_ms must be <= win_ms")
    if float(top_db) <= 0:
        raise ValueError("top_db must be > 0")
    if float(fmax) <= 0:
        raise ValueError("fmax must be > 0")
    if float(p_lo) >= float(p_hi):
        raise ValueError("p_lo must be lower than p_hi")
    if axis_mode == "log" and float(fmax) <= 20.0:
        raise ValueError("axis_mode=log requires fmax > 20 Hz")

    mono = _to_mono(samples)
    if mono.size < 16:
        return np.zeros((height, width, 3), dtype=np.uint8), {
            "width_px": int(width),
            "height_px": int(height),
            "frames": 0,
            "freq_bins": 0,
            "style": "classic",
        }

    n_fft = int(max(256, n_fft))
    win_len = int(max(32, round(float(win_ms) * float(source_sr) / 1000.0)))
    hop_len = int(max(1, round(float(hop_ms) * float(source_sr) / 1000.0)))
    win_len = min(win_len, n_fft)

    freqs, _times, stft = sps.stft(
        mono,
        fs=int(source_sr),
        nperseg=win_len,
        noverlap=max(0, win_len - hop_len),
        nfft=n_fft,
        padded=False,
        boundary=None,
    )
    power = np.abs(stft).astype(np.float32) ** 2
    if power.size == 0:
        return np.zeros((height, width, 3), dtype=np.uint8), {
            "width_px": int(width),
            "height_px": int(height),
            "frames": 0,
            "freq_bins": 0,
            "style": "classic",
        }

    fmax = min(float(max(100.0, fmax)), float(source_sr) / 2.0)
    if fmax <= 0:
        raise ValueError("fmax must be > 0 and <= Nyquist frequency")
    fmax_idx = int(np.searchsorted(freqs, fmax, side="right"))
    fmax_idx = max(2, min(fmax_idx, power.shape[0]))
    power = power[:fmax_idx, :]
    freqs_used = freqs[:fmax_idx]

    db = 10.0 * np.log10(power + 1e-12)
    db -= float(np.max(db))
    norm = _scale_to_norm(
        db,
        scale_mode=scale_mode,
        top_db=float(top_db),
        p_lo=float(p_lo),
        p_hi=float(p_hi),
    )
    norm, f_floor_hz = _remap_frequency_axis(
        norm,
        freqs_used,
        axis_mode=axis_mode,
        fmax_hz=fmax,
    )

    gamma = max(1e-6, float(gamma))
    norm = np.power(norm, 1.0 / gamma).astype(np.float32)

    gray_u8 = np.clip(np.round(norm * 255.0), 0, 255).astype(np.uint8)
    detail_norm = np.zeros_like(norm, dtype=np.float32)
    if detail_mode == "highpass":
        blur = cv2.GaussianBlur(norm, (0, 0), max(0.1, float(detail_sigma)))
        detail_norm = np.clip(norm - blur, 0.0, 1.0)
    elif detail_mode == "edgesobel":
        gx = cv2.Sobel(norm, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(norm, cv2.CV_32F, 0, 1, ksize=3)
        grad = np.sqrt(gx * gx + gy * gy)
        p = float(np.percentile(grad, min(max(detail_p, 1.0), 99.9)))
        detail_norm = np.clip(grad / max(1e-6, p), 0.0, 1.0)

    bgr = _apply_colormap(gray_u8, colormap)
    if detail_mode != "off":
        overlay_gain = max(0.0, float(detail_gain)) / 100.0
        overlay = np.clip(detail_norm * 255.0 * overlay_gain, 0, 255).astype(np.uint8)
        overlay_bgr = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGR)
        bgr = np.clip(bgr.astype(np.float32) + overlay_bgr.astype(np.float32), 0, 255).astype(np.uint8)

    interp = _interp_flag(freq_interp, width)
    resized = cv2.resize(bgr, (int(width), int(height)), interpolation=interp)
    resized = cv2.flip(resized, 0)
    meta: Dict[str, float | int | str] = {
        "width_px": int(width),
        "height_px": int(height),
        "frames": int(power.shape[1]),
        "freq_bins": int(norm.shape[0]),
        "fmax_used_hz": float(freqs_used[-1] if freqs_used.size else 0.0),
        "f_floor_hz": float(f_floor_hz),
        "style": "classic",
        "preset": str(preset),
        "n_fft": int(n_fft),
        "win_ms": float(win_ms),
        "hop_ms": float(hop_ms),
        "top_db": float(top_db),
        "fmax": float(fmax),
        "colormap": str(colormap),
        "gamma": float(gamma),
        "detail_mode": str(detail_mode),
        "detail_sigma": float(detail_sigma),
        "detail_gain": float(detail_gain),
        "detail_p": float(detail_p),
        "freq_interp": str(freq_interp),
        "axis_mode": str(axis_mode),
        "scale_mode": str(scale_mode),
        "p_lo": float(p_lo),
        "p_hi": float(p_hi),
    }
    return resized, meta
