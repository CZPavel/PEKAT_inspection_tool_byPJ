import numpy as np
import pytest

from pektool.core.sound_camera.render_payload import render_payload_image


def _sine(sr: int, sec: float, hz: float = 440.0) -> np.ndarray:
    t = np.arange(int(sr * sec), dtype=np.float32) / float(sr)
    return np.sin(2.0 * np.pi * hz * t).astype(np.float32)


def test_render_payload_shape_dtype_and_determinism():
    samples = _sine(48000, 1.0)
    img1, meta1 = render_payload_image(
        samples=samples,
        source_sr=48000,
        frame_seconds=1.0,
        overlap_percent=50.0,
        style_mode="stack3",
        y_repeat=4,
        variant_mode="none",
    )
    img2, meta2 = render_payload_image(
        samples=samples,
        source_sr=48000,
        frame_seconds=1.0,
        overlap_percent=50.0,
        style_mode="stack3",
        y_repeat=4,
        variant_mode="none",
    )
    assert img1.shape == (768, 1000, 3)
    assert img1.dtype == np.uint8
    assert np.array_equal(img1, img2)
    assert meta1["style_mode"] == "stack3"
    assert meta2["overlap_percent"] == 50.0


def test_render_payload_invalid_style_raises():
    samples = _sine(16000, 0.5)
    with pytest.raises(ValueError):
        render_payload_image(
            samples=samples,
            source_sr=16000,
            frame_seconds=0.5,
            overlap_percent=0.0,
            style_mode="invalid_style",
            y_repeat=1,
            variant_mode="none",
        )


def test_render_payload_overlay_toggles_affect_output():
    samples = _sine(48000, 1.0)
    img_plain, _ = render_payload_image(
        samples=samples,
        source_sr=48000,
        frame_seconds=1.0,
        overlap_percent=50.0,
        style_mode="stack3",
        y_repeat=4,
        variant_mode="none",
        overlay_grid=False,
        overlay_time_ticks=False,
        overlay_stack_bounds=False,
        overlay_legend=False,
    )
    img_overlay, _ = render_payload_image(
        samples=samples,
        source_sr=48000,
        frame_seconds=1.0,
        overlap_percent=50.0,
        style_mode="stack3",
        y_repeat=4,
        variant_mode="none",
        overlay_grid=True,
        overlay_time_ticks=True,
        overlay_stack_bounds=True,
        overlay_legend=True,
    )
    assert img_plain.shape == img_overlay.shape
    assert not np.array_equal(img_plain, img_overlay)
