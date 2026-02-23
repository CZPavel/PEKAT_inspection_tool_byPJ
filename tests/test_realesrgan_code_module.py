from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "pekat_libs"
    / "onnxruntime_realesrgan"
    / "helpers"
    / "code_module_onnx_realesrgan_cpu_smoke.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("realesrgan_code_module", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSession:
    def get_inputs(self):
        return [SimpleNamespace(name="image")]

    def get_outputs(self):
        return [SimpleNamespace(name="upscaled_image")]

    def run(self, output_names, feed_dict):
        x = feed_dict["image"]
        up = np.repeat(np.repeat(x, 4, axis=2), 4, axis=3)
        return [up]


def test_x4_output_shape_for_even_dimensions(tmp_path):
    module = _load_module()
    model = tmp_path / "real_esrgan_general_x4v3.onnx"
    data = tmp_path / "real_esrgan_general_x4v3.data"
    model.write_text("x", encoding="utf-8")
    data.write_text("x", encoding="utf-8")

    module._get_session = lambda *_args, **_kwargs: (_FakeSession(), "image", "upscaled_image")
    context = {"image": np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)}
    module.main(
        context,
        {
            "model_path": str(model),
            "pydeps_path": str(tmp_path),
            "tile_size": 128,
            "tile_overlap": 16,
            "output_mode": "x4",
            "log_level": "silent",
        },
    )

    assert context["image"].shape == (1920, 2560, 3)


def test_same_size_mode_for_odd_dimensions(tmp_path):
    module = _load_module()
    model = tmp_path / "real_esrgan_general_x4v3.onnx"
    data = tmp_path / "real_esrgan_general_x4v3.data"
    model.write_text("x", encoding="utf-8")
    data.write_text("x", encoding="utf-8")

    module._get_session = lambda *_args, **_kwargs: (_FakeSession(), "image", "upscaled_image")
    context = {"image": np.random.randint(0, 255, (479, 641, 3), dtype=np.uint8)}
    module.main(
        context,
        {
            "model_path": str(model),
            "pydeps_path": str(tmp_path),
            "output_mode": "same_size",
            "log_level": "silent",
        },
    )

    assert context["image"].shape == (479, 641, 3)


def test_grayscale_input_is_supported(tmp_path):
    module = _load_module()
    model = tmp_path / "real_esrgan_general_x4v3.onnx"
    data = tmp_path / "real_esrgan_general_x4v3.data"
    model.write_text("x", encoding="utf-8")
    data.write_text("x", encoding="utf-8")

    module._get_session = lambda *_args, **_kwargs: (_FakeSession(), "image", "upscaled_image")
    context = {"image": np.random.randint(0, 255, (120, 160), dtype=np.uint8)}
    module.main(
        context,
        {
            "model_path": str(model),
            "pydeps_path": str(tmp_path),
            "output_mode": "x4",
            "log_level": "silent",
        },
    )

    assert context["image"].shape == (480, 640, 3)


def test_session_cache_reuses_session_instance(tmp_path):
    module = _load_module()
    model = tmp_path / "real_esrgan_general_x4v3.onnx"
    data = tmp_path / "real_esrgan_general_x4v3.data"
    model.write_text("x", encoding="utf-8")
    data.write_text("x", encoding="utf-8")

    class _FakeOrt:
        calls = 0
        __version__ = "fake"

        class InferenceSession(_FakeSession):
            def __init__(self, *_args, **_kwargs):
                _FakeOrt.calls += 1

    module._load_onnxruntime = lambda: _FakeOrt
    module.__main__.pop(module.SESSION_CACHE_KEY, None)

    first = module._get_session(tmp_path, model, lambda _msg: None)
    second = module._get_session(tmp_path, model, lambda _msg: None)
    assert first[0] is second[0]
    assert _FakeOrt.calls == 1
