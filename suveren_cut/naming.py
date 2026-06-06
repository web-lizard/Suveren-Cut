from __future__ import annotations

import re
from pathlib import Path


WINDOWS_FORBIDDEN = r'<>:"/\\|?*'


def safe_filename(value: str, fallback: str = "clip", limit: int = 90) -> str:
    value = value.strip()
    for char in WINDOWS_FORBIDDEN:
        value = value.replace(char, " ")
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("._ ")

    if not value:
        value = fallback

    return value[:limit].strip("._ ") or fallback


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    for i in range(2, 9999):
        candidate = parent / f"{stem}_{i:02d}{suffix}"
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Cannot create unique path for {path}")
