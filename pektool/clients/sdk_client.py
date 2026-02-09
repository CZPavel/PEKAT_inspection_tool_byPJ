from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .base import BaseClient


class SDKClient(BaseClient):
    def __init__(
        self,
        host: str,
        port: int,
        project_path: str,
        start_mode: str,
        already_running: bool,
    ) -> None:
        try:
            from pekat_vision_sdk import Instance  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pekat-vision-sdk is not installed") from exc

        self._started_project = False
        self._instance = None

        project_path = project_path or ""
        if start_mode == "connect_only":
            self._instance = Instance(host=host, port=port, already_running=True)
        elif start_mode == "always_start":
            if not project_path:
                raise ValueError("project_path must be set when start_mode=always_start")
            self._instance = Instance(project_path, host=host, port=port)
            self._started_project = True
        else:  # auto
            if project_path and not already_running:
                self._instance = Instance(project_path, host=host, port=port)
                self._started_project = True
            else:
                self._instance = Instance(host=host, port=port, already_running=True)

    def ping(self) -> bool:
        try:
            return bool(self._instance.ping())
        except Exception:
            return False

    def stop(self) -> None:
        if self._started_project:
            try:
                self._instance.stop()
            except Exception:
                pass

    def analyze(
        self,
        image: object,
        data: str,
        timeout_sec: int,
        response_type: str,
        context_in_body: bool,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[bytes]]:
        kwargs = dict(response_type=response_type, data=data, timeout=timeout_sec)
        try:
            result = self._instance.analyze(image, **kwargs, context_in_body=context_in_body)
        except TypeError:
            result = self._instance.analyze(image, **kwargs)

        if isinstance(result, dict):
            return result, None
        return None, None