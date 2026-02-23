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
    run_mode: Literal["loop", "once", "initial_then_watch", "just_watch"] = "initial_then_watch"
    delay_between_images_ms: int = 150
    queue_maxsize: int = 100
    max_workers: int = 1
    graceful_stop_timeout_sec: int = 10


FileActionMode = Literal[
    "delete_after_eval",
    "move_by_result",
    "move_ok_delete_nok",
    "delete_ok_move_nok",
]


class FileActionPathConfig(BaseModel):
    base_dir: str = ""
    create_daily_folder: bool = False
    create_hourly_folder: bool = False
    include_result_prefix: bool = False
    include_timestamp_suffix: bool = False
    include_string: bool = False
    string_value: str = ""


class FileActionsConfig(BaseModel):
    enabled: bool = False
    mode: FileActionMode = "move_by_result"
    unknown_as_nok: bool = True
    collision_policy: Literal["auto_rename"] = "auto_rename"
    save_json_context: bool = False
    save_processed_image: bool = False
    processed_response_type: Literal["annotated_image"] = "annotated_image"
    ok: FileActionPathConfig = Field(default_factory=FileActionPathConfig)
    nok: FileActionPathConfig = Field(default_factory=FileActionPathConfig)


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
    oknok_source: Literal["context_result", "result_field"] = "context_result"
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


