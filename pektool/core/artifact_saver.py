from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..config import AppConfig
from ..types import ArtifactSaveResult, NormalizedEvaluation
from .file_actions import build_target_dir, build_target_name, ensure_unique_target, resolve_effective_status


def save_artifacts(
    source_path: Path,
    context: Optional[dict[str, Any]],
    image_bytes: Optional[bytes],
    evaluation: NormalizedEvaluation,
    cfg: AppConfig,
    now: datetime,
) -> ArtifactSaveResult:
    file_cfg = cfg.file_actions
    save_json = bool(file_cfg.save_json_context)
    save_processed = bool(file_cfg.save_processed_image)

    if not save_json and not save_processed:
        return ArtifactSaveResult(
            json_saved=False,
            json_path=None,
            processed_saved=False,
            processed_path=None,
            reason="artifacts-disabled",
        )

    effective_status = resolve_effective_status(evaluation, file_cfg.unknown_as_nok)
    target_cfg = file_cfg.ok if effective_status == "OK" else file_cfg.nok
    if not target_cfg.base_dir.strip():
        return ArtifactSaveResult(
            json_saved=False,
            json_path=None,
            processed_saved=False,
            processed_path=None,
            reason=f"missing-target-dir-{effective_status.lower()}",
        )

    target_dir = build_target_dir(Path(target_cfg.base_dir), target_cfg, now)
    target_dir.mkdir(parents=True, exist_ok=True)

    reasons: list[str] = []
    json_saved = False
    json_path: Optional[str] = None
    processed_saved = False
    processed_path: Optional[str] = None

    if save_json:
        try:
            context_payload = context if isinstance(context, dict) else {}
            json_name = build_target_name(
                base_stem=source_path.stem,
                source_suffix=".json",
                effective_status=effective_status,
                cfg=target_cfg,
                now=now,
            )
            json_target = ensure_unique_target(target_dir / json_name)
            json_target.write_text(
                json.dumps(context_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            json_saved = True
            json_path = str(json_target)
        except Exception as exc:  # pragma: no cover - defensive
            reasons.append(f"json-save-failed:{exc}")

    if save_processed:
        if image_bytes is None:
            reasons.append("processed-image-missing")
        else:
            try:
                processed_name = build_target_name(
                    base_stem=f"ANOTATED_{source_path.stem}",
                    source_suffix=".png",
                    effective_status=effective_status,
                    cfg=target_cfg,
                    now=now,
                )
                processed_target = ensure_unique_target(target_dir / processed_name)
                processed_target.write_bytes(image_bytes)
                processed_saved = True
                processed_path = str(processed_target)
            except Exception as exc:  # pragma: no cover - defensive
                reasons.append(f"processed-save-failed:{exc}")

    return ArtifactSaveResult(
        json_saved=json_saved,
        json_path=json_path,
        processed_saved=processed_saved,
        processed_path=processed_path,
        reason="; ".join(reasons) if reasons else None,
    )
