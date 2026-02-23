import numpy as np
import pytest

from pektool.core.sound_camera.render_lissajous import render_lissajous_image


def _signal() -> np.ndarray:
    t = np.linspace(0.0, 1.0, 8000, endpoint=False, dtype=np.float32)
    return (
        0.7 * np.sin(2.0 * np.pi * 220.0 * t)
        + 0.2 * np.sin(2.0 * np.pi * 330.0 * t)
        + 0.1 * np.sin(2.0 * np.pi * 510.0 * t)
    ).astype(np.float32)


def test_render_lissajous_tau_both_is_2w():
    samples = _signal()
    img, meta = render_lissajous_image(
        samples_mono=samples,
        tau="both",
        width=320,
        height=200,
        accum="avg",
        point_size_step=2,
        point_render_style="classic",
        value_mode="radial",
        rotation="none",
    )
    assert img.shape == (200, 640, 3)
    assert img.dtype == np.uint8
    assert meta["tau"] == "both"


def test_render_lissajous_modes_have_effect():
    samples = _signal()
    base, _ = render_lissajous_image(
        samples_mono=samples,
        tau=5,
        width=320,
        height=240,
        accum="none",
        point_size_step=2,
        point_render_style="classic",
        value_mode="radial",
        rotation="none",
    )
    rotated, _ = render_lissajous_image(
        samples_mono=samples,
        tau=5,
        width=320,
        height=240,
        accum="none",
        point_size_step=2,
        point_render_style="classic",
        value_mode="radial",
        rotation="plus45",
    )
    flat_mode, _ = render_lissajous_image(
        samples_mono=samples,
        tau=5,
        width=320,
        height=240,
        accum="none",
        point_size_step=2,
        point_render_style="classic",
        value_mode="flat",
        rotation="none",
    )
    sharp_style, _ = render_lissajous_image(
        samples_mono=samples,
        tau=5,
        width=320,
        height=240,
        accum="none",
        point_size_step=2,
        point_render_style="sharp_stamp",
        value_mode="radial",
        rotation="none",
    )
    avg_accum, _ = render_lissajous_image(
        samples_mono=samples,
        tau=5,
        width=320,
        height=240,
        accum="avg",
        point_size_step=2,
        point_render_style="classic",
        value_mode="radial",
        rotation="none",
    )
    assert not np.array_equal(base, rotated)
    assert not np.array_equal(base, flat_mode)
    assert not np.array_equal(base, sharp_style)
    assert not np.array_equal(base, avg_accum)


def test_render_lissajous_point_size_step_increases_coverage():
    samples = _signal()
    img_small, _ = render_lissajous_image(
        samples_mono=samples,
        tau=5,
        width=200,
        height=200,
        accum="none",
        point_size_step=1,
        point_render_style="classic",
        value_mode="radial",
        rotation="none",
    )
    img_big, _ = render_lissajous_image(
        samples_mono=samples,
        tau=5,
        width=200,
        height=200,
        accum="none",
        point_size_step=7,
        point_render_style="classic",
        value_mode="radial",
        rotation="none",
    )
    assert int(np.count_nonzero(img_big)) > int(np.count_nonzero(img_small))


def test_render_lissajous_color_redundancy_uses_all_channels():
    samples = _signal()
    img, _ = render_lissajous_image(
        samples_mono=samples,
        tau=5,
        width=300,
        height=300,
        accum="max",
        point_size_step=4,
        point_render_style="square_stamp",
        value_mode="flat",
        rotation="none",
    )
    channel_nnz = [int(np.count_nonzero(img[..., c])) for c in range(3)]
    assert all(v > 0 for v in channel_nnz)
    assert not np.array_equal(img[..., 0], img[..., 1])
    assert not np.array_equal(img[..., 1], img[..., 2])


def test_render_lissajous_validates_params():
    samples = _signal()
    with pytest.raises(ValueError):
        render_lissajous_image(
            samples_mono=samples,
            tau=5,
            width=128,
            height=128,
            point_size_step=9,
        )
