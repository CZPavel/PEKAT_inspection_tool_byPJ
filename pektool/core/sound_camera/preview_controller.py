from __future__ import annotations

import queue
import threading
from typing import Optional

from ...config import AppConfig
from .engine import SoundCameraEngine
from .models import SoundCameraFrame


class SoundCameraPreviewController:
    """Standalone preview lifecycle controller independent from Runner sending."""

    def __init__(self, *, logger) -> None:
        self.logger = logger
        self._queue: "queue.Queue[SoundCameraFrame]" = queue.Queue(maxsize=4)
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._engine: Optional[SoundCameraEngine] = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, config: AppConfig) -> None:
        with self._lock:
            if self.is_running():
                return
            self._clear_queue()
            self._stop_event = threading.Event()

        def _on_frame(frame: SoundCameraFrame) -> None:
            while True:
                try:
                    self._queue.put_nowait(frame)
                    return
                except queue.Full:
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        return

        with self._lock:
            self._engine = SoundCameraEngine(
                config=config,
                logger=self.logger,
                stop_event=self._stop_event,
                on_frame=_on_frame,
            )
            self._thread = threading.Thread(target=self._engine.run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if self._stop_event is not None:
                self._stop_event.set()
            if self._thread is not None:
                self._thread.join(timeout=2.0)
            self._thread = None
            self._stop_event = None
            self._engine = None
            self._clear_queue()

    def reconfigure(self, config: AppConfig) -> None:
        with self._lock:
            running = self.is_running()
        if running:
            self.stop()
            self.start(config)

    def poll_latest(self) -> Optional[SoundCameraFrame]:
        latest: Optional[SoundCameraFrame] = None
        while True:
            try:
                latest = self._queue.get_nowait()
            except queue.Empty:
                break
        return latest

    def _clear_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
