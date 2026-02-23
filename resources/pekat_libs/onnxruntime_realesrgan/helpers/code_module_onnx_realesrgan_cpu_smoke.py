from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, Tuple

import cv2
import numpy as np

# Keep cache between PEKAT frames.
if "__main__" not in globals():
    __main__ = {}

MODEL_INPUT_SIZE = 128
MODEL_SCALE = 4

DEFAULT_PYDEPS = Path(r"C:\ProgramData\PEKAT\pydeps")
FALLBACK_PYDEPS = Path(r"C:\Program Files\PEKAT VISION 3.19.3\server")
DEFAULT_MODEL = Path(r"C:\ProgramData\PEKAT\models\real_esrgan_general_x4v3.onnx")
FALLBACK_MODEL = Path(
    r"C:\Program Files\PEKAT VISION 3.19.3\server\models\real_esrgan_general_x4v3.onnx"
)
SESSION_CACHE_KEY = "__realesrgan_ort_sessions__"


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_str(value, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _log(message: str, log_enabled: bool) -> None:
    if log_enabled:
        print(f"[RealESRGAN] {message}", flush=True)


def _load_config(module_item) -> Dict[str, object]:
    source = module_item if isinstance(module_item, dict) else {}
    output_mode = _as_str(source.get("output_mode"), "x4").lower()
    if output_mode not in {"x4", "same_size"}:
        output_mode = "x4"

    log_level = _as_str(source.get("log_level"), "info").lower()
    if log_level not in {"silent", "info"}:
        log_level = "info"

    tile_size = _as_int(source.get("tile_size"), MODEL_INPUT_SIZE)
    tile_overlap = _as_int(source.get("tile_overlap"), 16)

    if tile_size != MODEL_INPUT_SIZE:
        tile_size = MODEL_INPUT_SIZE

    max_overlap = max(0, (tile_size // 2) - 1)
    tile_overlap = min(max(tile_overlap, 0), max_overlap)

    return {
        "enabled": _as_bool(source.get("enabled"), True),
        "output_mode": output_mode,
        "tile_size": tile_size,
        "tile_overlap": tile_overlap,
        "pydeps_path": source.get("pydeps_path"),
        "model_path": source.get("model_path"),
        "log_enabled": log_level == "info",
    }


def _resolve_existing_path(candidates) -> Path:
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return Path(candidates[0])


def _resolve_paths(config: Dict[str, object]) -> Tuple[Path, Path]:
    pydeps_candidates = []
    user_pydeps = config.get("pydeps_path")
    if user_pydeps:
        pydeps_candidates.append(Path(str(user_pydeps)))
    pydeps_candidates.extend([DEFAULT_PYDEPS, FALLBACK_PYDEPS])

    model_candidates = []
    user_model = config.get("model_path")
    if user_model:
        model_candidates.append(Path(str(user_model)))
    model_candidates.extend([DEFAULT_MODEL, FALLBACK_MODEL])

    return _resolve_existing_path(pydeps_candidates), _resolve_existing_path(model_candidates)


def _model_data_path(model_path: Path) -> Path:
    return model_path.with_suffix(".data")


def _normalize_image(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.ndim == 3 and image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    elif image.ndim != 3:
        raise ValueError("Unsupported input shape for context['image']")

    if image.dtype == np.uint8:
        return image

    if np.issubdtype(image.dtype, np.floating):
        img = np.nan_to_num(image, nan=0.0, posinf=255.0, neginf=0.0)
        if img.max(initial=0.0) <= 1.0:
            img = img * 255.0
        return np.clip(img, 0.0, 255.0).astype(np.uint8)

    return np.clip(image, 0, 255).astype(np.uint8)


def _load_onnxruntime():
    import onnxruntime as ort

    return ort


def _get_session(
    pydeps_path: Path,
    model_path: Path,
    log: Callable[[str], None],
):
    resolved_pydeps = str(pydeps_path)
    if resolved_pydeps not in sys.path:
        sys.path.insert(0, resolved_pydeps)

    cache = __main__.setdefault(SESSION_CACHE_KEY, {})
    cache_key = (str(pydeps_path), str(model_path))
    if cache_key in cache:
        return cache[cache_key]

    ort = _load_onnxruntime()
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    cache[cache_key] = (session, input_name, output_name)
    log(f"onnxruntime {ort.__version__} loaded; input={input_name}, output={output_name}")
    return cache[cache_key]


def _compute_tail_padding(length: int, tile_size: int, stride: int) -> int:
    if length < tile_size:
        return tile_size - length
    tail = (length - tile_size) % stride
    if tail == 0:
        return 0
    return stride - tail


def _pad_for_tiling(image: np.ndarray, tile_size: int, stride: int) -> Tuple[np.ndarray, int, int]:
    h, w = image.shape[:2]
    pad_bottom = _compute_tail_padding(h, tile_size, stride)
    pad_right = _compute_tail_padding(w, tile_size, stride)
    if pad_bottom == 0 and pad_right == 0:
        return image, 0, 0

    border_mode = cv2.BORDER_REFLECT_101 if h > 1 and w > 1 else cv2.BORDER_REPLICATE
    padded = cv2.copyMakeBorder(
        image,
        0,
        pad_bottom,
        0,
        pad_right,
        borderType=border_mode,
    )
    return padded, pad_bottom, pad_right


def _tile_positions(length: int, tile_size: int, stride: int):
    return range(0, length - tile_size + 1, stride)


def _preprocess_tile(tile_bgr: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(tile_bgr, cv2.COLOR_BGR2RGB)
    x = rgb.astype(np.float32) / 255.0
    return np.transpose(x, (2, 0, 1))[None, :, :, :]


def _postprocess_tile(tile_output: np.ndarray) -> np.ndarray:
    rgb = np.transpose(tile_output[0], (1, 2, 0))
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def _blend_weight_mask(tile_size: int, overlap: int) -> np.ndarray:
    out_size = tile_size * MODEL_SCALE
    overlap_out = overlap * MODEL_SCALE
    one_d = np.ones(out_size, dtype=np.float32)
    if overlap_out > 0:
        ramp = np.linspace(0.1, 1.0, overlap_out, dtype=np.float32)
        one_d[:overlap_out] = ramp
        one_d[-overlap_out:] = ramp[::-1]
    return np.outer(one_d, one_d)


def _upscale_tiled(
    image_bgr: np.ndarray,
    session,
    input_name: str,
    output_name: str,
    tile_size: int,
    overlap: int,
) -> np.ndarray:
    stride = max(1, tile_size - (2 * overlap))
    padded, pad_bottom, pad_right = _pad_for_tiling(image_bgr, tile_size, stride)
    padded_h, padded_w = padded.shape[:2]

    out_h = padded_h * MODEL_SCALE
    out_w = padded_w * MODEL_SCALE
    accum = np.zeros((out_h, out_w, 3), dtype=np.float32)
    weight_sum = np.zeros((out_h, out_w), dtype=np.float32)
    weights = _blend_weight_mask(tile_size, overlap)

    for y in _tile_positions(padded_h, tile_size, stride):
        for x in _tile_positions(padded_w, tile_size, stride):
            tile = padded[y : y + tile_size, x : x + tile_size]
            tile_input = _preprocess_tile(tile)
            tile_output = session.run([output_name], {input_name: tile_input})[0]
            tile_rgb = _postprocess_tile(tile_output)

            oy = y * MODEL_SCALE
            ox = x * MODEL_SCALE
            th = tile_rgb.shape[0]
            tw = tile_rgb.shape[1]

            accum[oy : oy + th, ox : ox + tw] += tile_rgb * weights[:, :, None]
            weight_sum[oy : oy + th, ox : ox + tw] += weights

    merged = accum / np.clip(weight_sum[:, :, None], 1e-6, None)
    orig_h, orig_w = image_bgr.shape[:2]
    crop_h = orig_h * MODEL_SCALE
    crop_w = orig_w * MODEL_SCALE
    merged = merged[:crop_h, :crop_w]
    out_u8 = np.clip(merged * 255.0, 0.0, 255.0).astype(np.uint8)
    return cv2.cvtColor(out_u8, cv2.COLOR_RGB2BGR)


def main(context, module_item=None):
    if not isinstance(context, dict):
        return

    config = _load_config(module_item)
    log_enabled = bool(config["log_enabled"])
    log = lambda message: _log(message, log_enabled)

    if not config["enabled"]:
        return

    image = context.get("image")
    if image is None or not isinstance(image, np.ndarray):
        return

    try:
        normalized = _normalize_image(image)
    except Exception as exc:
        log(f"Input normalization failed: {exc}")
        return

    pydeps_path, model_path = _resolve_paths(config)
    model_data_path = _model_data_path(model_path)
    if not model_path.exists() or not model_data_path.exists():
        log(f"Model files missing: {model_path} and/or {model_data_path}")
        return

    try:
        session, input_name, output_name = _get_session(pydeps_path, model_path, log)
        upscaled = _upscale_tiled(
            normalized,
            session,
            input_name,
            output_name,
            tile_size=int(config["tile_size"]),
            overlap=int(config["tile_overlap"]),
        )
        if config["output_mode"] == "same_size":
            h, w = normalized.shape[:2]
            upscaled = cv2.resize(upscaled, (w, h), interpolation=cv2.INTER_CUBIC)
        context["image"] = upscaled
    except Exception as exc:
        log(f"Inference failed: {exc}")
        return
