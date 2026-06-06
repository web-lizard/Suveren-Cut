from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from .naming import safe_filename, unique_path
from .timecodes import Clip, seconds_to_stamp


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg не найден в PATH. Поставь ffmpeg и перезапусти PowerShell.")


def render_clip(
    video_path: Path,
    clip: Clip,
    output_dir: Path,
    *,
    vertical: bool = True,
    crf: int = 21,
    preset: str = "veryfast",
) -> Path:
    ensure_ffmpeg()
    output_dir.mkdir(parents=True, exist_ok=True)

    start = seconds_to_stamp(clip.start)
    duration = f"{clip.duration:.3f}"

    filename = safe_filename(f"{clip.index:03d}_{clip.title}", fallback=f"clip_{clip.index:03d}") + ".mp4"
    output_path = unique_path(output_dir / filename)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss", start,
        "-i", str(video_path),
        "-t", duration,
        "-map", "0:v:0",
        "-map", "0:a:0?",
    ]

    if vertical:
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        cmd += ["-vf", vf]

    cmd += [
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed\n\nCOMMAND:\n"
            + " ".join(cmd)
            + "\n\nSTDERR:\n"
            + proc.stderr[-4000:]
        )

    return output_path
