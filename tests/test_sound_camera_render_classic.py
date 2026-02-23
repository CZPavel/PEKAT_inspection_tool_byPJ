import numpy as np
import pytest

from pektool.core.sound_camera import render_classic as classic_mod
from pektool.core.sound_camera.render_classic import classic_dependencies_status, render_classic_image


SCIPY_AVAILABLE = bool(classic_dependencies_status().get("scipy_available", False))


def _tone(sr: int = 48000, sec: float = 0.8) -> np.ndarray:
    t = np.arange(int(sr * sec), dtype=np.float32) / float(sr)
    return np.sin(2.0 * np.pi * 1000.0 * t).astype(np.float32)


def test_classic_dependencies_status_contract():
    status = classic_dependencies_status()
    assert "scipy_available" in status
    assert "error" in status
    assert isinstance(status["scipy_available"], bool)


def test_render_classic_missing_scipy_guard(monkeypatch):
    monkeypatch.setattr(classic_mod, "sps", None)
    status = classic_mod.classic_dependencies_status()
    assert status["scipy_available"] is False
    with pytest.raises(RuntimeError, match="scipy>=1.10"):
        classic_mod.render_classic_image(
            samples=np.zeros((1024,), dtype=np.float32),
            source_sr=16000,
            width=128,
            height=64,
            preset="none",
        )


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="requires scipy")
def test_render_classic_output_and_silence_stability():
    silent = np.zeros((2048,), dtype=np.float32)
    img, meta = render_classic_image(
        samples=silent,
        source_sr=16000,
        width=320,
        height=180,
        preset="none",
    )
    assert img.shape == (180, 320, 3)
    assert img.dtype == np.uint8
    assert meta["width_px"] == 320


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="requires scipy")
def test_render_classic_colormap_and_gamma_affect_output():
    samples = _tone()
    img_gray, _ = render_classic_image(
        samples=samples,
        source_sr=48000,
        width=300,
        height=220,
        preset="none",
        colormap="gray",
        gamma=1.0,
        detail_mode="off",
    )
    img_turbo, _ = render_classic_image(
        samples=samples,
        source_sr=48000,
        width=300,
        height=220,
        preset="none",
        colormap="turbo",
        gamma=2.0,
        detail_mode="highpass",
    )
    assert not np.array_equal(img_gray, img_turbo)


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="requires scipy")
def test_render_classic_preset_does_not_lock_runtime_controls():
    samples = _tone()
    img_gray, meta_gray = render_classic_image(
        samples=samples,
        source_sr=48000,
        width=300,
        height=220,
        preset="classic_fhd",
        colormap="gray",
        detail_mode="off",
        gamma=1.0,
    )
    img_turbo, meta_turbo = render_classic_image(
        samples=samples,
        source_sr=48000,
        width=300,
        height=220,
        preset="classic_fhd",
        colormap="turbo",
        detail_mode="edgesobel",
        gamma=2.2,
    )
    assert meta_gray["preset"] == "classic_fhd"
    assert meta_turbo["preset"] == "classic_fhd"
    assert meta_gray["colormap"] == "gray"
    assert meta_turbo["colormap"] == "turbo"
    assert not np.array_equal(img_gray, img_turbo)


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="requires scipy")
def test_render_classic_stft_controls_affect_output():
    samples = _tone(sr=96000, sec=1.0)
    base, _ = render_classic_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        n_fft=4096,
        win_ms=25.0,
        hop_ms=1.0,
        top_db=80.0,
        fmax=24000.0,
    )
    tuned, meta = render_classic_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        n_fft=8192,
        win_ms=40.0,
        hop_ms=0.5,
        top_db=65.0,
        fmax=12000.0,
    )
    assert meta["n_fft"] == 8192
    assert meta["win_ms"] == pytest.approx(40.0, abs=1e-6)
    assert meta["hop_ms"] == pytest.approx(0.5, abs=1e-6)
    assert meta["top_db"] == pytest.approx(65.0, abs=1e-6)
    assert meta["fmax"] == pytest.approx(12000.0, abs=1e-6)
    assert not np.array_equal(base, tuned)


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="requires scipy")
def test_render_classic_validates_hop_vs_window():
    with pytest.raises(ValueError, match="hop_ms must be <= win_ms"):
        render_classic_image(
            samples=_tone(),
            source_sr=48000,
            width=320,
            height=200,
            win_ms=10.0,
            hop_ms=20.0,
        )


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="requires scipy")
def test_render_classic_axis_modes_change_output():
    samples = _tone(sr=96000, sec=1.0)
    linear, meta_linear = render_classic_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        axis_mode="linear",
    )
    log_img, meta_log = render_classic_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        axis_mode="log",
    )
    mel_img, meta_mel = render_classic_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        axis_mode="mel",
    )
    assert meta_linear["axis_mode"] == "linear"
    assert meta_log["axis_mode"] == "log"
    assert meta_mel["axis_mode"] == "mel"
    assert not np.array_equal(linear, log_img)
    assert not np.array_equal(linear, mel_img)


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="requires scipy")
def test_render_classic_percentile_scale_mode_changes_output():
    samples = _tone(sr=96000, sec=1.0)
    top_img, meta_top = render_classic_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        scale_mode="top_db",
        top_db=80.0,
    )
    pct_img, meta_pct = render_classic_image(
        samples=samples,
        source_sr=96000,
        width=640,
        height=360,
        scale_mode="percentile",
        p_lo=2.0,
        p_hi=98.0,
    )
    assert meta_top["scale_mode"] == "top_db"
    assert meta_pct["scale_mode"] == "percentile"
    assert not np.array_equal(top_img, pct_img)
