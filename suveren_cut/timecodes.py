from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


TIMECODE_RE = re.compile(r"(?P<stamp>(?:\d{1,2}:)?\d{1,2}:\d{2})(?P<title>.*)$")


@dataclass
class Marker:
    index: int
    start: float
    stamp: str
    title: str
    raw: str


@dataclass
class Clip:
    index: int
    start: float
    end: float
    duration: float
    title: str
    source_stamp: str


def stamp_to_seconds(stamp: str) -> float:
    parts = [int(p) for p in stamp.strip().split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return float(minutes * 60 + seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours * 3600 + minutes * 60 + seconds)
    raise ValueError(f"Bad timestamp: {stamp}")


def seconds_to_stamp(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def clean_title(title: str) -> str:
    title = title.strip(" -–—\t")
    # Убираем частые эмодзи/символы из начала, но не убиваем смысл.
    title = re.sub(r"^[^\wА-Яа-яЁё]+", "", title).strip()
    title = re.sub(r"\s+", " ", title)
    return title or "Фрагмент стрима"


def parse_timecodes(text: str) -> list[Marker]:
    markers: list[Marker] = []

    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue

        match = TIMECODE_RE.search(raw)
        if not match:
            continue

        stamp = match.group("stamp")
        title = clean_title(match.group("title") or "")

        markers.append(
            Marker(
                index=len(markers) + 1,
                start=stamp_to_seconds(stamp),
                stamp=stamp,
                title=title,
                raw=raw,
            )
        )

    # Убираем дубли таймкодов, сохраняя первый.
    unique: list[Marker] = []
    seen: set[float] = set()
    for marker in markers:
        if marker.start in seen:
            continue
        seen.add(marker.start)
        unique.append(marker)

    return sorted(unique, key=lambda m: m.start)


def build_clips(
    markers: Iterable[Marker],
    *,
    max_duration: float = 75,
    last_clip_duration: float = 60,
    min_duration: float = 10,
    max_clips: int = 20,
) -> list[Clip]:
    items = list(markers)
    clips: list[Clip] = []

    for idx, marker in enumerate(items):
        next_start = items[idx + 1].start if idx + 1 < len(items) else marker.start + last_clip_duration
        natural_end = max(marker.start, next_start - 0.25)

        end = min(natural_end, marker.start + max_duration) if max_duration > 0 else natural_end
        duration = end - marker.start

        if duration < min_duration:
            continue

        clips.append(
            Clip(
                index=len(clips) + 1,
                start=marker.start,
                end=end,
                duration=duration,
                title=marker.title,
                source_stamp=marker.stamp,
            )
        )

        if len(clips) >= max_clips:
            break

    return clips
