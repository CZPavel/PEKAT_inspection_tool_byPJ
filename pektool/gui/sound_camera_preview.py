from __future__ import annotations

from typing import Callable, Optional

import cv2
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets


class SoundCameraPreviewDialog(QtWidgets.QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sound camera preview")
        self.resize(960, 640)
        self.setMinimumSize(640, 420)

        self._image = np.zeros((128, 128, 3), dtype=np.uint8)
        self._snapshot_callback: Optional[Callable[[], None]] = None

        root = QtWidgets.QVBoxLayout(self)
        toolbar = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("No frame yet.")
        self.snapshot_btn = QtWidgets.QPushButton("Snapshot")
        self.snapshot_btn.clicked.connect(self._on_snapshot)
        toolbar.addWidget(self.status_label, 1)
        toolbar.addWidget(self.snapshot_btn, 0)
        root.addLayout(toolbar)

        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumSize(320, 240)
        root.addWidget(self.image_label, 1)

        self.meta_label = QtWidgets.QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet("color: #666;")
        root.addWidget(self.meta_label, 0)

    def set_snapshot_callback(self, callback: Optional[Callable[[], None]]) -> None:
        self._snapshot_callback = callback

    def _on_snapshot(self) -> None:
        if self._snapshot_callback is not None:
            self._snapshot_callback()

    def latest_image(self) -> np.ndarray:
        return np.asarray(self._image)

    def update_frame(self, image_bgr: np.ndarray, status_text: str, meta_text: str) -> None:
        self._image = np.asarray(image_bgr, dtype=np.uint8).copy()
        self.status_label.setText(status_text)
        self.meta_label.setText(meta_text)
        self._render_scaled_pixmap()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._render_scaled_pixmap()

    def _render_scaled_pixmap(self) -> None:
        if self._image.size == 0:
            return
        target_w = max(1, self.image_label.width())
        target_h = max(1, self.image_label.height())
        rgb = cv2.cvtColor(self._image, cv2.COLOR_BGR2RGB)
        display = cv2.resize(rgb, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        h, w = display.shape[:2]
        bytes_per_line = w * 3
        qimg = QtGui.QImage(display.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qimg.copy())
        self.image_label.setPixmap(pix)

