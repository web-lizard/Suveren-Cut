from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .timecodes import Clip, seconds_to_stamp


def make_title(clip: Clip, channel_prefix: str = "Mr Lizard") -> str:
    title = clip.title.strip()
    if not title:
        title = "Фрагмент стрима"
    if len(title) > 78:
        title = title[:75].rstrip() + "..."
    return f"{channel_prefix}: {title}"


def make_description(clip: Clip, source_title: str = "", source_url: str = "") -> str:
    parts = [
        f"Фрагмент стрима: {clip.title}",
        f"Таймкод: {seconds_to_stamp(clip.start)}",
    ]

    if source_title:
        parts.append(f"Источник: {source_title}")
    if source_url:
        parts.append(f"Ссылка на оригинал: {source_url}")

    parts.append("")
    parts.append("#shorts #mrlizard #suverenitet #lizardia")
    return "\n".join(parts)


def write_manifest(
    output_dir: Path,
    rows: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = output_dir / "upload.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["file", "title", "description", "tags", "start", "end", "duration"],
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
