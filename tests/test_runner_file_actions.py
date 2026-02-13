import json
import logging
from pathlib import Path

from pektool.config import AppConfig
from pektool.core.runner import Runner
from pektool.types import ImageTask


class _DummyConnection:
    def __init__(self) -> None:
        self.total_sent = 0
        self.last_data = ""
        self.last_context = None
        self.eval_records = []
        self.client = None

    def is_connected(self) -> bool:
        return True

    def update_last_data(self, data_value: str) -> None:
        self.last_data = data_value

    def update_last_context(self, context):
        self.last_context = context

    def record_sent(self, _path: str) -> None:
        self.total_sent += 1

    def record_evaluation(self, complete_time_ms, ok_nok, context, error):
        self.eval_records.append((complete_time_ms, ok_nok, context, error))


def _build_runner(tmp_path: Path, cfg: AppConfig | None = None) -> Runner:
    config = cfg or AppConfig()
    config.logging.directory = str(tmp_path / "logs")
    logger = logging.getLogger(f"runner-test-{tmp_path.name}")
    logger.handlers = []
    logger.addHandler(logging.NullHandler())
    connection = _DummyConnection()
    return Runner(config, connection, logger)


def test_runner_logs_file_action_fields_in_jsonl(tmp_path):
    cfg = AppConfig()
    cfg.file_actions.enabled = True
    cfg.file_actions.mode = "delete_after_eval"
    runner = _build_runner(tmp_path, cfg)
    source = tmp_path / "img.png"
    source.write_bytes(b"x")
    task = ImageTask(path=source, data_value="data")

    runner._analyze_with_retry = lambda _task: ({"result": True, "completeTime": 0.02}, None)  # type: ignore[method-assign]
    result = runner._process_task(task)
    assert result is not None
    runner._log_result(task, result)

    jsonl = Path(cfg.logging.directory) / cfg.logging.jsonl_filename
    payload = json.loads(jsonl.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert "file_action_applied" in payload
    assert "file_action_operation" in payload
    assert "file_action_target" in payload
    assert "file_action_reason" in payload


def test_runner_continue_on_file_action_failure(tmp_path, monkeypatch):
    cfg = AppConfig()
    cfg.file_actions.enabled = True
    cfg.file_actions.mode = "delete_after_eval"
    runner = _build_runner(tmp_path, cfg)
    source = tmp_path / "img.png"
    source.write_bytes(b"x")
    task = ImageTask(path=source, data_value="data")

    runner._analyze_with_retry = lambda _task: ({"result": True, "completeTime": 0.02}, None)  # type: ignore[method-assign]
    monkeypatch.setattr("pektool.core.runner.apply_file_action", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    result = runner._process_task(task)
    assert result is not None
    assert result.status == "ok"
    assert result.file_action is not None
    assert result.file_action.applied is False
    assert result.file_action.reason is not None
    assert "runner-file-action-exception" in result.file_action.reason


def test_runner_files_source_mode_applies_file_actions(tmp_path):
    cfg = AppConfig()
    cfg.input.source_type = "files"
    cfg.file_actions.enabled = True
    cfg.file_actions.mode = "move_by_result"
    cfg.file_actions.ok.base_dir = str(tmp_path / "ok")
    cfg.file_actions.nok.base_dir = str(tmp_path / "nok")
    runner = _build_runner(tmp_path, cfg)
    source = tmp_path / "img.png"
    source.write_bytes(b"x")
    task = ImageTask(path=source, data_value="data")

    runner._analyze_with_retry = lambda _task: ({"result": True, "completeTime": 0.02}, None)  # type: ignore[method-assign]
    result = runner._process_task(task)

    assert result is not None
    assert result.status == "ok"
    assert result.file_action is not None
    assert result.file_action.applied is True
    assert result.file_action.operation == "move"
    assert Path(result.file_action.target_path).exists()  # type: ignore[arg-type]


def test_runner_forces_annotated_response_when_processed_enabled(tmp_path):
    cfg = AppConfig()
    cfg.file_actions.save_processed_image = True
    cfg.pekat.response_type = "context"
    runner = _build_runner(tmp_path, cfg)
    task = ImageTask(path=tmp_path / "img.png", data_value="data")
    task.path.write_bytes(b"x")

    class _Client:
        def __init__(self):
            self.response_type = None

        def analyze(self, *_args, **kwargs):
            self.response_type = kwargs.get("response_type")
            return {"result": True, "completeTime": 0.02}, b"img"

    client = _Client()
    runner.connection.client = client
    context, image = runner._analyze_with_retry(task)

    assert context is not None
    assert image == b"img"
    assert client.response_type == "annotated_image"


def test_runner_logs_processed_image_path_with_anotated_prefix(tmp_path):
    cfg = AppConfig()
    cfg.file_actions.save_processed_image = True
    cfg.file_actions.ok.base_dir = str(tmp_path / "ok")
    cfg.file_actions.nok.base_dir = str(tmp_path / "nok")
    runner = _build_runner(tmp_path, cfg)
    source = tmp_path / "img.png"
    source.write_bytes(b"x")
    task = ImageTask(path=source, data_value="data")

    runner._analyze_with_retry = lambda _task: ({"result": True, "completeTime": 0.02}, b"img")  # type: ignore[method-assign]
    result = runner._process_task(task)
    assert result is not None
    runner._log_result(task, result)

    assert result.artifact_save is not None
    assert result.artifact_save.processed_saved is True
    assert Path(result.artifact_save.processed_path).name.startswith("ANOTATED_")  # type: ignore[arg-type]

    jsonl = Path(cfg.logging.directory) / cfg.logging.jsonl_filename
    payload = json.loads(jsonl.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["processed_image_saved"] is True
    assert "ANOTATED_" in (payload["processed_image_path"] or "")
