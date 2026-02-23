from __future__ import annotations

import threading

import numpy as np


class AudioRingBuffer:
    """Thread-safe float32 ring buffer for audio frames [samples, channels]."""

    def __init__(self, capacity_samples: int, channels: int) -> None:
        if capacity_samples <= 0:
            raise ValueError("capacity_samples must be > 0")
        if channels <= 0:
            raise ValueError("channels must be > 0")
        self.capacity_samples = int(capacity_samples)
        self.channels = int(channels)
        self._data = np.zeros((self.capacity_samples, self.channels), dtype=np.float32)
        self._write_pos = 0
        self._size = 0
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        with self._lock:
            return self._size

    def write(self, frames: np.ndarray) -> None:
        arr = np.asarray(frames, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr[:, None]
        if arr.ndim != 2:
            raise ValueError("frames must have shape [samples] or [samples, channels]")

        if arr.shape[1] != self.channels:
            if arr.shape[1] > self.channels:
                arr = arr[:, : self.channels]
            else:
                pad = np.zeros((arr.shape[0], self.channels - arr.shape[1]), dtype=np.float32)
                arr = np.concatenate([arr, pad], axis=1)

        n = int(arr.shape[0])
        if n <= 0:
            return

        with self._lock:
            if n >= self.capacity_samples:
                arr = arr[-self.capacity_samples :]
                n = arr.shape[0]
                self._data[:, :] = arr
                self._write_pos = 0
                self._size = n
                return

            end = self._write_pos + n
            if end <= self.capacity_samples:
                self._data[self._write_pos : end, :] = arr
            else:
                first = self.capacity_samples - self._write_pos
                self._data[self._write_pos :, :] = arr[:first, :]
                self._data[: end % self.capacity_samples, :] = arr[first:, :]

            self._write_pos = end % self.capacity_samples
            self._size = min(self.capacity_samples, self._size + n)

    def read_latest(self, num_samples: int) -> np.ndarray:
        n = max(1, int(num_samples))
        out = np.zeros((n, self.channels), dtype=np.float32)
        with self._lock:
            available = min(n, self._size)
            if available <= 0:
                return out

            start = (self._write_pos - available) % self.capacity_samples
            if start + available <= self.capacity_samples:
                recent = self._data[start : start + available]
            else:
                first = self.capacity_samples - start
                recent = np.concatenate(
                    [self._data[start:, :], self._data[: available - first, :]], axis=0
                )
        out[-available:, :] = recent
        return out
