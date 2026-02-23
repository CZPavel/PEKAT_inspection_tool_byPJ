import json
import logging
import time
from pathlib import Path

import numpy as np

from pektool.config import AppConfig
from pektool.core.runner import Runner
from pektool.core.sound_camera.models import SoundCameraFrame


class _DummyClient:
    def __init__(self) -> None:
        self.calls = 0
        self.images = []

    def analyze(self, image, *_args, **_kwargs):
        self.calls += 1
        self.images.append(image)
        return {"result": True, "completeTime": 0.01}, None


class _DummyConnection:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.total_sent = 0
        self.last_data = ""
        self.last_context = None
        self.client = _DummyClient()
        self.eval_records = []

    def is_connected(self) -> bool:
        return self.connected

    def update_last_data(self, data_value: str) -> None:
        self.last_data = data_value

    def update_last_context(self, context):
        self.last_context = context

    def record_sent(self, _path: str) -> None:
        self.total_sent += 1

    def record_evaluation(self, complete_time_ms, ok_nok, context, error):
        self.eval_records.append((complete_time_ms, ok_nok, context, error))


class _EngineSaveSend:
    def __init__(self, *, config, logger, stop_event, on_frame) -> None:
        self.config = config
        self.stop_event = stop_event
        self.on_frame = on_frame

    def run(self) -> None:
        snapshot_dir = Path(self.config.audio.snapshot_dir)
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        image = np.zeros((64, 64, 3), dtype=np.uint8)
        path = snapshot_dir / "sound_classic_fuse7_001.png"
        path.write_bytes(b"png-bytes")
        frame = SoundCameraFrame(
            image_bgr=image,
            timestamp=time.time(),
            label_stem="sound_classic_fuse7_001",
            source="microphone",
            approach="classic",
            saved_path=path,
            meta={"width_px": 64, "height_px": 64, "style": "fuse7"},
        )
        self.on_frame(frame)
        time.sleep(0.25)
        self.stop_event.set()


class _EngineSendOnly:
    def __init__(self, *, config, logger, stop_event, on_frame) -> None:
        self.config = config
        self.stop_event = stop_event
        self.on_frame = on_frame

    def run(self) -> None:
        image = np.zeros((48, 48, 3), dtype=np.uint8)
        frame = SoundCameraFrame(
            image_bgr=image,
            timestamp=time.time(),
            label_stem="sound_classic_fuse4_base_001",
            source="loopback",
            approach="classic",
            saved_path=None,
            meta={"width_px": 48, "height_px": 48, "style": "fuse4_base"},
        )
        self.on_frame(frame)
        time.sleep(0.25)
        self.stop_event.set()


def _build_runner(tmp_path: Path, connection: _DummyConnection) -> Runner:
    cfg = AppConfig()
    cfg.logging.directory = str(tmp_path / "logs")
    cfg.behavior.delay_between_images_ms = 0
    cfg.behavior.graceful_stop_timeout_sec = 2
    cfg.audio.enabled = True
    cfg.audio.window_sec = 0.2
    cfg.audio.interval_sec = 0.2
    cfg.audio.snapshot_dir = str(tmp_path / "snapshots")
    logger = logging.getLogger(f"runner-sound-test-{tmp_path.name}")
    logger.handlers = []
    logger.addHandler(logging.NullHandler())
    return Runner(cfg, connection, logger)


def _wait_for(condition, timeout_sec: float = 3.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_runner_save_send_enqueues_path_and_logs_source_kind(tmp_path, monkeypatch):
    monkeypatch.setattr("pektool.core.runner.SoundCameraEngine", _EngineSaveSend)
    connection = _DummyConnection(connected=True)
    runner = _build_runner(tmp_path, connection)
    runner.config.audio.send_mode = "save_send"

    runner.start()
    try:
        assert _wait_for(lambda: connection.total_sent > 0)
    finally:
        runner.stop()

    assert connection.client.calls > 0
    assert isinstance(connection.client.images[0], Path)
    jsonl_path = Path(runner.config.logging.directory) / runner.config.logging.jsonl_filename
    line = jsonl_path.read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(line)
    assert payload["source_kind"] == "sound_camera"
    assert payload["status"] == "ok"
    assert "classic_fuse7" in str(payload["filename"]).lower()


def test_runner_send_only_uses_numpy_and_disables_source_file_actions(tmp_path, monkeypatch):
    monkeypatch.setattr("pektool.core.runner.SoundCameraEngine", _EngineSendOnly)

    def _forbidden_file_action(*_args, **_kwargs):
        raise AssertionError("Source file action must not be called in send_only mode")

    monkeypatch.setattr("pektool.core.runner.apply_file_action", _forbidden_file_action)

    connection = _DummyConnection(connected=True)
    runner = _build_runner(tmp_path, connection)
    runner.config.audio.send_mode = "send_only"
    runner.config.file_actions.enabled = True
    runner.config.file_actions.save_json_context = True
    runner.config.file_actions.ok.base_dir = str(tmp_path / "ok")
    runner.config.file_actions.nok.base_dir = str(tmp_path / "nok")

    runner.start()
    try:
        assert _wait_for(lambda: connection.total_sent > 0)
    finally:
        runner.stop()

    assert connection.client.calls > 0
    assert isinstance(connection.client.images[0], np.ndarray)
    json_files = list((tmp_path / "ok").rglob("*.json"))
    assert json_files, "Artifact JSON should remain available in send_only mode"
    jsonl_path = Path(runner.config.logging.directory) / runner.config.logging.jsonl_filename
    line = jsonl_path.read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(line)
    assert payload["file_action_reason"] == "send-only-source-file-actions-disabled"
    assert "classic_fuse4_base" in str(payload["filename"]).lower()
