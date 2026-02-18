from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


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
    image_bytes: Optional[bytes] = None
    artifact_save: Optional["ArtifactSaveResult"] = None


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


@dataclass
class ArtifactSaveResult:
    json_saved: bool
    json_path: Optional[str]
    processed_saved: bool
    processed_path: Optional[str]
    reason: Optional[str]


@dataclass
class ScriptAsset:
    id: str
    name: str
    source_filename: str
    storage_path_utf8: str
    storage_path_raw: str
    format: Literal["txt", "py", "pmodule"]
    category: str
    tags: List[str]
    short_description: str
    encoding_source: str
    size_bytes: int
    sha256: str
    created_at: str
    updated_at: str
    empty: bool = False
    purpose: str = ""
    what_it_does: str = ""
    context_keys: str = ""
    dependencies: str = ""
    description_source: str = ""


@dataclass
class ScriptCatalogIndex:
    schema_version: str
    generated_at: str
    items: List[ScriptAsset]


@dataclass
class InstallTarget:
    pekat_root: str
    server_path: str
    detected_version: str
    is_valid: bool
    warning: Optional[str] = None


@dataclass
class InstallPlanItem:
    src: str
    dst: str
    exists: bool
    will_overwrite: bool
    size: int


@dataclass
class InstallPlan:
    library_name: str
    target: InstallTarget
    items: List[InstallPlanItem]
    new_files: int
    overwrite_files: int
    total_size: int


@dataclass
class InstallResult:
    success: bool
    copied: int
    overwritten: int
    backup_path: Optional[str]
    errors: List[str]
