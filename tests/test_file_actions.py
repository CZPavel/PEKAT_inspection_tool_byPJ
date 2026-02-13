from datetime import datetime
from pathlib import Path

from pektool.config import AppConfig
from pektool.core.file_actions import apply_file_action
from pektool.types import NormalizedEvaluation


def _evaluation(status: str) -> NormalizedEvaluation:
    return NormalizedEvaluation(
        eval_status=status,  # type: ignore[arg-type]
        result_bool=True if status == "OK" else False if status == "NOK" else None,
        ok_nok=status if status in {"OK", "NOK"} else None,
        complete_time_s=0.1,
        complete_time_ms=100,
        detected_count=0,
    )


def _base_cfg() -> AppConfig:
    cfg = AppConfig()
    cfg.file_actions.enabled = True
    cfg.file_actions.mode = "move_by_result"
    return cfg


def test_file_actions_delete_after_eval_ok_nok(tmp_path):
    cfg = _base_cfg()
    cfg.file_actions.mode = "delete_after_eval"
    ok_file = tmp_path / "ok.png"
    nok_file = tmp_path / "nok.png"
    ok_file.write_bytes(b"x")
    nok_file.write_bytes(b"x")

    ok_result = apply_file_action(ok_file, _evaluation("OK"), cfg, datetime(2026, 2, 10, 7, 30, 0))
    nok_result = apply_file_action(nok_file, _evaluation("NOK"), cfg, datetime(2026, 2, 10, 7, 30, 0))

    assert ok_result.applied and ok_result.operation == "delete"
    assert nok_result.applied and nok_result.operation == "delete"
    assert not ok_file.exists()
    assert not nok_file.exists()


def test_file_actions_move_by_result_ok_to_ok_dir_nok_to_nok_dir(tmp_path):
    cfg = _base_cfg()
    cfg.file_actions.ok.base_dir = str(tmp_path / "ok")
    cfg.file_actions.nok.base_dir = str(tmp_path / "nok")
    ok_file = tmp_path / "a.png"
    nok_file = tmp_path / "b.png"
    ok_file.write_bytes(b"x")
    nok_file.write_bytes(b"x")

    ok_result = apply_file_action(ok_file, _evaluation("OK"), cfg, datetime(2026, 2, 10, 7, 30, 0))
    nok_result = apply_file_action(nok_file, _evaluation("NOK"), cfg, datetime(2026, 2, 10, 7, 30, 0))

    assert ok_result.applied and Path(ok_result.target_path).parent.name == "ok"  # type: ignore[arg-type]
    assert nok_result.applied and Path(nok_result.target_path).parent.name == "nok"  # type: ignore[arg-type]


def test_file_actions_move_ok_delete_nok(tmp_path):
    cfg = _base_cfg()
    cfg.file_actions.mode = "move_ok_delete_nok"
    cfg.file_actions.ok.base_dir = str(tmp_path / "ok")
    ok_file = tmp_path / "ok.png"
    nok_file = tmp_path / "nok.png"
    ok_file.write_bytes(b"x")
    nok_file.write_bytes(b"x")

    ok_result = apply_file_action(ok_file, _evaluation("OK"), cfg, datetime(2026, 2, 10, 7, 30, 0))
    nok_result = apply_file_action(nok_file, _evaluation("NOK"), cfg, datetime(2026, 2, 10, 7, 30, 0))

    assert ok_result.applied and ok_result.operation == "move"
    assert nok_result.applied and nok_result.operation == "delete"
    assert not nok_file.exists()


def test_file_actions_delete_ok_move_nok(tmp_path):
    cfg = _base_cfg()
    cfg.file_actions.mode = "delete_ok_move_nok"
    cfg.file_actions.nok.base_dir = str(tmp_path / "nok")
    ok_file = tmp_path / "ok.png"
    nok_file = tmp_path / "nok.png"
    ok_file.write_bytes(b"x")
    nok_file.write_bytes(b"x")

    ok_result = apply_file_action(ok_file, _evaluation("OK"), cfg, datetime(2026, 2, 10, 7, 30, 0))
    nok_result = apply_file_action(nok_file, _evaluation("NOK"), cfg, datetime(2026, 2, 10, 7, 30, 0))

    assert ok_result.applied and ok_result.operation == "delete"
    assert nok_result.applied and nok_result.operation == "move"
    assert not ok_file.exists()


def test_file_actions_unknown_error_treated_as_nok(tmp_path):
    cfg = _base_cfg()
    cfg.file_actions.nok.base_dir = str(tmp_path / "nok")
    src_file = tmp_path / "x.png"
    src_file.write_bytes(b"x")

    result = apply_file_action(src_file, _evaluation("UNKNOWN"), cfg, datetime(2026, 2, 10, 7, 30, 0))
    assert result.applied
    assert Path(result.target_path).parent.name == "nok"  # type: ignore[arg-type]


def test_file_actions_daily_hourly_folder_composition(tmp_path):
    cfg = _base_cfg()
    cfg.file_actions.ok.base_dir = str(tmp_path / "ok")
    cfg.file_actions.ok.create_daily_folder = True
    cfg.file_actions.ok.create_hourly_folder = True
    src_file = tmp_path / "x.png"
    src_file.write_bytes(b"x")

    now = datetime(2026, 2, 10, 7, 30, 0)
    result = apply_file_action(src_file, _evaluation("OK"), cfg, now)
    target = Path(result.target_path)  # type: ignore[arg-type]

    assert target.parent.name == "02_10_07"
    assert target.parent.parent.name == "2026_02_10"


def test_file_actions_filename_modifiers_order(tmp_path):
    cfg = _base_cfg()
    cfg.file_actions.ok.base_dir = str(tmp_path / "ok")
    cfg.file_actions.ok.include_result_prefix = True
    cfg.file_actions.ok.include_timestamp_suffix = True
    cfg.file_actions.ok.include_string = True
    cfg.file_actions.ok.string_value = "batchA"
    src_file = tmp_path / "sample.png"
    src_file.write_bytes(b"x")

    result = apply_file_action(src_file, _evaluation("OK"), cfg, datetime(2026, 2, 10, 7, 30, 0))
    assert Path(result.target_path).name == "OK_sample_2026_02_10_07_30_00_batchA.png"  # type: ignore[arg-type]


def test_file_actions_collision_auto_rename(tmp_path):
    cfg = _base_cfg()
    cfg.file_actions.ok.base_dir = str(tmp_path / "ok")
    target_dir = tmp_path / "ok"
    target_dir.mkdir()
    (target_dir / "sample.png").write_bytes(b"old")

    src_file = tmp_path / "sample.png"
    src_file.write_bytes(b"new")
    result = apply_file_action(src_file, _evaluation("OK"), cfg, datetime(2026, 2, 10, 7, 30, 0))

    assert Path(result.target_path).name == "sample_1.png"  # type: ignore[arg-type]
