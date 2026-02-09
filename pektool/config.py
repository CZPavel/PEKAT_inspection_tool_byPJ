from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, root_validator, validator


class RetryConfig(BaseModel):
    attempts: int = 5
    backoff_sec: float = 1.0
    max_backoff_sec: float = 10.0


class InputConfig(BaseModel):
    source_type: Literal["folder", "files"] = "folder"
    folder: str = ""
    include_subfolders: bool = True
    files: List[str] = Field(default_factory=list)
    extensions: List[str] = Field(
        default_factory=lambda: [
            ".png",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".tif",
            ".tiff",
            ".webp",
        ]
    )
    order: Literal["mtime"] = "mtime"
    poll_interval_sec: float = 1.0
    stability_checks: int = 2

    @validator("extensions", pre=True, always=True)
    def _lower_extensions(cls, value: List[str]) -> List[str]:
        return [ext.lower() for ext in value]


class BehaviorConfig(BaseModel):
    run_mode: Literal["loop", "once", "initial_then_watch"] = "initial_then_watch"
    delay_between_images_ms: int = 150
    queue_maxsize: int = 100
    max_workers: int = 1
    graceful_stop_timeout_sec: int = 10


class PekatConfig(BaseModel):
    timeout_sec: int = 10
    retry: RetryConfig = Field(default_factory=RetryConfig)
    response_type: Literal["context", "image", "annotated_image", "heatmap"] = "context"
    context_in_body: bool = False
    data_include_filename: bool = True
    data_include_timestamp: bool = False
    data_include_string: bool = False
    data_string_value: str = ""
    data_prefix: str = ""  # legacy support
    result_field: Optional[str] = None
    health_ping_sec: float = 5.0

    @root_validator(pre=True)
    def _apply_legacy_prefix(cls, values: dict) -> dict:
        data_prefix = values.get("data_prefix") or ""
        data_string_value = values.get("data_string_value") or ""
        data_include_string = values.get("data_include_string")
        if data_prefix and not data_string_value and not data_include_string:
            values["data_include_string"] = True
            values["data_string_value"] = data_prefix
        return values


class RestConfig(BaseModel):
    api_key: str = ""
    api_key_location: Literal["query", "header"] = "query"
    api_key_name: str = "api_key"
    use_session: bool = True


class ConnectionConfig(BaseModel):
    policy: Literal["off", "auto_start", "auto_start_stop", "auto_restart"] = "off"
    reconnect_attempts: int = 5
    reconnect_delay_sec: int = 30


class ProjectsManagerConfig(BaseModel):
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 7002
    tcp_enabled: bool = False
    enable_tcp: Optional[bool] = None
    http_base_url: str = "http://127.0.0.1:7000"
    enable_http_list: bool = False

    @root_validator(pre=True)
    def _map_enable_tcp(cls, values: dict) -> dict:
        if "tcp_enabled" not in values and "enable_tcp" in values:
            values["tcp_enabled"] = values.get("enable_tcp")
        return values


class LoggingConfig(BaseModel):
    directory: str = "logs"
    jsonl_filename: str = "results.jsonl"
    text_filename: str = "app.log"
    rotate_bytes: int = 1_048_576
    backups: int = 5


class AppConfig(BaseModel):
    mode: Literal["sdk", "rest"] = "rest"
    host: str = "127.0.0.1"
    port: int = 8000
    project_path: str = ""
    start_mode: Literal["auto", "connect_only", "always_start"] = "auto"
    already_running: bool = False

    input: InputConfig = Field(default_factory=InputConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    pekat: PekatConfig = Field(default_factory=PekatConfig)
    rest: RestConfig = Field(default_factory=RestConfig)
    projects_manager: ProjectsManagerConfig = Field(default_factory=ProjectsManagerConfig)
    connection: ConnectionConfig = Field(default_factory=ConnectionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    class Config:
        extra = "ignore"


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return AppConfig.parse_obj(payload)


def save_config(config: AppConfig, path: Path) -> None:
    data = config.dict()
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=False)


def resolve_path(path_value: str) -> Path:
    return Path(path_value).expanduser().resolve()

