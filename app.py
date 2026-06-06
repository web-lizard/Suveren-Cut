from __future__ import annotations

from pathlib import Path
import traceback

import streamlit as st

from suveren_cut.downloader import download_youtube, get_video_info
from suveren_cut.metadata import make_description, make_title, write_manifest
from suveren_cut.render import ensure_ffmpeg, render_clip
from suveren_cut.timecodes import build_clips, parse_timecodes, seconds_to_stamp


BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"
WORK_DIR = BASE_DIR / "work"


st.set_page_config(page_title="Sovereign Cut 2.0", page_icon="🦎", layout="wide")

st.title("🦎 Sovereign Cut 2.0 MVP")
st.caption("YouTube-ссылка + таймкоды → локальные нарезки + метаданные.")

with st.sidebar:
    st.header("Настройки")
    vertical = st.checkbox("Вертикальный формат 9:16 для Shorts", value=True)
    force_download = st.checkbox("Скачать заново, даже если файл уже есть", value=False)
    max_clips = st.number_input("Максимум клипов за прогон", min_value=1, max_value=100, value=12, step=1)
    max_duration = st.number_input("Максимальная длина клипа, сек", min_value=10, max_value=180, value=75, step=5)
    min_duration = st.number_input("Минимальная длина клипа, сек", min_value=1, max_value=60, value=10, step=1)
    last_clip_duration = st.number_input("Длина последнего клипа, сек", min_value=10, max_value=180, value=60, step=5)
    channel_prefix = st.text_input("Префикс заголовка", value="Mr Lizard")
    crf = st.slider("Качество CRF, меньше = лучше/тяжелее", min_value=16, max_value=30, value=21)

url = st.text_input("YouTube-ссылка на стрим", placeholder="https://www.youtube.com/watch?v=...")

timecodes = st.text_area(
    "Таймкоды",
    height=260,
    placeholder="00:00:00 🦎 Старт рептилоидной радиостанции\n00:04:39 🐊 Слава Лизардии\n00:12:30 🔥 Суверенитет выше магии",
)

col_a, col_b = st.columns([1, 1])

with col_a:
    preview_clicked = st.button("1. Проверить таймкоды", use_container_width=True)

with col_b:
    run_clicked = st.button("2. Скачать и нарезать", type="primary", use_container_width=True)

if preview_clicked:
    markers = parse_timecodes(timecodes)
    clips = build_clips(
        markers,
        max_duration=float(max_duration),
        last_clip_duration=float(last_clip_duration),
        min_duration=float(min_duration),
        max_clips=int(max_clips),
    )

    st.subheader("Найденные клипы")
    if not markers:
        st.warning("Таймкоды не распознаны. Проверь формат: 00:04:39 Название")
    else:
        st.write(f"Маркеров: {len(markers)}. Клипов после фильтров: {len(clips)}.")
        st.dataframe(
            [
                {
                    "№": c.index,
                    "start": seconds_to_stamp(c.start),
                    "end": seconds_to_stamp(c.end),
                    "duration": round(c.duration, 1),
                    "title": c.title,
                }
                for c in clips
            ],
            use_container_width=True,
            hide_index=True,
        )

if run_clicked:
    try:
        if not url.strip():
            st.error("Вставь YouTube-ссылку.")
            st.stop()

        markers = parse_timecodes(timecodes)
        if not markers:
            st.error("Таймкоды не распознаны. Нужны строки вида: 00:04:39 Название")
            st.stop()

        clips = build_clips(
            markers,
            max_duration=float(max_duration),
            last_clip_duration=float(last_clip_duration),
            min_duration=float(min_duration),
            max_clips=int(max_clips),
        )
        if not clips:
            st.error("После фильтров не осталось клипов. Уменьши минимальную длину или проверь таймкоды.")
            st.stop()

        ensure_ffmpeg()

        WORK_DIR.mkdir(parents=True, exist_ok=True)
        (WORK_DIR / "last_timecodes.txt").write_text(timecodes, encoding="utf-8")

        with st.status("Скачиваю видео через yt-dlp...", expanded=True) as status:
            video_path, info = download_youtube(url.strip(), DOWNLOADS_DIR, force=force_download)
            source_title = str(info.get("title") or "")
            st.write(f"Исходник: `{video_path}`")
            st.write(f"Название: {source_title or 'без названия'}")
            status.update(label="Видео готово. Режу клипы...", state="running")

            run_output_dir = OUTPUT_DIR / video_path.stem
            rows = []
            progress = st.progress(0)

            for i, clip in enumerate(clips, start=1):
                st.write(f"Режу {i}/{len(clips)}: {seconds_to_stamp(clip.start)} — {clip.title}")
                out = render_clip(
                    video_path,
                    clip,
                    run_output_dir,
                    vertical=vertical,
                    crf=int(crf),
                )

                rows.append(
                    {
                        "file": str(out),
                        "title": make_title(clip, channel_prefix=channel_prefix),
                        "description": make_description(clip, source_title=source_title, source_url=url.strip()),
                        "tags": "shorts,mrlizard,suverenitet,lizardia,stream",
                        "start": seconds_to_stamp(clip.start),
                        "end": seconds_to_stamp(clip.end),
                        "duration": round(clip.duration, 3),
                    }
                )
                progress.progress(i / len(clips))

            write_manifest(run_output_dir, rows)
            status.update(label="Готово. Нарезки собраны.", state="complete")

        st.success(f"Готово: {run_output_dir}")
        st.subheader("Файлы для загрузки")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(str(e))
        with st.expander("Технические подробности"):
            st.code(traceback.format_exc())
