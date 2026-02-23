from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from ...config import AppConfig
from .audio_sources import LoopbackSource, MicrophoneSource, SineSource
from .models import SoundCameraFrame
from .render_classic import render_classic_image
from .render_fuse7 import render_fuse7_image
from .render_lissajous import render_lissajous_image
from .render_payload import render_payload_image


class SoundCameraEngine:
    """Capture audio windows and render Sound camera frames."""

    def __init__(
        self,
        *,
        config: AppConfig,
        logger,
        stop_event,
        on_frame: Callable[[SoundCameraFrame], None],
    ) -> None:
        self.config = config
        self.logger = logger
        self.stop_event = stop_event
        self.on_frame = on_frame
        self.audio_cfg = config.audio
        self.source = None

    def run(self) -> None:
        interval = float(self._cfg("interval_sec", 2.0))
        next_tick = time.monotonic()
        self.source = self._build_source()
        self.source.start()

        send_mode = str(self._cfg("send_mode", "save_send")).strip().lower()
        snapshot_dir = Path(str(self._cfg("snapshot_dir", "sound_camera_snapshots"))).expanduser()
        if send_mode == "save_send":
            snapshot_dir.mkdir(parents=True, exist_ok=True)

        try:
            while not self.stop_event.is_set():
                cycle_start = time.monotonic()
                try:
                    frame = self._capture_and_render(snapshot_dir=snapshot_dir, send_mode=send_mode)
                    self.on_frame(frame)
                except Exception as exc:
                    self.logger.warning("Sound camera frame generation failed: %s", exc)
                    try:
                        self.on_frame(self._build_error_frame(exc))
                    except Exception:
                        pass

                next_tick = max(next_tick + interval, cycle_start + interval)
                sleep_time = next_tick - time.monotonic()
                if sleep_time > 0:
                    self.stop_event.wait(sleep_time)
        finally:
            if self.source is not None:
                try:
                    self.source.stop()
                except Exception:
                    pass
                self.source = None

    def _cfg(self, key: str, default):
        return getattr(self.audio_cfg, key, default)

    def _build_source(self):
        source = str(self._cfg("source", "loopback")).strip().lower()
        device_id = str(self._cfg("device_name", "") or "default")
        sample_rate = int(self._cfg("sample_rate_hz", 16000))
        channels = int(self._cfg("channels", 1))
        backend_policy = str(self._cfg("backend_policy", "auto")).strip().lower()
        if source == "loopback":
            return LoopbackSource(
                device_id=device_id if device_id else "default",
                sample_rate=sample_rate,
                channels=max(1, min(channels, 2)),
                backend_policy=backend_policy,
            )
        if source == "microphone":
            return MicrophoneSource(
                device_id=device_id if device_id else "default",
                sample_rate=sample_rate,
                channels=max(1, min(channels, 2)),
            )
        sine_freq = float(self._cfg("sine_freq_hz", 440.0))
        return SineSource(
            sample_rate=sample_rate,
            channels=max(1, min(channels, 2)),
            frequency_hz=sine_freq,
        )

    def _capture_and_render(self, *, snapshot_dir: Path, send_mode: str) -> SoundCameraFrame:
        assert self.source is not None
        source = str(self._cfg("source", "loopback")).strip().lower()
        approach = str(self._cfg("approach", "payload")).strip().lower()
        window_sec = float(self._cfg("window_sec", 1.0))
        samples_to_read = max(1, int(round(window_sec * float(self.source.sample_rate))))
        raw = self.source.get_latest(samples_to_read)
        mono = self._to_mono(raw)

        if approach == "lissajous":
            image, meta = self._render_lissajous(mono)
        elif approach == "classic":
            image, meta = self._render_classic(mono)
        else:
            image, meta = self._render_payload(raw)
            approach = "payload"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        prefix = str(self._cfg("file_prefix", "sound")).strip() or "sound"
        style_suffix = ""
        if approach == "classic":
            style_raw = str(meta.get("style", "")).strip().lower()
            style_clean = style_raw.replace(" ", "_") if style_raw else "classic"
            style_suffix = f"_{style_clean}"
        label_stem = f"{prefix}_{approach}{style_suffix}_{timestamp}"
        saved_path: Optional[Path] = None
        if send_mode == "save_send":
            saved_path = snapshot_dir / f"{label_stem}.png"
            if not cv2.imwrite(str(saved_path), image):
                raise RuntimeError(f"Unable to save sound camera snapshot: {saved_path}")

        return SoundCameraFrame(
            image_bgr=image,
            timestamp=time.time(),
            label_stem=label_stem,
            source=source if source in {"loopback", "microphone", "sine"} else "sine",
            approach=approach if approach in {"payload", "lissajous", "classic"} else "payload",
            saved_path=saved_path,
            meta=meta,
        )

    def _render_payload(self, samples: np.ndarray):
        payload_cfg = getattr(self.audio_cfg, "payload", None)
        frame_seconds = float(getattr(payload_cfg, "frame_seconds", self._cfg("window_sec", 1.0)))
        overlap_percent = float(getattr(payload_cfg, "overlap_percent", 50.0))
        style_mode = str(getattr(payload_cfg, "style_mode", "stack3"))
        y_repeat = int(getattr(payload_cfg, "y_repeat", 4))
        variant_mode = str(getattr(payload_cfg, "variant_mode", "none"))
        preview_resize_mode = str(getattr(payload_cfg, "preview_resize_mode", "pixel"))
        overlay_grid = bool(getattr(payload_cfg, "overlay_grid", True))
        overlay_time_ticks = bool(getattr(payload_cfg, "overlay_time_ticks", True))
        overlay_stack_bounds = bool(getattr(payload_cfg, "overlay_stack_bounds", True))
        overlay_legend = bool(getattr(payload_cfg, "overlay_legend", True))
        image, meta = render_payload_image(
            samples=samples,
            source_sr=int(self.source.sample_rate if self.source is not None else self._cfg("sample_rate_hz", 16000)),
            frame_seconds=frame_seconds,
            overlap_percent=overlap_percent,
            style_mode=style_mode,
            y_repeat=y_repeat,
            variant_mode=variant_mode,
            overlay_grid=overlay_grid,
            overlay_time_ticks=overlay_time_ticks,
            overlay_stack_bounds=overlay_stack_bounds,
            overlay_legend=overlay_legend,
        )
        meta["approach"] = "payload"
        meta["preview_resize_mode"] = preview_resize_mode
        return image, meta

    def _render_lissajous(self, mono: np.ndarray):
        liss = getattr(self.audio_cfg, "lissajous", None)
        tau_raw = getattr(liss, "tau", 5)
        tau = str(tau_raw).strip().lower()
        if tau != "both":
            tau = int(tau)  # type: ignore[assignment]
        width = int(getattr(liss, "width", 512))
        height = int(getattr(liss, "height", 512))
        accum = str(getattr(liss, "accum", "none"))
        point_size_step = int(getattr(liss, "point_size_step", 1))
        point_render_style = str(getattr(liss, "point_render_style", "classic"))
        value_mode = str(getattr(liss, "value_mode", "radial"))
        rotation = str(getattr(liss, "rotation", "none"))
        image, meta = render_lissajous_image(
            samples_mono=mono,
            tau=tau,
            width=width,
            height=height,
            accum=accum,  # type: ignore[arg-type]
            point_size_step=point_size_step,
            point_render_style=point_render_style,  # type: ignore[arg-type]
            value_mode=value_mode,  # type: ignore[arg-type]
            rotation=rotation,  # type: ignore[arg-type]
        )
        meta["approach"] = "lissajous"
        return image, meta

    def _render_classic(self, mono: np.ndarray):
        classic = getattr(self.audio_cfg, "classic", None)
        style = str(getattr(classic, "style", "classic")).strip().lower()
        width = int(getattr(classic, "width", 1024))
        height = int(getattr(classic, "height", 768))
        source_sr = int(self.source.sample_rate if self.source is not None else self._cfg("sample_rate_hz", 16000))
        common_kwargs = dict(
            samples=mono,
            source_sr=source_sr,
            width=width,
            height=height,
            n_fft=int(getattr(classic, "n_fft", 4096)),
            win_ms=float(getattr(classic, "win_ms", 25.0)),
            hop_ms=float(getattr(classic, "hop_ms", 1.0)),
            top_db=float(getattr(classic, "top_db", 80.0)),
            fmax=float(getattr(classic, "fmax", 24000.0)),
        )
        if style in {"fuse7", "fuse4_base"}:
            image, meta = render_fuse7_image(
                style=style,  # type: ignore[arg-type]
                n_mels_hue=int(getattr(classic, "n_mels_hue", 128)),
                n_mels_layers=int(getattr(classic, "n_mels_layers", 64)),
                scale_mode=str(getattr(classic, "scale_mode", "top_db")),  # type: ignore[arg-type]
                p_lo=float(getattr(classic, "p_lo", 1.0)),
                p_hi=float(getattr(classic, "p_hi", 99.0)),
                fuse7_profile=str(getattr(classic, "fuse7_profile", "ref_compat")),  # type: ignore[arg-type]
                norm_p=float(getattr(classic, "norm_p", 99.5)),
                freq_green_bias=float(getattr(classic, "freq_green_bias", 0.15)),
                edge_base_alpha=float(getattr(classic, "edge_base_alpha", 0.25)),
                flux_gain=float(getattr(classic, "flux_gain", 110.0)),
                edge_gain=float(getattr(classic, "edge_gain", 70.0)),
                **common_kwargs,
            )
        else:
            image, meta = render_classic_image(
                preset=str(getattr(classic, "preset", "none")),  # type: ignore[arg-type]
                colormap=str(getattr(classic, "colormap", "gray")),  # type: ignore[arg-type]
                gamma=float(getattr(classic, "gamma", 1.0)),
                detail_mode=str(getattr(classic, "detail_mode", "off")),  # type: ignore[arg-type]
                detail_sigma=float(getattr(classic, "detail_sigma", 1.2)),
                detail_gain=float(getattr(classic, "detail_gain", 70.0)),
                detail_p=float(getattr(classic, "detail_p", 99.5)),
                freq_interp=str(getattr(classic, "freq_interp", "auto")),  # type: ignore[arg-type]
                axis_mode=str(getattr(classic, "axis_mode", "linear")),  # type: ignore[arg-type]
                scale_mode=str(getattr(classic, "scale_mode", "top_db")),  # type: ignore[arg-type]
                p_lo=float(getattr(classic, "p_lo", 1.0)),
                p_hi=float(getattr(classic, "p_hi", 99.0)),
                **common_kwargs,
            )
        meta["approach"] = "classic"
        meta["style"] = str(meta.get("style", style or "classic"))
        return image, meta

    def _build_error_frame(self, exc: Exception) -> SoundCameraFrame:
        approach = str(self._cfg("approach", "payload")).strip().lower()
        source = str(self._cfg("source", "loopback")).strip().lower()
        if approach == "classic":
            classic = getattr(self.audio_cfg, "classic", None)
            width = int(getattr(classic, "width", 1024))
            height = int(getattr(classic, "height", 768))
        elif approach == "lissajous":
            liss = getattr(self.audio_cfg, "lissajous", None)
            width = int(getattr(liss, "width", 512))
            height = int(getattr(liss, "height", 512))
        else:
            payload = getattr(self.audio_cfg, "payload", None)
            frame_seconds = float(getattr(payload, "frame_seconds", 1.0))
            width = max(1, int(round(frame_seconds * 1000.0)))
            y_repeat = int(getattr(payload, "y_repeat", 4))
            style_mode = str(getattr(payload, "style_mode", "stack3"))
            sections = 3 if style_mode == "stack3" else 1
            height = max(64, int(64 * max(1, y_repeat) * sections))
        image = np.zeros((height, width, 3), dtype=np.uint8)
        msg = f"render error: {type(exc).__name__}"
        cv2.putText(
            image,
            msg[:80],
            (12, min(height - 12, 28)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            str(exc)[:120],
            (12, min(height - 12, 54)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        prefix = str(self._cfg("file_prefix", "sound")).strip() or "sound"
        label_stem = f"{prefix}_{approach}_error_{timestamp}"
        meta = {
            "approach": approach,
            "error": str(exc),
            "width_px": int(width),
            "height_px": int(height),
        }
        return SoundCameraFrame(
            image_bgr=image,
            timestamp=time.time(),
            label_stem=label_stem,
            source=source if source in {"loopback", "microphone", "sine"} else "sine",
            approach=approach if approach in {"payload", "lissajous", "classic"} else "payload",
            saved_path=None,
            meta=meta,
        )

    @staticmethod
    def _to_mono(samples: np.ndarray) -> np.ndarray:
        arr = np.asarray(samples, dtype=np.float32)
        if arr.ndim == 1:
            return arr
        if arr.ndim == 2:
            return arr.mean(axis=1, dtype=np.float32)
        raise ValueError(f"Unexpected audio array shape: {arr.shape}")
