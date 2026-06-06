from __future__ import annotations

from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from .naming import safe_filename


def _find_existing_by_id(download_dir: Path, video_id: str) -> Path | None:
    matches = sorted(
        [p for p in download_dir.glob(f"*{video_id}*") if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def get_video_info(url: str) -> dict[str, Any]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


def download_youtube(url: str, download_dir: Path, *, force: bool = False) -> tuple[Path, dict[str, Any]]:
    download_dir.mkdir(parents=True, exist_ok=True)

    info = get_video_info(url)
    video_id = str(info.get("id") or "")
    title = safe_filename(str(info.get("title") or "youtube_video"), limit=80)

    if video_id and not force:
        existing = _find_existing_by_id(download_dir, video_id)
        if existing:
            return existing, info

    outtmpl = str(download_dir / f"{title}_{video_id}.%(ext)s")

    opts = {
        "outtmpl": outtmpl,
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
    }

    before = {p.resolve() for p in download_dir.glob("*") if p.is_file()}

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    after = {p.resolve() for p in download_dir.glob("*") if p.is_file()}
    created = list(after - before)

    if video_id:
        by_id = _find_existing_by_id(download_dir, video_id)
        if by_id:
            return by_id, info

    if created:
        newest = sorted(created, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        return newest, info

    raise RuntimeError("yt-dlp finished, but downloaded file was not found.")
