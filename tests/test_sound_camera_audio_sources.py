from types import SimpleNamespace

import pytest

from pektool.core.sound_camera import audio_sources


class _FakeSoundDevice:
    def __init__(self) -> None:
        self._devices = [
            {"name": "Mic One", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Speaker Primary", "max_input_channels": 0, "max_output_channels": 2},
            {"name": "Stereo Mix", "max_input_channels": 2, "max_output_channels": 0},
        ]
        self._hostapis = [{"name": "Windows WASAPI", "default_output_device": 1}]
        self.default = SimpleNamespace(device=(0, 1))

    def query_devices(self, index=None):
        if index is None:
            return self._devices
        return self._devices[int(index)]

    def query_hostapis(self):
        return self._hostapis


def test_list_microphone_devices(monkeypatch):
    fake_sd = _FakeSoundDevice()
    monkeypatch.setattr(audio_sources, "_require_sounddevice", lambda: fake_sd)
    rows = audio_sources.list_microphone_devices()
    assert rows[0]["id"] == "default"
    assert any("Mic One" in row["label"] for row in rows)


def test_resolve_primary_loopback_falls_back_to_sounddevice(monkeypatch):
    fake_sd = _FakeSoundDevice()
    monkeypatch.setattr(audio_sources, "_require_sounddevice", lambda: fake_sd)

    def _no_pyaudio():
        raise RuntimeError("missing pyaudio")

    monkeypatch.setattr(audio_sources, "_require_pyaudiowpatch", _no_pyaudio)
    resolved = audio_sources._resolve_primary_loopback_id(fake_sd)
    assert resolved == "1"


def test_list_loopback_devices_fallback_contains_primary(monkeypatch):
    fake_sd = _FakeSoundDevice()
    monkeypatch.setattr(audio_sources, "_require_sounddevice", lambda: fake_sd)

    def _no_pyaudio():
        raise RuntimeError("missing pyaudio")

    monkeypatch.setattr(audio_sources, "_require_pyaudiowpatch", _no_pyaudio)
    rows = audio_sources.list_loopback_devices()
    assert rows[0]["id"] == "default"
    assert any("[PRIMARY]" in row["label"] for row in rows[1:])


def test_resolve_device_index_default_output(monkeypatch):
    fake_sd = _FakeSoundDevice()
    monkeypatch.setattr(audio_sources, "_require_sounddevice", lambda: fake_sd)
    idx = audio_sources._resolve_device_index(
        fake_sd,
        "default",
        require_input=False,
        require_output=True,
    )
    assert idx == 1


def test_resolve_device_index_missing_raises():
    fake_sd = _FakeSoundDevice()
    with pytest.raises(RuntimeError):
        audio_sources._resolve_device_index(
            fake_sd,
            "missing-name",
            require_input=True,
            require_output=False,
        )
