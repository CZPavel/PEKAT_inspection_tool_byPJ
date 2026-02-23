from __future__ import annotations

from functools import lru_cache
from typing import Dict, Literal, Tuple

import numpy as np


AccumMode = Literal["none", "max", "sum", "avg"]
PointRenderStyle = Literal["classic", "sharp_stamp", "square_stamp"]
ValueMode = Literal["radial", "flat"]
RotationMode = Literal["none", "plus45", "minus45"]
TauMode = Literal[1, 5, 10, 20, 50, "both"]


def _prepare_xy(samples_mono: np.ndarray, tau: int) -> Tuple[np.ndarray, np.ndarray]:
    samples = np.asarray(samples_mono, dtype=np.float32).reshape(-1)
    if tau <= 0:
        raise ValueError("tau must be > 0")
    if samples.size <= tau:
        return np.empty((0,), dtype=np.float32), np.empty((0,), dtype=np.float32)
    return samples[:-tau], samples[tau:]


def _accumulate_pixels(
    image: np.ndarray,
    y_pix: np.ndarray,
    x_pix: np.ndarray,
    rgb: np.ndarray,
    accum: AccumMode,
) -> np.ndarray:
    if accum == "none":
        image[y_pix, x_pix] = rgb
        return image
    if accum == "max":
        for c in range(3):
            np.maximum.at(image[..., c], (y_pix, x_pix), rgb[:, c])
        return image
    if accum == "sum":
        work = np.zeros_like(image, dtype=np.uint32)
        for c in range(3):
            np.add.at(work[..., c], (y_pix, x_pix), rgb[:, c].astype(np.uint32))
        np.clip(work, 0, 255, out=work)
        return work.astype(np.uint8)
    if accum == "avg":
        sums = np.zeros_like(image, dtype=np.uint32)
        counts = np.zeros(image.shape[:2], dtype=np.uint32)
        for c in range(3):
            np.add.at(sums[..., c], (y_pix, x_pix), rgb[:, c].astype(np.uint32))
        np.add.at(counts, (y_pix, x_pix), 1)
        denom = np.maximum(counts, 1)[:, :, None]
        out = sums / denom
        return np.clip(np.round(out), 0, 255).astype(np.uint8)
    raise ValueError(f"Unsupported accum mode: {accum}")


@lru_cache(maxsize=32)
def _disk_brush(radius: int, point_render_style: str):
    if radius <= 0:
        return (
            np.array([0], dtype=np.int32),
            np.array([0], dtype=np.int32),
            np.array([1.0], dtype=np.float32),
        )

    yy, xx = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    if point_render_style == "square_stamp":
        dx = xx.reshape(-1).astype(np.int32)
        dy = yy.reshape(-1).astype(np.int32)
        w = np.ones(dx.shape[0], dtype=np.float32)
        return dx, dy, w

    dist = np.sqrt((xx * xx + yy * yy).astype(np.float32))
    mask = dist <= float(radius)
    dx = xx[mask].astype(np.int32)
    dy = yy[mask].astype(np.int32)

    if point_render_style == "classic":
        d = dist[mask]
        w = 1.0 - (d / (radius + 1e-9)) * 0.65
        w = np.clip(w, 0.35, 1.0).astype(np.float32)
    elif point_render_style == "sharp_stamp":
        w = np.ones(dx.shape[0], dtype=np.float32)
    else:
        raise ValueError(f"Unsupported point_render_style: {point_render_style}")
    return dx, dy, w


