import numpy as np
import pytest

from pektool.core.sound_camera.render_classic import classic_dependencies_status
from pektool.core.sound_camera.render_fuse7 import render_fuse7_image


SCIPY_AVAILABLE = bool(classic_dependencies_status().get("scipy_available", False))


def _tone(sr: int = 96000, sec: float = 1.0) -> np.ndarray:
    t = np.arange(int(sr * sec), dtype=np.float32) / float(sr)
    return (
        0.8 * np.sin(2.0 * np.pi * 1000.0 * t)
        + 0.3 * np.sin(2.0 * np.pi * 3500.0 * t)
    ).astype(np.float32)


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="requires scipy")
def test_render_fuse7_and_fuse4_base_shapes():
    samples = _tone()
    fuse7_img, fuse7_meta = render_fuse7_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        style="fuse7",
    )
    base_img, base_meta = render_fuse7_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        style="fuse4_base",
    )
    assert fuse7_img.shape == (360, 640, 3)
    assert base_img.shape == (360, 640, 3)
    assert fuse7_img.dtype == np.uint8
    assert base_img.dtype == np.uint8
    assert fuse7_meta["style"] == "fuse7"
    assert base_meta["style"] == "fuse4_base"


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="requires scipy")
def test_render_fuse7_profile_and_gains_have_effect():
    samples = _tone()
    ref_img, ref_meta = render_fuse7_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        style="fuse7",
        fuse7_profile="ref_compat",
        flux_gain=110.0,
        edge_gain=70.0,
        norm_p=99.5,
    )
    tuned_img, tuned_meta = render_fuse7_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        style="fuse7",
        fuse7_profile="default",
        flux_gain=250.0,
        edge_gain=200.0,
        norm_p=95.0,
    )
    assert ref_meta["fuse7_profile"] == "ref_compat"
    assert tuned_meta["fuse7_profile"] == "default"
    assert not np.array_equal(ref_img, tuned_img)
