from __future__ import annotations

from typing import Dict, List, Tuple

import cv2
import numpy as np


STYLE_MODES = ("raw_stream", "bitplane_transpose", "delta_bitplane_transpose", "stack3")
PAYLOAD_VARIANTS = (
    "none",
    "perm_rgb",
    "perm_rbg",
    "perm_grb",
    "perm_gbr",
    "perm_brg",
    "perm_bgr",
    "invert_all",
    "invert_r",
    "invert_g",
    "invert_b",
    "xor80_all",
    "dark_gray_06",
    "dark_turbo_04",
)


def _resample_linear(signal: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    src = np.asarray(signal, dtype=np.float32).reshape(-1)
    if src_sr == dst_sr:
        return src
    if src.size <= 1:
        dst_n = max(1, int(round(src.size * float(dst_sr) / max(src_sr, 1))))
        return np.zeros(dst_n, dtype=np.float32)
    ratio = float(dst_sr) / float(src_sr)
    dst_n = max(1, int(round(src.size * ratio)))
    x_src = np.linspace(0.0, 1.0, src.size, endpoint=False, dtype=np.float64)
    x_dst = np.linspace(0.0, 1.0, dst_n, endpoint=False, dtype=np.float64)
    return np.interp(x_dst, x_src, src).astype(np.float32)


def _to_mono(samples: np.ndarray) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        return arr.mean(axis=1, dtype=np.float32)
    raise ValueError(f"Unexpected audio shape: {arr.shape}")


def _float_to_i16(signal: np.ndarray) -> np.ndarray:
    x = np.asarray(signal, dtype=np.float32)
    x = np.clip(x, -1.0, 1.0)
    return np.round(x * 32767.0).astype(np.int16)


def _resolve_hop_samples(overlap_percent: float) -> int:
    overlap = float(np.clip(overlap_percent, 0.0, 95.0))
    hop = int(round(96.0 * (1.0 - overlap / 100.0)))
    return max(1, hop)


def _prepare_pcm16_for_spec(samples_i16: np.ndarray, width_px: int, overlap_percent: float) -> tuple[np.ndarray, int]:
    hop = _resolve_hop_samples(overlap_percent)
    required = max(96, int(96 + max(0, int(width_px) - 1) * hop))
    src = np.asarray(samples_i16, dtype=np.int16).reshape(-1)
    if src.size >= required:
        return src[-required:], hop
    out = np.zeros(required, dtype=np.int16)
    out[-src.size :] = src
    return out, hop


def _pack_96bits_to_12bytes(bits01: np.ndarray) -> np.ndarray:
    bits = np.asarray(bits01, dtype=np.uint8).reshape(96)
    packed = np.packbits(bits, bitorder="big")
    return packed.astype(np.uint8)


def _encode_pcm16_raw_stream(samples_i16: np.ndarray, width_px: int, overlap_percent: float) -> np.ndarray:
    prepared, hop = _prepare_pcm16_for_spec(samples_i16, width_px, overlap_percent)
    out = np.zeros((64, width_px, 3), dtype=np.uint8)
    for col in range(width_px):
        start = col * hop
        chunk = prepared[start : start + 96]
        bytes_le = chunk.astype("<i2", copy=False).view(np.uint8).reshape(-1)
        out[:, col, :] = bytes_le.reshape(64, 3)
    return out


def _encode_pcm16_bitplanes(samples_i16: np.ndarray, width_px: int, overlap_percent: float) -> np.ndarray:
    prepared, hop = _prepare_pcm16_for_spec(samples_i16, width_px, overlap_percent)
    out = np.zeros((64, width_px, 3), dtype=np.uint8)
    u16 = prepared.view(np.uint16)
    for col in range(width_px):
        start = col * hop
        col_u16 = u16[start : start + 96]
        for plane in range(16):
            shift = 15 - plane
            bits = ((col_u16 >> shift) & 1).astype(np.uint8)
            packed12 = _pack_96bits_to_12bytes(bits)
            row_start = plane * 4
            out[row_start : row_start + 4, col, :] = packed12.reshape(4, 3)
    return out


def _encode_pcm16_delta_bitplanes(samples_i16: np.ndarray, width_px: int, overlap_percent: float) -> np.ndarray:
    prepared, _hop = _prepare_pcm16_for_spec(samples_i16, width_px, overlap_percent)
    u16 = prepared.view(np.uint16)
    delta = np.diff(u16.astype(np.int32), prepend=int(u16[0])).astype(np.int32)
    delta_u16 = np.mod(delta, 65536).astype(np.uint16)
    # Reuse bitplane encoder with the same overlap stepping.
    return _encode_pcm16_bitplanes(delta_u16.view(np.int16), width_px, overlap_percent=overlap_percent)


def _y_repeat_image(img: np.ndarray, repeat: int) -> np.ndarray:
    repeat = max(1, int(repeat))
    if repeat == 1:
        return img
    return np.repeat(img, repeat, axis=0)


def _compose_stack3(raw64: np.ndarray, bit64: np.ndarray, delta64: np.ndarray, y_repeat: int = 4) -> np.ndarray:
    return np.concatenate(
        [
            _y_repeat_image(raw64, y_repeat),
            _y_repeat_image(bit64, y_repeat),
            _y_repeat_image(delta64, y_repeat),
        ],
        axis=0,
    )


def _style_image_from_triplet(triplet: Dict[str, np.ndarray], style_mode: str, y_repeat: int = 4) -> np.ndarray:
    if style_mode == "raw_stream":
        return _y_repeat_image(triplet["raw_stream"], y_repeat)
    if style_mode == "bitplane_transpose":
        return _y_repeat_image(triplet["bitplane_transpose"], y_repeat)
    if style_mode == "delta_bitplane_transpose":
        return _y_repeat_image(triplet["delta_bitplane_transpose"], y_repeat)
    if style_mode == "stack3":
        return _compose_stack3(
            triplet["raw_stream"],
            triplet["bitplane_transpose"],
            triplet["delta_bitplane_transpose"],
            y_repeat=y_repeat,
        )
    raise ValueError(f"Unsupported payload style_mode: {style_mode}")


def _permute_bgr(img: np.ndarray, order: str) -> np.ndarray:
    idx = {"b": 0, "g": 1, "r": 2}
    return img[..., [idx[c] for c in order]]


def _apply_variant(base_image: np.ndarray, variant_id: str, stack_image: np.ndarray | None = None) -> np.ndarray:
    img = np.asarray(base_image, dtype=np.uint8)
    variant = str(variant_id or "none").lower()
    if variant in {"none", ""}:
        return img
    if variant == "perm_rgb":
        return _permute_bgr(img, "rgb")
    if variant == "perm_rbg":
        return _permute_bgr(img, "rbg")
    if variant == "perm_grb":
        return _permute_bgr(img, "grb")
    if variant == "perm_gbr":
        return _permute_bgr(img, "gbr")
    if variant == "perm_brg":
        return _permute_bgr(img, "brg")
    if variant == "perm_bgr":
        return img
    if variant == "invert_all":
        return 255 - img
    if variant == "invert_r":
        out = img.copy()
        out[..., 2] = 255 - out[..., 2]
        return out
    if variant == "invert_g":
        out = img.copy()
        out[..., 1] = 255 - out[..., 1]
        return out
    if variant == "invert_b":
        out = img.copy()
        out[..., 0] = 255 - out[..., 0]
        return out
    if variant == "xor80_all":
        return np.bitwise_xor(img, 0x80)
    if variant == "dark_gray_06":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        dark = np.clip(gray.astype(np.float32) * 0.6, 0, 255).astype(np.uint8)
        return cv2.cvtColor(dark, cv2.COLOR_GRAY2BGR)
    if variant == "dark_turbo_04":
        source = stack_image if stack_image is not None else img
        gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
        turbo = cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)
        return np.clip(turbo.astype(np.float32) * 0.4, 0, 255).astype(np.uint8)
    return img


