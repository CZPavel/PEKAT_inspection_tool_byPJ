"""Helper for PEKAT Code module: add local server paths to sys.path."""

from __future__ import annotations

import sys
from pathlib import Path


def add_pekat_server_paths(context: dict | None = None) -> None:
    """Append likely PEKAT server paths so imports like `pyzbar` can resolve."""
    candidates = []
    if context and isinstance(context, dict):
        maybe_server = context.get("pekat_server_path")
        if maybe_server:
            candidates.append(Path(str(maybe_server)))

    candidates.extend(
        [
            Path.cwd(),
            Path.cwd() / "server",
            Path.cwd() / "libs",
        ]
    )

    for candidate in candidates:
        try:
            resolved = str(candidate.resolve())
        except Exception:
            resolved = str(candidate)
        if resolved not in sys.path:
            sys.path.append(resolved)


if __name__ == "__main__":
    add_pekat_server_paths({})
    print("Updated sys.path with PEKAT-like locations.")

