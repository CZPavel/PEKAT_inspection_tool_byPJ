from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import logging


@dataclass
class FileInfo:
    path: Path
    size: int
    mtime: float
    stable_count: int


class FileScanner:
    def __init__(
        self,
        folder: Path,
        include_subfolders: bool,
        extensions: List[str],
        stability_checks: int,
        logger: logging.Logger,
    ) -> None:
        self.folder = folder
        self.include_subfolders = include_subfolders
        self.extensions = set(ext.lower() for ext in extensions)
        self.stability_checks = max(stability_checks, 1)
        self.logger = logger
        self._state: Dict[Path, FileInfo] = {}

    def _iter_files(self) -> Iterable[Path]:
        if self.include_subfolders:
            yield from self.folder.rglob("*")
        else:
            yield from self.folder.glob("*")

    def scan(self) -> List[Path]:
        if not self.folder.exists():
            self.logger.warning("Input folder not found: %s", self.folder)
            return []

        new_state: Dict[Path, FileInfo] = {}
        ready: List[Tuple[float, Path]] = []

        for path in self._iter_files():
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.extensions:
                continue
            try:
                stat = path.stat()
            except OSError as exc:
                self.logger.warning("Failed to stat %s: %s", path, exc)
                continue

            previous = self._state.get(path)
            if previous and previous.size == stat.st_size and previous.mtime == stat.st_mtime:
                stable_count = previous.stable_count + 1
            else:
                stable_count = 0

            info = FileInfo(path=path, size=stat.st_size, mtime=stat.st_mtime, stable_count=stable_count)
            new_state[path] = info

            if stable_count >= self.stability_checks:
                ready.append((stat.st_mtime, path))

        self._state = new_state
        ready.sort(key=lambda item: item[0])
        return [path for _, path in ready]

    def reset(self) -> None:
        self._state.clear()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)
