from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from ..io.image_loader import encode_png, load_image_cv
from .base import BaseClient


class RestClient(BaseClient):
    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        api_key_location: str,
        api_key_name: str,
        use_session: bool = True,
    ) -> None:
        self.base_url = f"http://{host}:{port}"
        self.api_key = api_key
        self.api_key_location = api_key_location
        self.api_key_name = api_key_name
        self.session = requests.Session() if use_session else requests

    def _apply_api_key(self, params: Dict[str, str], headers: Dict[str, str]) -> None:
        if not self.api_key:
            return
        if self.api_key_location == "header":
            headers[self.api_key_name] = self.api_key
        else:
            params[self.api_key_name] = self.api_key

    def ping(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/ping", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def stop(self) -> None:
        try:
            self.session.get(f"{self.base_url}/stop", timeout=5)
        except requests.RequestException:
            pass

    def analyze(
        self,
        image: object,
        data: str,
        timeout_sec: int,
        response_type: str,
        context_in_body: bool,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[bytes]]:
        headers: Dict[str, str] = {"Content-Type": "application/octet-stream"}
        params: Dict[str, str] = {
            "response_type": response_type,
            "data": data,
            "context_in_body": "true" if context_in_body else "false",
        }
        self._apply_api_key(params, headers)

        if BaseClient.is_path(image):
            path = Path(image)
            if path.suffix.lower() == ".png":
                payload = path.read_bytes()
            else:
                payload = encode_png(load_image_cv(path))
        elif BaseClient.is_numpy(image):
            payload = encode_png(image)
        elif isinstance(image, (bytes, bytearray)):
            payload = bytes(image)
        else:
            raise ValueError("Unsupported image type for REST client")

        response = self.session.post(
            f"{self.base_url}/analyze_image",
            params=params,
            data=payload,
            headers=headers,
            timeout=timeout_sec,
        )
        response.raise_for_status()

        context = self._parse_context(response, context_in_body)
        return context, None

    def _parse_context(self, response: requests.Response, context_in_body: bool) -> Optional[Dict[str, Any]]:
        if context_in_body:
            image_len = int(response.headers.get("ImageLen", "0"))
            payload = response.content
            if image_len > 0:
                context_bytes = payload[image_len:]
            else:
                context_bytes = payload
            if not context_bytes:
                return None
            try:
                return json.loads(context_bytes.decode("utf-8"))
            except json.JSONDecodeError:
                return None

        header = response.headers.get("ContextBase64utf")
        if not header:
            return None
        try:
            decoded = base64.b64decode(header)
            return json.loads(decoded.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None

