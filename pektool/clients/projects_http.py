from __future__ import annotations

from typing import Any, Dict, List

import requests


class ProjectsManagerHttp:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def list_projects(self) -> List[Dict[str, Any]]:
        response = requests.get(f"{self.base_url}/projects/list", timeout=5)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return payload
        return payload.get("projects", [])