"""Helper for PEKAT Code module: add external pydeps folder to sys.path."""

from __future__ import annotations

import sys
from pathlib import Path


DEFAULT_PYDEPS = Path(r"C:\ProgramData\PEKAT\pydeps")


def add_pydeps_to_sys_path(pydeps_path: str | Path = DEFAULT_PYDEPS) -> Path:
    path = Path(pydeps_path)
    try:
        resolved = str(path.resolve())
    except Exception:
        resolved = str(path)

    if resolved not in sys.path:
        sys.path.insert(0, resolved)
    return path


if __name__ == "__main__":
    selected = add_pydeps_to_sys_path()
    print(f"Updated sys.path with: {selected}")