def _expand_points_with_disk(
    x_pix: np.ndarray,
    y_pix: np.ndarray,
    rgb: np.ndarray,
    width: int,
    height: int,
    radius: int,
    point_render_style: PointRenderStyle,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if radius <= 0:
        return x_pix, y_pix, rgb
    dx, dy, weights = _disk_brush(radius, point_render_style)
    xp = x_pix[:, None] + dx[None, :]
    yp = y_pix[:, None] + dy[None, :]
    valid = (xp >= 0) & (xp < width) & (yp >= 0) & (yp < height)
    if not np.any(valid):
        return (
            np.empty((0,), dtype=np.int32),
            np.empty((0,), dtype=np.int32),
            np.empty((0, 3), dtype=np.uint8),
        )
    x_exp = xp[valid].astype(np.int32, copy=False)
    y_exp = yp[valid].astype(np.int32, copy=False)
    rgb_exp = np.repeat(rgb[:, None, :], dx.size, axis=1).astype(np.float32)
    rgb_exp *= weights[None, :, None]
    rgb_exp = rgb_exp[valid]
    return x_exp, y_exp, np.clip(np.round(rgb_exp), 0, 255).astype(np.uint8)


def _rotate_xy(xn: np.ndarray, yn: np.ndarray, rotation: RotationMode | str) -> Tuple[np.ndarray, np.ndarray]:
    mode = str(rotation)
    if mode == "none":
        return xn, yn
    if mode == "plus45":
        theta = np.pi / 4.0
    elif mode == "minus45":
        theta = -np.pi / 4.0
    else:
        raise ValueError("rotation must be one of: none, plus45, minus45")
    c = np.cos(theta).astype(np.float32)
    s = np.sin(theta).astype(np.float32)
    xr = (c * xn) - (s * yn)
    yr = (s * xn) + (c * yn)
    max_abs = max(float(np.max(np.abs(xr))), float(np.max(np.abs(yr))), 1e-9)
    xr = xr / max_abs
    yr = yr / max_abs
    np.clip(xr, -1.0, 1.0, out=xr)
    np.clip(yr, -1.0, 1.0, out=yr)
    return xr, yr


def _hsv_to_rgb_uint8(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    # Reference vectorized conversion from the lab implementation.
    h = np.asarray(h, dtype=np.float32)
    s = np.asarray(s, dtype=np.float32)
    v = np.asarray(v, dtype=np.float32)

    h = np.mod(h, 1.0)
    s = np.clip(s, 0.0, 1.0)
    v = np.clip(v, 0.0, 1.0)

    c = v * s
    h6 = h * 6.0
    x = c * (1.0 - np.abs((h6 % 2.0) - 1.0))
    m = v - c

    i = np.floor(h6).astype(np.int32) % 6

    r = np.zeros_like(v, dtype=np.float32)
    g = np.zeros_like(v, dtype=np.float32)
    b = np.zeros_like(v, dtype=np.float32)

    mask = i == 0
    r[mask], g[mask], b[mask] = c[mask], x[mask], 0.0
    mask = i == 1
    r[mask], g[mask], b[mask] = x[mask], c[mask], 0.0
    mask = i == 2
    r[mask], g[mask], b[mask] = 0.0, c[mask], x[mask]
    mask = i == 3
    r[mask], g[mask], b[mask] = 0.0, x[mask], c[mask]
    mask = i == 4
    r[mask], g[mask], b[mask] = x[mask], 0.0, c[mask]
    mask = i == 5
    r[mask], g[mask], b[mask] = c[mask], 0.0, x[mask]

    rgb = np.stack((r + m, g + m, b + m), axis=-1)
    return np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)


def _render_single_tau(
    samples_mono: np.ndarray,
    *,
    tau: int,
    width: int,
    height: int,
    accum: AccumMode = "none",
    point_size_step: int = 1,
    point_render_style: PointRenderStyle = "classic",
    value_mode: ValueMode = "radial",
    rotation: RotationMode = "none",
) -> Tuple[np.ndarray, Dict[str, float | int | str]]:
    if tau <= 0:
        raise ValueError("tau must be > 0")
    if tau not in {1, 5, 10, 20, 50}:
        raise ValueError("tau must be one of 1, 5, 10, 20, 50")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if point_size_step < 1 or point_size_step > 7:
        raise ValueError("point_size_step must be in range 1..7")
    if point_render_style not in {"classic", "sharp_stamp", "square_stamp"}:
        raise ValueError("point_render_style is invalid")
    if value_mode not in {"radial", "flat"}:
        raise ValueError("value_mode is invalid")

    image = np.zeros((height, width, 3), dtype=np.uint8)
    x, y = _prepare_xy(samples_mono, int(tau))
    n_points = x.size
    if n_points == 0:
        return image, {
            "tau": int(tau),
            "width_px": int(width),
            "height_px": int(height),
            "points": 0,
        }

    xn = x / (np.max(np.abs(x)) + 1e-9)
    yn = y / (np.max(np.abs(y)) + 1e-9)
    xr, yr = _rotate_xy(xn, yn, rotation)

    x_pix = np.floor(((xr + 1.0) / 2.0) * (width - 1)).astype(np.int32)
    y_pix = np.floor((1.0 - ((yr + 1.0) / 2.0)) * (height - 1)).astype(np.int32)
    np.clip(x_pix, 0, width - 1, out=x_pix)
    np.clip(y_pix, 0, height - 1, out=y_pix)

    if n_points == 1:
        h = np.array([0.0], dtype=np.float32)
    else:
        h = np.arange(n_points, dtype=np.float32) / float(n_points - 1)
    s = np.ones(n_points, dtype=np.float32)
    if value_mode == "radial":
        a = np.sqrt(xn * xn + yn * yn)
        v = a / (np.max(a) + 1e-9)
    else:
        v = np.ones(n_points, dtype=np.float32)

    rgb = _hsv_to_rgb_uint8(h, s, v)
    radius = int(point_size_step) - 1
    x_draw, y_draw, rgb_draw = _expand_points_with_disk(
        x_pix=x_pix,
        y_pix=y_pix,
        rgb=rgb,
        width=width,
        height=height,
        radius=radius,
        point_render_style=point_render_style,
    )
    image = _accumulate_pixels(image, y_draw, x_draw, rgb_draw, accum)
    bgr = image[..., ::-1].copy()
    meta: Dict[str, float | int | str] = {
        "tau": int(tau),
        "width_px": int(width),
        "height_px": int(height),
        "points": int(n_points),
        "accum": accum,
        "point_size_step": int(point_size_step),
        "point_render_style": point_render_style,
        "value_mode": value_mode,
        "rotation": rotation,
    }
    return bgr, meta


def render_lissajous_image(
    samples_mono: np.ndarray,
    *,
    tau: TauMode,
    width: int,
    height: int,
    accum: AccumMode = "none",
    point_size_step: int = 1,
    point_render_style: PointRenderStyle = "classic",
    value_mode: ValueMode = "radial",
    rotation: RotationMode = "none",
) -> Tuple[np.ndarray, Dict[str, float | int | str]]:
    tau_value = str(tau).strip().lower()
    if tau_value == "both":
        left, meta_left = _render_single_tau(
            samples_mono=samples_mono,
            tau=1,
            width=width,
            height=height,
            accum=accum,
            point_size_step=point_size_step,
            point_render_style=point_render_style,
            value_mode=value_mode,
            rotation=rotation,
        )
        right, meta_right = _render_single_tau(
            samples_mono=samples_mono,
            tau=5,
            width=width,
            height=height,
            accum=accum,
            point_size_step=point_size_step,
            point_render_style=point_render_style,
            value_mode=value_mode,
            rotation=rotation,
        )
        combined = np.concatenate([left, right], axis=1)
        meta: Dict[str, float | int | str] = {
            "tau": "both",
            "width_px": int(combined.shape[1]),
            "height_px": int(combined.shape[0]),
            "points": int(meta_left.get("points", 0)) + int(meta_right.get("points", 0)),
            "accum": accum,
            "point_size_step": int(point_size_step),
            "point_render_style": point_render_style,
            "value_mode": value_mode,
            "rotation": rotation,
        }
        return combined, meta

    try:
        tau_int = int(tau_value)
    except ValueError as exc:
        raise ValueError("tau must be one of 1, 5, 10, 20, 50, both") from exc
    return _render_single_tau(
        samples_mono=samples_mono,
        tau=tau_int,
        width=width,
        height=height,
        accum=accum,
        point_size_step=point_size_step,
        point_render_style=point_render_style,
        value_mode=value_mode,
        rotation=rotation,
    )
