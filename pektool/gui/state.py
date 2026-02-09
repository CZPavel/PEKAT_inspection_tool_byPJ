from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.runner import Runner


@dataclass
class GuiState:
    runner: Optional[Runner] = None
    client: Optional[object] = None
