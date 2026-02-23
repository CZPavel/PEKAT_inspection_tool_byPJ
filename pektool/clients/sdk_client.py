from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, Dict, Optional, Tuple

from ..io.image_loader import encode_png
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
        # Primary path: pass object directly (Path/bytes/numpy) to SDK instance.
        try:
            result = self._call_analyze(
                image=image,
                data=data,
                timeout_sec=timeout_sec,
                response_type=response_type,
                context_in_body=context_in_body,
            )
            return self._extract_context_and_image(result)
        except Exception:
            if not BaseClient.is_numpy(image):
                raise

        # Send-only fallback for SDK runtimes that do not accept numpy image directly.
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                tmp_path = Path(handle.name)
                handle.write(encode_png(image))  # type: ignore[arg-type]
            result = self._call_analyze(
                image=tmp_path,
                data=data,
                timeout_sec=timeout_sec,
                response_type=response_type,
                context_in_body=context_in_body,
            )
            return self._extract_context_and_image(result)
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _call_analyze(
        self,
        *,
        image: object,
        data: str,
        timeout_sec: int,
        response_type: str,
        context_in_body: bool,
    ) -> object:
        kwargs = dict(response_type=response_type, data=data, timeout=timeout_sec)
        try:
            return self._instance.analyze(image, **kwargs, context_in_body=context_in_body)
        except TypeError:
            return self._instance.analyze(image, **kwargs)

    def _extract_context_and_image(
        self, result: object
    ) -> Tuple[Optional[Dict[str, Any]], Optional[bytes]]:
        if isinstance(result, dict):
            return result, None

        if isinstance(result, (tuple, list)):
            if len(result) >= 2:
                context = result[0] if isinstance(result[0], dict) else None
                image_bytes = result[1] if isinstance(result[1], (bytes, bytearray)) else None
                return context, bytes(image_bytes) if image_bytes is not None else None
            if len(result) == 1 and isinstance(result[0], dict):
                return result[0], None

        context = getattr(result, "context", None)
        image_bytes = (
            getattr(result, "image_bytes", None)
            or getattr(result, "image", None)
            or getattr(result, "annotated_image", None)
        )
        if isinstance(context, dict):
            if isinstance(image_bytes, bytearray):
                image_bytes = bytes(image_bytes)
            if isinstance(image_bytes, bytes):
                return context, image_bytes
            return context, None

        return None, None

