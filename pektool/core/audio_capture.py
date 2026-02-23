from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from ..config import AppConfig


class AudioSnapshotProducer:
    """Capture periodic microphone windows and save them as spectrogram PNG snapshots."""

    def __init__(
        self,
        config: AppConfig,
        logger,
        stop_event,
        on_snapshot: Callable[[Path], None],
    ) -> None:
        self.config = config
        self.logger = logger
        self.stop_event = stop_event
        self.on_snapshot = on_snapshot
        self.audio_cfg = config.audio
        self.snapshot_dir = Path(self.audio_cfg.snapshot_dir).expanduser()
        self._sounddevice = self._load_sounddevice()

    def run(self) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        interval = float(self.audio_cfg.interval_sec)
        next_tick = time.monotonic()

        while not self.stop_event.is_set():
            cycle_start = time.monotonic()
            try:
                samples = self._capture_audio_window()
                spectrogram = self._build_spectrogram(samples)
                snapshot_path = self.snapshot_dir / self._build_snapshot_name()
                if not cv2.imwrite(str(snapshot_path), spectrogram):
                    raise RuntimeError(f"Unable to save snapshot to {snapshot_path}")
                self.on_snapshot(snapshot_path)
            except Exception as exc:
                self.logger.warning("Audio snapshot failed: %s", exc)

            next_tick = max(next_tick + interval, cycle_start + interval)
            sleep_time = next_tick - time.monotonic()
            if sleep_time > 0:
                self.stop_event.wait(sleep_time)

    def _load_sounddevice(self):
        if self.audio_cfg.backend != "sounddevice":
            raise RuntimeError(f"Unsupported audio backend: {self.audio_cfg.backend}")
        try:
            import sounddevice as sd  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Missing dependency 'sounddevice'. Install it via 'pip install sounddevice'."
            ) from exc
        return sd

    def _capture_audio_window(self) -> np.ndarray:
        sample_rate = int(self.audio_cfg.sample_rate_hz)
        frames = max(1, int(round(float(self.audio_cfg.window_sec) * sample_rate)))
        device = self.audio_cfg.device_name.strip() or None
        recording = self._sounddevice.rec(
            frames=frames,
            samplerate=sample_rate,
            channels=int(self.audio_cfg.channels),
            dtype="float32",
            device=device,
        )
        self._sounddevice.wait()
        samples = np.asarray(recording, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            raise RuntimeError("Microphone returned empty capture buffer.")
        return samples

    def _build_spectrogram(self, samples: np.ndarray) -> np.ndarray:
        if samples.size < 64:
            raise RuntimeError("Audio window is too short for spectrogram generation.")

        fft_size = min(1024, samples.size)
        fft_size = max(64, 2 ** int(np.floor(np.log2(fft_size))))
        hop = max(32, fft_size // 4)

        if samples.size < fft_size:
            samples = np.pad(samples, (0, fft_size - samples.size))

        window = np.hanning(fft_size).astype(np.float32)
        frames = []
        for start in range(0, max(1, samples.size - fft_size + 1), hop):
            segment = samples[start : start + fft_size]
            if segment.size < fft_size:
                segment = np.pad(segment, (0, fft_size - segment.size))
            frames.append(np.fft.rfft(segment * window))
        if not frames:
            frames.append(np.fft.rfft(samples[:fft_size] * window))

        magnitude = np.abs(np.stack(frames, axis=1))
        db = 20.0 * np.log10(magnitude + 1e-8)
        db -= float(np.max(db))
        db = np.clip(db, -80.0, 0.0)
        normalized = ((db + 80.0) / 80.0 * 255.0).astype(np.uint8)
        image = cv2.flip(normalized, 0)
        return cv2.applyColorMap(image, cv2.COLORMAP_INFERNO)

    def _build_snapshot_name(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        prefix = self.audio_cfg.file_prefix.strip() or "mic"
        return f"{prefix}_{timestamp}.png"