def _draw_grid(img: np.ndarray, step_x: int = 100, step_y: int = 64) -> None:
    h, w = img.shape[:2]
    color = (80, 80, 80)
    for x in range(0, w, max(1, step_x)):
        cv2.line(img, (x, 0), (x, h - 1), color, 1, cv2.LINE_AA)
    for y in range(0, h, max(1, step_y)):
        cv2.line(img, (0, y), (w - 1, y), color, 1, cv2.LINE_AA)


def _draw_time_ticks(img: np.ndarray, frame_seconds: float) -> None:
    h, w = img.shape[:2]
    sec_count = max(1, int(round(frame_seconds)))
    tick_color = (200, 200, 200)
    for sec in range(sec_count + 1):
        x = int(round(sec / max(1, sec_count) * (w - 1)))
        cv2.line(img, (x, h - 1), (x, max(0, h - 18)), tick_color, 1, cv2.LINE_AA)


def _draw_stack_bounds(img: np.ndarray, y_repeat: int) -> None:
    if img.shape[0] < 3:
        return
    section = max(1, int(round(64 * max(1, y_repeat))))
    color = (140, 220, 140)
    for y in (section, section * 2):
        if 0 <= y < img.shape[0]:
            cv2.line(img, (0, y), (img.shape[1] - 1, y), color, 1, cv2.LINE_AA)