class AudioConfig(BaseModel):
    enabled: bool = False
    # Legacy compatibility fields kept for older config/gui payloads.
    backend: Literal["sounddevice"] = "sounddevice"
    source_mode: Literal["audio_only"] = "audio_only"

    # Unified Sound camera runtime controls.
    approach: Literal["payload", "lissajous", "classic"] = "payload"
    source: Literal["loopback", "microphone", "sine"] = "loopback"
    backend_policy: Literal["auto", "prefer_pyaudiowpatch", "sounddevice_only"] = "auto"
    send_mode: Literal["save_send", "send_only"] = "save_send"
    device_name: str = ""
    sample_rate_hz: int = 16000
    channels: int = 1
    window_sec: float = 1.0
    interval_sec: float = 2.0
    snapshot_dir: str = "sound_camera_snapshots"
    file_prefix: str = "sound"
    sine_freq_hz: float = 440.0

    class PayloadConfig(BaseModel):
        frame_seconds: float = 1.0
        overlap_percent: float = 50.0
        style_mode: Literal[
            "raw_stream",
            "bitplane_transpose",
            "delta_bitplane_transpose",
            "stack3",
        ] = "stack3"
        y_repeat: Literal[1, 2, 4] = 4
        variant_mode: str = "none"
        preview_resize_mode: Literal["pixel", "smooth"] = "pixel"
        overlay_grid: bool = True
        overlay_time_ticks: bool = True
        overlay_stack_bounds: bool = True
        overlay_legend: bool = True

    class LissajousConfig(BaseModel):
        tau: Literal[1, 5, 10, 20, 50, "both"] = 5
        width: int = 512
        height: int = 512
        accum: Literal["none", "max", "sum", "avg"] = "none"
        point_size_step: int = 1
        point_render_style: Literal["classic", "sharp_stamp", "square_stamp"] = "classic"
        value_mode: Literal["radial", "flat"] = "radial"
        rotation: Literal["none", "plus45", "minus45"] = "none"

    class ClassicConfig(BaseModel):
        preset: Literal["none", "classic_fhd", "classic_impulse"] = "none"
        style: Literal["classic", "fuse7", "fuse4_base"] = "classic"
        axis_mode: Literal["linear", "log", "mel"] = "linear"
        scale_mode: Literal["top_db", "percentile"] = "top_db"
        p_lo: float = 1.0
        p_hi: float = 99.0
        n_mels_hue: int = 128
        n_mels_layers: int = 64
        fuse7_profile: Literal["default", "ref_compat"] = "ref_compat"
        norm_p: float = 99.5
        freq_green_bias: float = 0.15
        edge_base_alpha: float = 0.25
        flux_gain: float = 110.0
        edge_gain: float = 70.0
        width: int = 1024
        height: int = 768
        n_fft: int = 4096
        win_ms: float = 25.0
        hop_ms: float = 1.0
        top_db: float = 80.0
        fmax: float = 24000.0
        colormap: Literal["none", "gray", "turbo", "viridis", "magma"] = "gray"
        gamma: float = 1.0
        detail_mode: Literal["off", "highpass", "edgesobel"] = "off"
        detail_sigma: float = 1.2
        detail_gain: float = 70.0
        detail_p: float = 99.5
        freq_interp: Literal["auto", "area", "linear", "nearest"] = "auto"

        @root_validator(skip_on_failure=True)
        def _validate_ranges(cls, values: dict) -> dict:
            p_lo = float(values.get("p_lo", 1.0))
            p_hi = float(values.get("p_hi", 99.0))
            if p_lo < 0.0 or p_lo >= 100.0:
                raise ValueError("classic.p_lo must be in range [0, 100)")
            if p_hi <= 0.0 or p_hi > 100.0:
                raise ValueError("classic.p_hi must be in range (0, 100]")
            if p_lo >= p_hi:
                raise ValueError("classic.p_lo must be lower than classic.p_hi")

            n_mels_hue = int(values.get("n_mels_hue", 128))
            n_mels_layers = int(values.get("n_mels_layers", 64))
            if n_mels_hue < 8 or n_mels_hue > 512:
                raise ValueError("classic.n_mels_hue must be in range 8..512")
            if n_mels_layers < 8 or n_mels_layers > 512:
                raise ValueError("classic.n_mels_layers must be in range 8..512")

            norm_p = float(values.get("norm_p", 99.5))
            detail_p = float(values.get("detail_p", 99.5))
            if norm_p <= 0.0 or norm_p > 100.0:
                raise ValueError("classic.norm_p must be in range (0, 100]")
            if detail_p <= 0.0 or detail_p > 100.0:
                raise ValueError("classic.detail_p must be in range (0, 100]")

            edge_base_alpha = float(values.get("edge_base_alpha", 0.25))
            if edge_base_alpha < 0.0 or edge_base_alpha > 1.0:
                raise ValueError("classic.edge_base_alpha must be in range [0, 1]")
            return values

    payload: PayloadConfig = Field(default_factory=PayloadConfig)
    lissajous: LissajousConfig = Field(default_factory=LissajousConfig)
    classic: ClassicConfig = Field(default_factory=ClassicConfig)

    @validator("sample_rate_hz")
    def _validate_sample_rate(cls, value: int) -> int:
        if value < 8000 or value > 192000:
            raise ValueError("sample_rate_hz must be in range 8000..192000")
        return value

    @validator("channels")
    def _validate_channels(cls, value: int) -> int:
        if value < 1 or value > 2:
            raise ValueError("channels must be in range 1..2")
        return value

    @root_validator(skip_on_failure=True)
    def _validate_timing(cls, values: dict) -> dict:
        interval_sec = values.get("interval_sec")
        window_sec = values.get("window_sec")
        approach = str(values.get("approach", "payload")).strip().lower()
        if isinstance(interval_sec, (float, int)) and isinstance(window_sec, (float, int)):
            # Classic mode supports overlap between adjacent windows.
            if approach != "classic" and float(interval_sec) < float(window_sec):
                raise ValueError("interval_sec must be >= window_sec (except approach=classic)")
        return values

    @root_validator(pre=True)
    def _migrate_legacy_fields(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "interval_sec" not in values and "fps" in values:
            try:
                fps = float(values.get("fps", 0.0))
                if fps > 0.0:
                    values["interval_sec"] = 1.0 / fps
            except Exception:
                pass
        # Legacy default behavior was microphone-oriented audio-only flow.
        if "source" not in values:
            source_mode = str(values.get("source_mode", "")).strip().lower()
            if source_mode == "audio_only":
                values["source"] = "microphone"

        if "snapshot_dir" not in values and "audio_snapshot_dir" in values:
            values["snapshot_dir"] = values.get("audio_snapshot_dir")

        if "device_name" not in values and "audio_device_name" in values:
            values["device_name"] = values.get("audio_device_name")

        # Keep old defaults for existing persisted files when explicit values are missing.
        if "file_prefix" not in values and str(values.get("source_mode", "")).strip().lower() == "audio_only":
            values["file_prefix"] = values.get("file_prefix", "mic")
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
    file_actions: FileActionsConfig = Field(default_factory=FileActionsConfig)
    pekat: PekatConfig = Field(default_factory=PekatConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
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

