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


@dataclass
class NormalizedEvaluation:
    eval_status: Literal["OK", "NOK", "UNKNOWN", "ERROR"]
    result_bool: Optional[bool]
    ok_nok: Optional[str]
    complete_time_s: Optional[float]
    complete_time_ms: Optional[int]
    detected_count: int
