from __future__ import annotations

from pathlib import Path

_WIDTH = 72


def _header(label: str = "") -> str:
    inner = f" {label} " if label else ""
    pad = (_WIDTH - len(inner)) // 2
    return "=" * pad + inner + "=" * (_WIDTH - pad - len(inner))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n} {unit}"
        n //= 1024
    return f"{n} PB"
