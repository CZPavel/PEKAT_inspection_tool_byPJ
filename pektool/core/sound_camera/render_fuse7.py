from __future__ import annotations

from typing import Dict, Literal, Tuple

import cv2
import numpy as np

from .render_classic import classic_dependencies_status

try:
    from scipy import signal as sps
except Exception:  # pragma: no cover - optional runtime dependency
    sps = None


Fuse7Style = Literal["fuse7", "fuse4_base"]
Fuse7Profile = Literal["default", "ref_compat"]
ScaleMode = Literal["top_db", "percentile"]


def _require_dependencies() -> None:
    status = classic_dependencies_status()
    if not bool(status.get("scipy_available", False)):
        raise RuntimeError(str(status.get("error", "scipy is required")))
    if sps is None:
        raise RuntimeError("scipy.signal is required for FUSE rendering")


def _to_mono(samples: np.ndarray) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        return arr.mean(axis=1, dtype=np.float32)
    raise ValueError(f"Unsupported audio shape: {arr.shape}")


def _hz_to_mel(freq_hz: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + np.asarray(freq_hz, dtype=np.float32) / 700.0)


def _mel_to_hz(mel_value: np.ndarray) -> np.ndarray:
    return 700.0 * (np.power(10.0, np.asarray(mel_value, dtype=np.float32) / 2595.0) - 1.0)


