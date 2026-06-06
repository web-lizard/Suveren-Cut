from __future__ import annotations

from pathlib import Path
import os
import shutil


def get_ffmpeg_exe() -> str:
    env_value = os.environ.get("SOVEREIGN_FFMPEG")
    if env_value and Path(env_value).exists():
        return env_value

    system_value = shutil.which("ffmpeg")
    if system_value:
        return system_value

    try:
        import imageio_ffmpeg

        bundled_value = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled_value and Path(bundled_value).exists():
            return str(bundled_value)
    except Exception as exc:
        raise RuntimeError(
            "ffmpeg is not available. Install dependencies: python -m pip install -r requirements.txt"
        ) from exc

    raise RuntimeError(
        "ffmpeg is not available. Install dependencies: python -m pip install -r requirements.txt"
    )


def get_ffmpeg_location_for_ytdlp() -> str:
    return str(Path(get_ffmpeg_exe()).parent)
