from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


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