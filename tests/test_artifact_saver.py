import json
from datetime import datetime
from pathlib import Path

from pektool.config import AppConfig
from pektool.core.artifact_saver import save_artifacts
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


def _base_cfg(tmp_path: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.file_actions.save_json_context = True
    cfg.file_actions.save_processed_image = True
    cfg.file_actions.ok.base_dir = str(tmp_path / "ok")
    cfg.file_actions.nok.base_dir = str(tmp_path / "nok")
    return cfg


def test_processed_default_name_has_anotated_prefix(tmp_path):
    cfg = _base_cfg(tmp_path)
    source = tmp_path / "a.png"
    source.write_bytes(b"x")

    result = save_artifacts(
        source_path=source,
        context={"result": True},
        image_bytes=b"img",
        evaluation=_evaluation("OK"),
        cfg=cfg,
        now=datetime(2026, 2, 13, 10, 20, 30),
    )

    assert result.processed_saved is True
    assert Path(result.processed_path).name == "ANOTATED_a.png"  # type: ignore[arg-type]


def test_processed_name_with_include_result(tmp_path):
    cfg = _base_cfg(tmp_path)
    cfg.file_actions.ok.include_result_prefix = True
    source = tmp_path / "a.png"
    source.write_bytes(b"x")

    result = save_artifacts(
        source_path=source,
        context={"result": True},
        image_bytes=b"img",
        evaluation=_evaluation("OK"),
        cfg=cfg,
        now=datetime(2026, 2, 13, 10, 20, 30),
    )
    assert Path(result.processed_path).name == "OK_ANOTATED_a.png"  # type: ignore[arg-type]


def test_processed_name_with_timestamp_and_string(tmp_path):
    cfg = _base_cfg(tmp_path)
    cfg.file_actions.ok.include_timestamp_suffix = True
    cfg.file_actions.ok.include_string = True
    cfg.file_actions.ok.string_value = "batch1"
    source = tmp_path / "a.png"
    source.write_bytes(b"x")

    result = save_artifacts(
        source_path=source,
        context={"result": True},
        image_bytes=b"img",
        evaluation=_evaluation("OK"),
        cfg=cfg,
        now=datetime(2026, 2, 13, 10, 20, 30),
    )
    assert (
        Path(result.processed_path).name  # type: ignore[arg-type]
        == "ANOTATED_a_2026_02_13_10_20_30_batch1.png"
    )


def test_json_name_keeps_original_stem(tmp_path):
    cfg = _base_cfg(tmp_path)
    source = tmp_path / "a.png"
    source.write_bytes(b"x")

    result = save_artifacts(
        source_path=source,
        context={"result": True},
        image_bytes=b"img",
        evaluation=_evaluation("OK"),
        cfg=cfg,
        now=datetime(2026, 2, 13, 10, 20, 30),
    )
    assert Path(result.json_path).name == "a.json"  # type: ignore[arg-type]
    payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))  # type: ignore[arg-type]
    assert payload["result"] is True


def test_collision_auto_rename_for_anotated_file(tmp_path):
    cfg = _base_cfg(tmp_path)
    target_dir = tmp_path / "ok"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "ANOTATED_a.png").write_bytes(b"old")
    source = tmp_path / "a.png"
    source.write_bytes(b"x")

    result = save_artifacts(
        source_path=source,
        context={"result": True},
        image_bytes=b"img",
        evaluation=_evaluation("OK"),
        cfg=cfg,
        now=datetime(2026, 2, 13, 10, 20, 30),
    )
    assert Path(result.processed_path).name == "ANOTATED_a_1.png"  # type: ignore[arg-type]


def test_unknown_and_error_are_routed_to_nok(tmp_path):
    cfg = _base_cfg(tmp_path)
    source_unknown = tmp_path / "u.png"
    source_error = tmp_path / "e.png"
    source_unknown.write_bytes(b"x")
    source_error.write_bytes(b"x")

    unknown_result = save_artifacts(
        source_path=source_unknown,
        context={"result": None},
        image_bytes=b"img",
        evaluation=_evaluation("UNKNOWN"),
        cfg=cfg,
        now=datetime(2026, 2, 13, 10, 20, 30),
    )
    error_result = save_artifacts(
        source_path=source_error,
        context={"result": None},
        image_bytes=b"img",
        evaluation=_evaluation("ERROR"),
        cfg=cfg,
        now=datetime(2026, 2, 13, 10, 20, 30),
    )

    assert "nok" in Path(unknown_result.json_path).parts  # type: ignore[arg-type]
    assert "nok" in Path(error_result.processed_path).parts  # type: ignore[arg-type]
