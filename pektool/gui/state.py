from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.connection import ConnectionManager
from ..core.runner import Runner


@dataclass
class GuiState:
    runner: Optional[Runner] = None
    connection: Optional[ConnectionManager] = None
    config: Optional[object] = None
