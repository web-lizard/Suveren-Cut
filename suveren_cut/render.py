from __future__ import annotations

from pathlib import Path
import re
import subprocess

from .ffmpeg_tools import get_ffmpeg_exe
from .naming import safe_filename, unique_path
from .timecodes import Clip, seconds_to_stamp


def ensure_ffmpeg() -> None:
    get_ffmpeg_exe()


def _even(value: int, minimum: int = 2) -> int:
    value = int(value)
    if value < minimum:
        value = minimum
    if value % 2:
        value -= 1
    return max(minimum, value)


def get_video_size(video_path: Path) -> tuple[int, int]:
    ffmpeg_exe = get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-i",
        str(video_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (proc.stderr or "") + "\n" + (proc.stdout or "")

    matches = re.findall(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    if not matches:
        matches = re.findall(r"(\d{3,5})x(\d{3,5})", text)

    if not matches:
        raise RuntimeError("Could not detect video size from ffmpeg output.")

    sizes = [(int(w), int(h)) for w, h in matches]
    return max(sizes, key=lambda pair: pair[0] * pair[1])


def extract_frame(video_path: Path, output_path: Path, *, at_seconds: float = 0) -> Path:
    ffmpeg_exe = get_ffmpeg_exe()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-y",
        "-ss",
        str(max(0, float(at_seconds))),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError("frame extract failed\n\n" + proc.stderr[-3000:])

    return output_path


def _bounded_crop(
    *,
    src_w: int,
    src_h: int,
    x: int,
    y: int,
    w: int,
    h: int,
) -> tuple[int, int, int, int]:
    x = max(0, int(x))
    y = max(0, int(y))

    if x >= src_w:
        x = 0
    if y >= src_h:
        y = 0

    w = max(2, int(w))
    h = max(2, int(h))

    w = min(w, src_w - x)
    h = min(h, src_h - y)

    w = _even(w)
    h = _even(h)
    x = _even(x, minimum=0)
    y = _even(y, minimum=0)

    return x, y, w, h


def build_video_filter(
    video_path: Path,
    *,
    output_mode: str,
    top_x: int = 0,
    top_y: int = 0,
    top_w: int = 1280,
    top_h: int = 720,
    bottom_x: int = 0,
    bottom_y: int = 540,
    bottom_w: int = 1920,
    bottom_h: int = 540,
    top_percent: int = 58,
) -> tuple[list[str], list[str]]:
    if output_mode == "original_16_9":
        return [], ["-map", "0:v:0", "-map", "0:a:0?"]

    if output_mode == "shorts_center_crop":
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        return ["-vf", vf], ["-map", "0:v:0", "-map", "0:a:0?"]

    if output_mode == "shorts_stacked":
        src_w, src_h = get_video_size(video_path)

        top_x, top_y, top_w, top_h = _bounded_crop(
            src_w=src_w,
            src_h=src_h,
            x=top_x,
            y=top_y,
            w=top_w,
            h=top_h,
        )

        bottom_x, bottom_y, bottom_w, bottom_h = _bounded_crop(
            src_w=src_w,
            src_h=src_h,
            x=bottom_x,
            y=bottom_y,
            w=bottom_w,
            h=bottom_h,
        )

        top_percent = max(25, min(80, int(top_percent)))
        top_out_h = _even(round(1920 * top_percent / 100))
        bottom_out_h = _even(1920 - top_out_h)

        complex_filter = (
            f"[0:v]split=2[topsrc][bottomsrc];"
            f"[topsrc]crop={top_w}:{top_h}:{top_x}:{top_y},"
            f"scale=1080:{top_out_h}:force_original_aspect_ratio=increase,"
            f"crop=1080:{top_out_h}[top];"
            f"[bottomsrc]crop={bottom_w}:{bottom_h}:{bottom_x}:{bottom_y},"
            f"scale=1080:{bottom_out_h}:force_original_aspect_ratio=increase,"
            f"crop=1080:{bottom_out_h}[bottom];"
            f"[top][bottom]vstack=inputs=2[v]"
        )

        return ["-filter_complex", complex_filter], ["-map", "[v]", "-map", "0:a:0?"]

    raise ValueError(f"Unknown output_mode: {output_mode}")


def render_clip(
    video_path: Path,
    clip: Clip,
    output_dir: Path,
    *,
    output_mode: str = "shorts_center_crop",
    vertical: bool | None = None,
    crf: int = 21,
    preset: str = "veryfast",
    top_x: int = 0,
    top_y: int = 0,
    top_w: int = 1280,
    top_h: int = 720,
    bottom_x: int = 0,
    bottom_y: int = 540,
    bottom_w: int = 1920,
    bottom_h: int = 540,
    top_percent: int = 58,
) -> Path:
    ffmpeg_exe = get_ffmpeg_exe()
    output_dir.mkdir(parents=True, exist_ok=True)

    if vertical is not None:
        output_mode = "shorts_center_crop" if vertical else "original_16_9"

    start = seconds_to_stamp(clip.start)
    duration = f"{clip.duration:.3f}"

    filename = safe_filename(f"{clip.index:03d}_{clip.title}", fallback=f"clip_{clip.index:03d}") + ".mp4"
    output_path = unique_path(output_dir / filename)

    filter_args, map_args = build_video_filter(
        video_path,
        output_mode=output_mode,
        top_x=top_x,
        top_y=top_y,
        top_w=top_w,
        top_h=top_h,
        bottom_x=bottom_x,
        bottom_y=bottom_y,
        bottom_w=bottom_w,
        bottom_h=bottom_h,
        top_percent=top_percent,
    )

    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-y",
        "-ss",
        start,
        "-i",
        str(video_path),
        "-t",
        duration,
    ]

    cmd += filter_args
    cmd += map_args

    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed\n\nCOMMAND:\n"
            + " ".join(cmd)
            + "\n\nSTDERR:\n"
            + proc.stderr[-5000:]
        )

    return output_path
