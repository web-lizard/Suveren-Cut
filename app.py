from __future__ import annotations

from pathlib import Path
import traceback

import streamlit as st

from suveren_cut.downloader import download_youtube
from suveren_cut.metadata import make_description, make_title, write_manifest
from suveren_cut.render import ensure_ffmpeg, get_video_size, render_clip
from suveren_cut.timecodes import build_clips, parse_timecodes, seconds_to_stamp


BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"
WORK_DIR = BASE_DIR / "work"


OUTPUT_MODE_LABELS = {
    "Оригинал 16:9 без кропа": "original_16_9",
    "Shorts 9:16, тупой центр-кроп": "shorts_center_crop",
    "Shorts 9:16, стек: верх + низ": "shorts_stacked",
}

LENGTH_PRESETS = {
    "Shorts standard, 60 сек": (60, 10, 45),
    "Shorts long, 90 сек": (90, 10, 60),
    "Shorts max, 120 сек": (120, 10, 75),
    "Clips, 3 минуты": (180, 20, 120),
    "Custom": None,
}


st.set_page_config(page_title="Sovereign Cut 2.1", page_icon="🦎", layout="wide")

st.title("🦎 Sovereign Cut 2.1")
st.caption("YouTube-ссылка + таймкоды -> локальные нарезки + режимы кадра + метаданные.")

with st.sidebar:
    st.header("Настройки")

    output_mode_label = st.selectbox(
        "Режим кадра",
        list(OUTPUT_MODE_LABELS.keys()),
        index=2,
    )
    output_mode = OUTPUT_MODE_LABELS[output_mode_label]

    length_preset = st.selectbox(
        "Пресет длины",
        list(LENGTH_PRESETS.keys()),
        index=1,
    )

    if LENGTH_PRESETS[length_preset] is None:
        max_duration_default = 90
        min_duration_default = 10
        last_clip_default = 60
    else:
        max_duration_default, min_duration_default, last_clip_default = LENGTH_PRESETS[length_preset]

    force_download = st.checkbox("Скачать заново, даже если файл уже есть", value=False)
    max_clips = st.number_input("Максимум клипов за прогон", min_value=1, max_value=100, value=12, step=1)
    max_duration = st.number_input("Максимальная длина клипа, сек", min_value=10, max_value=300, value=max_duration_default, step=5)
    min_duration = st.number_input("Минимальная длина клипа, сек", min_value=1, max_value=120, value=min_duration_default, step=1)
    last_clip_duration = st.number_input("Длина последнего клипа, сек", min_value=10, max_value=300, value=last_clip_default, step=5)
    channel_prefix = st.text_input("Префикс заголовка", value="Mr Lizard")
    crf = st.slider("Качество CRF, меньше = лучше/тяжелее", min_value=16, max_value=30, value=21)

    st.divider()
    st.subheader("Stacked 9:16 crop")

    st.caption("Координаты считаются от исходного 16:9 кадра. Для 1920x1080: x слева, y сверху.")

    top_percent = st.slider("Высота верхнего блока, %", min_value=25, max_value=80, value=58, step=1)

    st.markdown("**Верхний блок**")
    top_x = st.number_input("top x", min_value=0, max_value=4000, value=420, step=10)
    top_y = st.number_input("top y", min_value=0, max_value=4000, value=0, step=10)
    top_w = st.number_input("top width", min_value=100, max_value=4000, value=1080, step=10)
    top_h = st.number_input("top height", min_value=100, max_value=4000, value=720, step=10)

    st.markdown("**Нижний блок**")
    bottom_x = st.number_input("bottom x", min_value=0, max_value=4000, value=0, step=10)
    bottom_y = st.number_input("bottom y", min_value=0, max_value=4000, value=520, step=10)
    bottom_w = st.number_input("bottom width", min_value=100, max_value=4000, value=1920, step=10)
    bottom_h = st.number_input("bottom height", min_value=100, max_value=4000, value=560, step=10)

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

            try:
                src_w, src_h = get_video_size(video_path)
                st.write(f"Размер исходника: `{src_w}x{src_h}`")
            except Exception as size_error:
                st.write(f"Размер исходника не определён: {size_error}")

            status.update(label="Видео готово. Режу клипы...", state="running")

            run_output_dir = OUTPUT_DIR / video_path.stem
            rows = []
            progress = st.progress(0)

            for i, clip in enumerate(clips, start=1):
                st.write(f"Режу {i}/{len(clips)}: {seconds_to_stamp(clip.start)} - {clip.title}")

                out = render_clip(
                    video_path,
                    clip,
                    run_output_dir,
                    output_mode=output_mode,
                    crf=int(crf),
                    top_x=int(top_x),
                    top_y=int(top_y),
                    top_w=int(top_w),
                    top_h=int(top_h),
                    bottom_x=int(bottom_x),
                    bottom_y=int(bottom_y),
                    bottom_w=int(bottom_w),
                    bottom_h=int(bottom_h),
                    top_percent=int(top_percent),
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
                        "mode": output_mode,
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
