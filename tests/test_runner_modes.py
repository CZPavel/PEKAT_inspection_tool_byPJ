import logging

from pektool.config import AppConfig
from pektool.core.runner import Runner


class _DummyConnection:
    total_sent = 0

    def is_connected(self) -> bool:
        return False


class _DummyLogger:
    def warning(self, *_args, **_kwargs):
        return None


def test_collect_existing_paths_respects_subfolders(tmp_path):
    root_png = tmp_path / "root.png"
    root_png.write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    sub_png = sub / "nested.png"
    sub_png.write_bytes(b"x")

    cfg = AppConfig()
    cfg.input.folder = str(tmp_path)
    cfg.input.include_subfolders = False
    runner = Runner(cfg, _DummyConnection(), logging.getLogger("test"))
    paths_no_sub = runner._collect_existing_paths(tmp_path)
    assert root_png in paths_no_sub
    assert sub_png not in paths_no_sub

    cfg.input.include_subfolders = True
    runner_with_sub = Runner(cfg, _DummyConnection(), logging.getLogger("test"))
    paths_with_sub = runner_with_sub._collect_existing_paths(tmp_path)
    assert root_png in paths_with_sub
    assert sub_png in paths_with_sub


def test_loop_mode_forces_file_actions_disabled(tmp_path):
    cfg = AppConfig()
    cfg.input.folder = str(tmp_path)
    cfg.behavior.run_mode = "loop"
    cfg.file_actions.enabled = True
    runner = Runner(cfg, _DummyConnection(), _DummyLogger())
    runner.start()
    runner.stop()
    assert cfg.file_actions.enabled is False
