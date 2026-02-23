from pathlib import Path

import pytest

from pektool.config import AppConfig, load_config


def test_load_config_example():
    path = Path(__file__).resolve().parents[1] / "configs" / "config.example.yaml"
    cfg = load_config(path)
    assert cfg.host
    assert cfg.port
    assert cfg.audio.interval_sec == 2.0
    assert cfg.audio.window_sec == 1.0
    assert cfg.audio.approach == "payload"
    assert cfg.audio.send_mode == "save_send"


def test_audio_defaults_when_section_missing():
    cfg = AppConfig.parse_obj(
        {
            "host": "127.0.0.1",
            "port": 8000,
        }
    )
    assert cfg.audio.enabled is False
    assert cfg.audio.backend == "sounddevice"
    assert cfg.audio.source_mode == "audio_only"
    assert cfg.audio.snapshot_dir == "sound_camera_snapshots"
    assert cfg.audio.approach == "payload"
    assert cfg.audio.source == "loopback"
    assert cfg.audio.send_mode == "save_send"


def test_audio_config_validates_interval_vs_window():
    with pytest.raises(ValueError):
        AppConfig.parse_obj(
            {
                "audio": {
                    "enabled": True,
                    "approach": "payload",
                    "window_sec": 2.0,
                    "interval_sec": 1.0,
                }
            }
        )


def test_audio_classic_allows_overlap_interval_less_than_window():
    cfg = AppConfig.parse_obj(
        {
            "audio": {
                "enabled": True,
                "approach": "classic",
                "window_sec": 2.0,
                "interval_sec": 1.0,
            }
        }
    )
    assert cfg.audio.interval_sec == pytest.approx(1.0, abs=1e-6)
    assert cfg.audio.window_sec == pytest.approx(2.0, abs=1e-6)


def test_audio_lissajous_still_rejects_interval_less_than_window():
    with pytest.raises(ValueError):
        AppConfig.parse_obj(
            {
                "audio": {
                    "enabled": True,
                    "approach": "lissajous",
                    "window_sec": 2.0,
                    "interval_sec": 1.0,
                }
            }
        )


def test_audio_legacy_gui_migration_keys_are_applied():
    cfg = AppConfig.parse_obj(
        {
            "audio": {
                "source_mode": "audio_only",
                "audio_snapshot_dir": "C:/legacy_snapshots",
                "audio_device_name": "Legacy Mic",
            }
        }
    )
    assert cfg.audio.source == "microphone"
    assert cfg.audio.snapshot_dir == "C:/legacy_snapshots"
    assert cfg.audio.device_name == "Legacy Mic"


def test_audio_lissajous_tau_both_is_supported():
    cfg = AppConfig.parse_obj(
        {
            "audio": {
                "lissajous": {
                    "tau": "both",
                }
            }
        }
    )
    assert cfg.audio.lissajous.tau == "both"


def test_audio_fps_alias_maps_to_interval():
    cfg = AppConfig.parse_obj(
        {
            "audio": {
                "fps": 0.5,
            }
        }
    )
    assert cfg.audio.interval_sec == pytest.approx(2.0, abs=1e-6)


def test_audio_classic_new_style_and_axis_modes_are_supported():
    cfg = AppConfig.parse_obj(
        {
            "audio": {
                "approach": "classic",
                "classic": {
                    "style": "fuse7",
                    "axis_mode": "mel",
                    "scale_mode": "percentile",
                    "p_lo": 2.0,
                    "p_hi": 98.0,
                },
            }
        }
    )
    assert cfg.audio.classic.style == "fuse7"
    assert cfg.audio.classic.axis_mode == "mel"
    assert cfg.audio.classic.scale_mode == "percentile"
    assert cfg.audio.classic.p_lo == pytest.approx(2.0, abs=1e-6)
    assert cfg.audio.classic.p_hi == pytest.approx(98.0, abs=1e-6)


def test_audio_classic_rejects_invalid_style_and_axis():
    with pytest.raises(ValueError):
        AppConfig.parse_obj({"audio": {"classic": {"style": "fuse9"}}})
    with pytest.raises(ValueError):
        AppConfig.parse_obj({"audio": {"classic": {"axis_mode": "octave"}}})
