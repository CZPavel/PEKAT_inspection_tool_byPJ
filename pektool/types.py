from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional


@dataclass
class ImageTask:
    path: Path
    data_value: str


@dataclass
class AnalyzeResult:
    status: str
    latency_ms: int
    error: Optional[str]
    context: Optional[Dict[str, Any]]
    ok_nok: Optional[str]
    evaluation: Optional["NormalizedEvaluation"] = None
    file_action: Optional["FileActionResult"] = None


@dataclass
class NormalizedEvaluation:
    eval_status: Literal["OK", "NOK", "UNKNOWN", "ERROR"]
    result_bool: Optional[bool]
    ok_nok: Optional[str]
    complete_time_s: Optional[float]
    complete_time_ms: Optional[int]
    detected_count: int


@dataclass
class FileActionResult:
    applied: bool
    operation: Literal["none", "delete", "move"]
    source_path: str
    target_path: Optional[str]
    reason: Optional[str]
    eval_status: Literal["OK", "NOK", "UNKNOWN", "ERROR"]