def _draw_legend(img: np.ndarray, style_mode: str, variant_mode: str) -> None:
    text = f"{style_mode} | {variant_mode}"
    cv2.rectangle(img, (8, 8), (8 + 12 * len(text), 30), (0, 0, 0), -1)
    cv2.putText(img, text, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)


def render_payload_image(
    samples: np.ndarray,
    source_sr: int,
    *,
    frame_seconds: float,
    overlap_percent: float,
    style_mode: str,
    y_repeat: int,
    variant_mode: str,
    overlay_grid: bool = True,
    overlay_time_ticks: bool = True,
    overlay_stack_bounds: bool = True,
    overlay_legend: bool = True,
) -> Tuple[np.ndarray, Dict[str, float | int | str]]:
    target_sr = 96000
    mono = _to_mono(samples)
    mono = _resample_linear(mono, int(source_sr), target_sr)
    samples_i16 = _float_to_i16(mono)
    frame_seconds = float(max(0.2, min(4.0, frame_seconds)))
    width_px = max(1, int(round(frame_seconds * 1000.0)))
    overlap_percent = float(np.clip(overlap_percent, 0.0, 95.0))

    triplet = {
        "raw_stream": _encode_pcm16_raw_stream(samples_i16, width_px, overlap_percent),
        "bitplane_transpose": _encode_pcm16_bitplanes(samples_i16, width_px, overlap_percent),
        "delta_bitplane_transpose": _encode_pcm16_delta_bitplanes(samples_i16, width_px, overlap_percent),
    }
    stack = _compose_stack3(
        triplet["raw_stream"],
        triplet["bitplane_transpose"],
        triplet["delta_bitplane_transpose"],
        y_repeat=int(y_repeat),
    )
    base = _style_image_from_triplet(triplet, style_mode=style_mode, y_repeat=int(y_repeat))
    final = _apply_variant(base, variant_id=variant_mode, stack_image=stack)

    if overlay_grid:
        _draw_grid(final)
    if overlay_time_ticks:
        _draw_time_ticks(final, frame_seconds)
    if overlay_stack_bounds and style_mode == "stack3":
        _draw_stack_bounds(final, int(y_repeat))
    if overlay_legend:
        _draw_legend(final, style_mode, variant_mode)

    meta: Dict[str, float | int | str] = {
        "frame_seconds": frame_seconds,
        "width_px": int(final.shape[1]),
        "height_px": int(final.shape[0]),
        "style_mode": style_mode,
        "variant_mode": variant_mode,
        "overlap_percent": overlap_percent,
        "target_sr": target_sr,
    }
    return final, meta
