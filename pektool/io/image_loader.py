from __future__ import annotations

from pathlib import Path
from typing import Tuple

import cv2
import numpy as np


def load_image_cv(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Failed to read image: {path}")
    return image


def encode_png(image: np.ndarray) -> bytes:
    success, buf = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Failed to encode image as PNG")
    return buf.tobytes()


def load_png_bytes(path: Path) -> bytes:
    image = load_image_cv(path)
    return encode_png(image)


def load_raw_bytes_and_shape(path: Path) -> Tuple[bytes, int, int]:
    image = load_image_cv(path)
    height, width = image.shape[:2]
    return image.tobytes(), height, width