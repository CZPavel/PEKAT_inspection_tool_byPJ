from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal

from ..config import AppConfig, FileActionPathConfig
from ..types import FileActionResult, NormalizedEvaluation

_INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*]+')


def apply_file_action(
    path: Path,
    evaluation: NormalizedEvaluation,
    cfg: AppConfig,
    now: datetime,
) -> FileActionResult:
    file_cfg = cfg.file_actions
    if not file_cfg.enabled:
        return FileActionResult(
            applied=False,
            operation="none",
            source_path=str(path),
            target_path=None,
            reason="file-actions-disabled",
            eval_status=evaluation.eval_status,
        )

    effective_status = _resolve_effective_status(evaluation, file_cfg.unknown_as_nok)
    operation = _resolve_operation(file_cfg.mode, effective_status)
    if operation == "none":
        return FileActionResult(
            applied=False,
            operation="none",
            source_path=str(path),
            target_path=None,
            reason="no-operation",
            eval_status=evaluation.eval_status,
        )

    try:
        if operation == "delete":
            path.unlink()
            return FileActionResult(
                applied=True,
                operation="delete",
                source_path=str(path),
                target_path=None,
                reason=None,
                eval_status=evaluation.eval_status,
            )

        target_cfg = file_cfg.ok if effective_status == "OK" else file_cfg.nok
        if not target_cfg.base_dir.strip():
            return FileActionResult(
                applied=False,
                operation="move",
                source_path=str(path),
                target_path=None,
                reason=f"missing-target-dir-{effective_status.lower()}",
                eval_status=evaluation.eval_status,
            )

        target_dir = _build_target_dir(Path(target_cfg.base_dir), target_cfg, now)
        target_dir.mkdir(parents=True, exist_ok=True)

        target_name = _build_target_filename(path, effective_status, target_cfg, now)
        target_path = _ensure_unique_target(target_dir / target_name)

        if path.resolve() == target_path.resolve():
            return FileActionResult(
                applied=False,
                operation="move",
                source_path=str(path),
                target_path=str(target_path),
                reason="source-equals-target",
                eval_status=evaluation.eval_status,
            )

        shutil.move(str(path), str(target_path))
        return FileActionResult(
            applied=True,
            operation="move",
            source_path=str(path),
            target_path=str(target_path),
            reason=None,
            eval_status=evaluation.eval_status,
        )
    except FileNotFoundError:
        return FileActionResult(
            applied=False,
            operation=operation,
            source_path=str(path),
            target_path=None,
            reason="source-not-found",
            eval_status=evaluation.eval_status,
        )
    except Exception as exc:  # pragma: no cover - defensive path
        return FileActionResult(
            applied=False,
            operation=operation,
            source_path=str(path),
            target_path=None,
            reason=f"file-action-error:{exc}",
            eval_status=evaluation.eval_status,
        )


def _resolve_effective_status(
    evaluation: NormalizedEvaluation,
    unknown_as_nok: bool,
) -> Literal["OK", "NOK", "UNKNOWN"]:
    if evaluation.eval_status == "OK":
        return "OK"
    if evaluation.eval_status == "NOK":
        return "NOK"
    if unknown_as_nok:
        return "NOK"
    return "UNKNOWN"


def _resolve_operation(
    mode: str,
    effective_status: Literal["OK", "NOK", "UNKNOWN"],
) -> Literal["none", "delete", "move"]:
    if mode == "delete_after_eval":
        return "delete"
    if mode == "move_by_result":
        return "move"
    if mode == "move_ok_delete_nok":
        return "move" if effective_status == "OK" else "delete"
    if mode == "delete_ok_move_nok":
        return "delete" if effective_status == "OK" else "move"
    return "none"


def _build_target_dir(base_dir: Path, cfg: FileActionPathConfig, now: datetime) -> Path:
    target = base_dir
    if cfg.create_daily_folder:
        target = target / now.strftime("%Y_%m_%d")
    if cfg.create_hourly_folder:
        target = target / now.strftime("%m_%d_%H")
    return target


def _build_target_filename(
    source_path: Path,
    effective_status: Literal["OK", "NOK", "UNKNOWN"],
    cfg: FileActionPathConfig,
    now: datetime,
) -> str:
    stem = source_path.stem
    if cfg.include_result_prefix:
        stem = f"{effective_status}_{stem}"
    if cfg.include_timestamp_suffix:
        stem = f"{stem}_{now.strftime('%Y_%m_%d_%H_%M_%S')}"
    if cfg.include_string and cfg.string_value.strip():
        stem = f"{stem}_{_sanitize_fragment(cfg.string_value.strip())}"
    return f"{stem}{source_path.suffix}"


def _sanitize_fragment(value: str) -> str:
    return _INVALID_FILE_CHARS.sub("_", value)


def _ensure_unique_target(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 1
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1
