from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import numpy as np


SoundApproach = Literal["payload", "lissajous", "classic"]
SoundSource = Literal["loopback", "microphone", "sine"]
SoundSendMode = Literal["save_send", "send_only"]


@dataclass(slots=True)
class SoundCameraFrame:
    image_bgr: np.ndarray
    timestamp: float
    label_stem: str
    source: SoundSource
    approach: SoundApproach
    saved_path: Optional[Path] = None
    meta: Optional[Dict[str, Any]] = None