def _mel_filterbank(
    *,
    sr: int,
    n_fft: int,
    n_mels: int,
    fmin: float,
    fmax: float,
) -> np.ndarray:
    if n_mels <= 0:
        raise ValueError("n_mels must be > 0")
    nyquist = float(sr) / 2.0
    fmin = float(max(0.0, fmin))
    fmax = float(min(max(fmax, fmin + 1.0), nyquist))

    freqs = np.linspace(0.0, nyquist, int(n_fft // 2 + 1), dtype=np.float32)
    mel_points = np.linspace(
        float(_hz_to_mel(np.array([fmin], dtype=np.float32))[0]),
        float(_hz_to_mel(np.array([fmax], dtype=np.float32))[0]),
        n_mels + 2,
        dtype=np.float32,
    )
    hz_points = _mel_to_hz(mel_points).astype(np.float32)

    fb = np.zeros((n_mels, freqs.size), dtype=np.float32)
    for idx in range(n_mels):
        left = hz_points[idx]
        center = hz_points[idx + 1]
        right = hz_points[idx + 2]
        if center <= left:
            center = left + 1e-6
        if right <= center:
            right = center + 1e-6
        left_slope = (freqs - left) / (center - left)
        right_slope = (right - freqs) / (right - center)
        tri = np.maximum(0.0, np.minimum(left_slope, right_slope))
        area_norm = 2.0 / max(1e-6, right - left)
        fb[idx, :] = tri * area_norm
    return fb


def _power_to_db_top(power: np.ndarray, top_db: float) -> np.ndarray:
    db = 10.0 * np.log10(np.maximum(power, 1e-12))
    db -= float(np.max(db))
    return np.clip(db, -float(top_db), 0.0).astype(np.float32)


def _scale_db_to_norm(
    db: np.ndarray,
    *,
    scale_mode: ScaleMode,
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
    return np.clip((db + float(top_db)) / float(top_db), 0.0, 1.0).astype(np.float32)


def _normalize_percentile(values: np.ndarray, p: float) -> np.ndarray:
    ref = float(np.percentile(values, min(max(p, 1.0), 99.99)))
    if ref <= 1e-12:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip(values / ref, 0.0, 1.0).astype(np.float32)


def _resize_interp(
    *,
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
    profile: Fuse7Profile,
) -> int:
    if profile == "ref_compat":
        return cv2.INTER_AREA
    if dst_w < src_w or dst_h < src_h:
        return cv2.INTER_AREA
    return cv2.INTER_LINEAR


def _to_u8(values_01: np.ndarray) -> np.ndarray:
    return np.clip(np.round(np.asarray(values_01, dtype=np.float32) * 255.0), 0, 255).astype(np.uint8)


def render_fuse7_image(
    samples: np.ndarray,
    source_sr: int,
    *,
    width: int,
    height: int,
    style: Fuse7Style = "fuse7",
    n_fft: int = 4096,
    win_ms: float = 25.0,
    hop_ms: float = 1.0,
    fmin: float = 0.0,
    fmax: float = 24000.0,
    n_mels_hue: int = 128,
    n_mels_layers: int = 64,
    top_db: float = 80.0,
    scale_mode: ScaleMode = "top_db",
    p_lo: float = 1.0,
    p_hi: float = 99.0,
    fuse7_profile: Fuse7Profile = "ref_compat",
    norm_p: float = 99.5,
    freq_green_bias: float = 0.15,
    edge_base_alpha: float = 0.25,
    flux_gain: float = 110.0,
    edge_gain: float = 70.0,
) -> Tuple[np.ndarray, Dict[str, float | int | str]]:
    _require_dependencies()
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
    if float(norm_p) <= 0.0 or float(norm_p) > 100.0:
        raise ValueError("norm_p must be in range (0, 100]")
    if float(edge_base_alpha) < 0.0 or float(edge_base_alpha) > 1.0:
        raise ValueError("edge_base_alpha must be in range [0, 1]")

    mono = _to_mono(samples)
    if mono.size < 16:
        return np.zeros((height, width, 3), dtype=np.uint8), {
            "width_px": int(width),
            "height_px": int(height),
            "frames": 0,
            "style": str(style),
        }

    n_fft = int(max(256, n_fft))
    win_len = int(max(32, round(float(win_ms) * float(source_sr) / 1000.0)))
    hop_len = int(max(1, round(float(hop_ms) * float(source_sr) / 1000.0)))
    win_len = min(win_len, n_fft)
    fmax = min(float(max(100.0, fmax)), float(source_sr) / 2.0)

    _freqs, _times, stft = sps.stft(
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
            "style": str(style),
        }

    fb_hue = _mel_filterbank(
        sr=int(source_sr),
        n_fft=n_fft,
        n_mels=int(n_mels_hue),
        fmin=float(fmin),
        fmax=float(fmax),
    )
    fb_layers = _mel_filterbank(
        sr=int(source_sr),
        n_fft=n_fft,
        n_mels=int(n_mels_layers),
        fmin=float(fmin),
        fmax=float(fmax),
    )
    mel_hue = (fb_hue @ power).astype(np.float32)
    mel_layers = (fb_layers @ power).astype(np.float32)

    hue_db = _power_to_db_top(mel_hue, float(top_db))
    energy_norm = _scale_db_to_norm(
        hue_db,
        scale_mode=scale_mode,
        top_db=float(top_db),
        p_lo=float(p_lo),
        p_hi=float(p_hi),
    )
    layers_db = _power_to_db_top(mel_layers, float(top_db))

    d1 = np.diff(layers_db, axis=1, prepend=layers_db[:, :1])
    d2 = np.diff(d1, axis=1, prepend=d1[:, :1])
    edge_mag = np.sqrt(d1 * d1 + d2 * d2).astype(np.float32)
    edge_norm = _normalize_percentile(edge_mag, float(norm_p))

    flux = np.maximum(np.diff(mel_layers, axis=1, prepend=mel_layers[:, :1]), 0.0)
    flux = np.log1p(flux).astype(np.float32)
    flux_norm = _normalize_percentile(flux, float(norm_p))

    src_h, src_w = int(energy_norm.shape[0]), int(energy_norm.shape[1])
    interp = _resize_interp(
        src_w=src_w,
        src_h=src_h,
        dst_w=int(width),
        dst_h=int(height),
        profile=fuse7_profile,
    )

    hue_u8 = _to_u8(energy_norm)
    hsv = np.zeros((src_h, src_w, 3), dtype=np.uint8)
    hue_grad = np.linspace(0, 179, src_h, dtype=np.uint8).reshape(src_h, 1)
    hsv[..., 0] = hue_grad
    hsv[..., 1] = 255
    hsv[..., 2] = hue_u8
    base = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    base = cv2.resize(base, (int(width), int(height)), interpolation=interp)

    edge_u8 = cv2.resize(_to_u8(edge_norm), (int(width), int(height)), interpolation=interp)
    flux_u8 = cv2.resize(_to_u8(flux_norm), (int(width), int(height)), interpolation=interp)

    base_f = base.astype(np.float32)
    if abs(float(freq_green_bias)) > 1e-9:
        grad = np.linspace(0.0, 255.0, int(height), dtype=np.float32).reshape(int(height), 1)
        base_f[:, :, 1] = np.clip(
            base_f[:, :, 1] + (grad - 128.0) * float(freq_green_bias),
            0.0,
            255.0,
        )
    if float(edge_base_alpha) > 0.0:
        edges_rgb = cv2.cvtColor(edge_u8, cv2.COLOR_GRAY2BGR).astype(np.float32)
        alpha = float(edge_base_alpha)
        base_f = np.clip((1.0 - alpha) * base_f + alpha * edges_rgb, 0.0, 255.0)
    fuse4_base = base_f.astype(np.uint8)

    if style == "fuse4_base":
        output = fuse4_base
    else:
        fuse7 = fuse4_base.astype(np.float32)
        flux_n = flux_u8.astype(np.float32) / 255.0
        edge_n = edge_u8.astype(np.float32) / 255.0
        fuse7[:, :, 2] = np.clip(fuse7[:, :, 2] + float(flux_gain) * flux_n, 0.0, 255.0)
        fuse7[:, :, 0] = np.clip(fuse7[:, :, 0] + float(edge_gain) * edge_n, 0.0, 255.0)
        fuse7[:, :, 1] = np.clip(fuse7[:, :, 1] + float(edge_gain) * edge_n, 0.0, 255.0)
        fuse7[:, :, 2] = np.clip(fuse7[:, :, 2] + float(edge_gain) * edge_n, 0.0, 255.0)
        output = fuse7.astype(np.uint8)

    meta: Dict[str, float | int | str] = {
        "width_px": int(width),
        "height_px": int(height),
        "frames": int(power.shape[1]),
        "style": str(style),
        "preset": "none",
        "n_fft": int(n_fft),
        "win_ms": float(win_ms),
        "hop_ms": float(hop_ms),
        "top_db": float(top_db),
        "fmax": float(fmax),
        "n_mels_hue": int(n_mels_hue),
        "n_mels_layers": int(n_mels_layers),
        "scale_mode": str(scale_mode),
        "p_lo": float(p_lo),
        "p_hi": float(p_hi),
        "fuse7_profile": str(fuse7_profile),
        "norm_p": float(norm_p),
        "freq_green_bias": float(freq_green_bias),
        "edge_base_alpha": float(edge_base_alpha),
        "flux_gain": float(flux_gain),
        "edge_gain": float(edge_gain),
    }
    return output, meta
