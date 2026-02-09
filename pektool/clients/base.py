from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np


class BaseClient(ABC):
    @abstractmethod
    def ping(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def analyze(
        self,
        image: object,
        data: str,
        timeout_sec: int,
        response_type: str,
        context_in_body: bool,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[bytes]]:
        raise NotImplementedError

    @staticmethod
    def is_path(obj: object) -> bool:
        return isinstance(obj, Path)

    @staticmethod
    def is_numpy(obj: object) -> bool:
        return isinstance(obj, np.ndarray)
