from __future__ import annotations

from pathlib import Path
import traceback

import streamlit as st
from PIL import Image
from streamlit_drawable_canvas import st_canvas

from suveren_cut.downloader import download_youtube
from suveren_cut.metadata import make_description, make_title, write_manifest
from suveren_cut.render import ensure_ffmpeg, extract_frame, get_video_size, render_clip
from suveren_cut.timecodes import build_clips, parse_timecodes, seconds_to_stamp


BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"
WORK_DIR = BASE_DIR / "work"

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}

OUTPUT_MODE_LABELS = {
    "Оригинал 16:9 без кропа": "original_16_9",
    "Shorts 9:16, центр-кроп": "shorts_center_crop",
    "Shorts 9:16, стек: верх + низ": "shorts_stacked",
}

LENGTH_PRESETS = {
    "Shorts standard, 60 сек": (60, 10, 45),
    "Shorts long, 90 сек": (90, 10, 60),
    "Shorts max, 120 сек": (120, 10, 75),
    "Clips, 3 минуты": (180, 20, 120),
    "Custom": None,
}

CROP_DEFAULTS = {
    "top_percent": 58,
    "top_x": 420,
    "top_y": 0,
    "top_w": 1080,
    "top_h": 720,
    "bottom_x": 0,
    "bottom_y": 520,
    "bottom_w": 1920,
    "bottom_h": 560,
}


def init_state() -> None:
    for key, value in CROP_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("preview_video_path", "")
    st.session_state.setdefault("preview_frame_path", "")
    st.session_state.setdefault("preview_src_w", 1920)
    st.session_state.setdefault("preview_src_h", 1080)


def list_downloaded_videos() -> list[Path]:
    if not DOWNLOADS_DIR.exists():
        return []
    items = [
        path
        for path in DOWNLOADS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS
    ]
    return sorted(items, key=lambda p: p.stat().st_mtime, reverse=True)


def video_label(path: Path) -> str:
    try:
        size_mb = path.stat().st_size / 1024 / 1024
        return f"{path.name} | {size_mb:.1f} MB"
    except OSError:
        return path.name


def resolve_video_source(url: str, selected_local_video: Path | None, force_download: bool) -> tuple[Path, dict]:
    if selected_local_video and selected_local_video.exists():
        return selected_local_video, {
            "title": selected_local_video.stem,
            "webpage_url": url.strip(),
            "source": "local",
        }

    if not url.strip():
        raise RuntimeError("Нужно выбрать уже скачанное видео или вставить YouTube-ссылку.")

    return download_youtube(url.strip(), DOWNLOADS_DIR, force=force_download)


def default_preview_second(timecodes_text: str) -> int:
    markers = parse_timecodes(timecodes_text)
    if markers:
        return int(markers[0].start + 5)
    return 30


def canvas_rect_from_crop(x: int, y: int, w: int, h: int, sx: float, sy: float, stroke: str, fill: str) -> dict:
    return {
        "type": "rect",
        "version": "4.4.0",
        "originX": "left",
        "originY": "top",
        "left": int(x / sx),
        "top": int(y / sy),
        "width": int(w / sx),
        "height": int(h / sy),
        "fill": fill,
        "stroke": stroke,
        "strokeWidth": 3,
        "strokeUniform": True,
        "scaleX": 1,
        "scaleY": 1,
        "angle": 0,
        "opacity": 1,
    }


def canvas_initial_drawing(src_w: int, src_h: int, display_w: int, display_h: int) -> dict:
    sx = src_w / display_w
    sy = src_h / display_h

    return {
        "version": "4.4.0",
        "objects": [
            canvas_rect_from_crop(
                st.session_state.top_x,
                st.session_state.top_y,
                st.session_state.top_w,
                st.session_state.top_h,
                sx,
                sy,
                "#00ff88",
                "rgba(0, 255, 136, 0.15)",
            ),
            canvas_rect_from_crop(
                st.session_state.bottom_x,
                st.session_state.bottom_y,
                st.session_state.bottom_w,
                st.session_state.bottom_h,
                sx,
                sy,
                "#ffb000",
                "rgba(255, 176, 0, 0.15)",
            ),
        ],
    }


def rect_to_crop(obj: dict, sx: float, sy: float) -> dict:
    left = float(obj.get("left", 0))
    top = float(obj.get("top", 0))
    width = float(obj.get("width", 0)) * float(obj.get("scaleX", 1))
    height = float(obj.get("height", 0)) * float(obj.get("scaleY", 1))

    return {
        "x": max(0, int(round(left * sx))),
        "y": max(0, int(round(top * sy))),
        "w": max(2, int(round(width * sx))),
        "h": max(2, int(round(height * sy))),
    }


def apply_canvas_layout(canvas_json: dict, src_w: int, src_h: int, display_w: int, display_h: int) -> bool:
    if not canvas_json:
        return False

    objects = canvas_json.get("objects") or []
    rects = [obj for obj in objects if obj.get("type") == "rect"]

    if len(rects) < 2:
        return False

    sx = src_w / display_w
    sy = src_h / display_h

    crops = [rect_to_crop(obj, sx, sy) for obj in rects[:2]]
    crops = sorted(crops, key=lambda item: item["y"])

    top = crops[0]
    bottom = crops[1]

    st.session_state.top_x = top["x"]
    st.session_state.top_y = top["y"]
    st.session_state.top_w = top["w"]
    st.session_state.top_h = top["h"]

    st.session_state.bottom_x = bottom["x"]
    st.session_state.bottom_y = bottom["y"]
    st.session_state.bottom_w = bottom["w"]
    st.session_state.bottom_h = bottom["h"]

    return True


def prepare_preview_frame(
    url: str,
    selected_local_video: Path | None,
    force_download: bool,
    frame_second: float,
) -> None:
    ensure_ffmpeg()

    with st.status("Готовлю preview-кадр...", expanded=True) as status:
        video_path, info = resolve_video_source(url, selected_local_video, force_download)
        st.write(f"Видео: `{video_path}`")

        src_w, src_h = get_video_size(video_path)
        st.write(f"Размер: `{src_w}x{src_h}`")

        frame_path = WORK_DIR / "layout_preview.jpg"
        extract_frame(video_path, frame_path, at_seconds=frame_second)

        st.session_state.preview_video_path = str(video_path)
        st.session_state.preview_frame_path = str(frame_path)
        st.session_state.preview_src_w = src_w
        st.session_state.preview_src_h = src_h

        status.update(label="Preview-кадр готов.", state="complete")


def frame_editor_block(
    url: str,
    selected_local_video: Path | None,
    force_download: bool,
    timecodes_text: str,
) -> None:
    st.subheader("🎛️ Визуальная настройка кадра")
    st.caption("Зелёная рамка = верхний слой. Оранжевая рамка = нижний слой. Двигай и растягивай мышкой.")

    source_hint = "Источник: "
    if selected_local_video:
        source_hint += f"локальный файл `{selected_local_video.name}`"
    elif url.strip():
        source_hint += "YouTube-ссылка, будет скачано при необходимости"
    else:
        source_hint += "выбери локальный файл или вставь YouTube-ссылку"
    st.info(source_hint)

    with st.expander("Тонкая настройка preview", expanded=False):
        frame_second = st.number_input(
            "Секунда кадра",
            min_value=0,
            max_value=99999,
            value=default_preview_second(timecodes_text),
            step=5,
        )
    if "frame_second" not in locals():
        frame_second = default_preview_second(timecodes_text)

    col_prep, col_reset = st.columns([1, 1])
    with col_prep:
        if st.button("Подготовить preview", use_container_width=True):
            prepare_preview_frame(url, selected_local_video, force_download, frame_second)

    with col_reset:
        if st.button("Сбросить crop к дефолту", use_container_width=True):
            for key, value in CROP_DEFAULTS.items():
                st.session_state[key] = value
            st.success("Crop сброшен.")

    frame_path = st.session_state.get("preview_frame_path") or ""
    if not frame_path or not Path(frame_path).exists():
        st.info("Сначала подготовь preview-кадр.")
        return

    src_w = int(st.session_state.preview_src_w)
    src_h = int(st.session_state.preview_src_h)

    image = Image.open(frame_path).convert("RGB")
    display_w = min(960, src_w)
    display_h = round(src_h * display_w / src_w)
    image_display = image.resize((display_w, display_h))

    initial = canvas_initial_drawing(src_w, src_h, display_w, display_h)

    canvas_result = st_canvas(
        fill_color="rgba(0, 255, 136, 0.12)",
        stroke_width=3,
        stroke_color="#00ff88",
        background_image=image_display,
        update_streamlit=True,
        height=display_h,
        width=display_w,
        drawing_mode="transform",
        initial_drawing=initial,
        key="layout_canvas",
    )

    col_apply, col_info = st.columns([1, 2])

    with col_apply:
        if st.button("Применить координаты из рамок", type="primary", use_container_width=True):
            ok = apply_canvas_layout(canvas_result.json_data, src_w, src_h, display_w, display_h)
            if ok:
                st.success("Координаты применены.")
            else:
                st.error("Нужны две прямоугольные рамки.")

    with col_info:
        st.write(
            {
                "top": {
                    "x": st.session_state.top_x,
                    "y": st.session_state.top_y,
                    "w": st.session_state.top_w,
                    "h": st.session_state.top_h,
                },
                "bottom": {
                    "x": st.session_state.bottom_x,
                    "y": st.session_state.bottom_y,
                    "w": st.session_state.bottom_w,
                    "h": st.session_state.bottom_h,
                },
            }
        )


init_state()

st.set_page_config(page_title="Sovereign Cut 2.4", page_icon="🦎", layout="wide")

st.title("🦎 Sovereign Cut 2.4")
st.caption("YouTube-ссылка или локальный скачанный файл -> таймкоды -> нарезки + визуальная настройка кадра.")

downloaded_videos = list_downloaded_videos()
download_labels = ["Не выбрано"] + [video_label(path) for path in downloaded_videos]

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

    force_download = st.checkbox("Скачать заново по ссылке", value=False)
    max_clips = st.number_input("Максимум клипов за прогон", min_value=1, max_value=100, value=12, step=1)
    max_duration = st.number_input("Максимальная длина клипа, сек", min_value=10, max_value=300, value=max_duration_default, step=5)
    min_duration = st.number_input("Минимальная длина клипа, сек", min_value=1, max_value=120, value=min_duration_default, step=1)
    last_clip_duration = st.number_input("Длина последнего клипа, сек", min_value=10, max_value=300, value=last_clip_default, step=5)
    channel_prefix = st.text_input("Префикс заголовка", value="Mr Lizard")
    crf = st.slider("Качество CRF, меньше = лучше/тяжелее", min_value=16, max_value=30, value=21)

    st.divider()
    st.subheader("Stacked 9:16")
    st.session_state.top_percent = st.slider("Высота верхнего блока, %", min_value=25, max_value=80, value=int(st.session_state.top_percent), step=1)

    with st.expander("Точные координаты", expanded=False):
        st.session_state.top_x = st.number_input("top x", min_value=0, max_value=4000, value=int(st.session_state.top_x), step=10)
        st.session_state.top_y = st.number_input("top y", min_value=0, max_value=4000, value=int(st.session_state.top_y), step=10)
        st.session_state.top_w = st.number_input("top width", min_value=100, max_value=4000, value=int(st.session_state.top_w), step=10)
        st.session_state.top_h = st.number_input("top height", min_value=100, max_value=4000, value=int(st.session_state.top_h), step=10)

        st.session_state.bottom_x = st.number_input("bottom x", min_value=0, max_value=4000, value=int(st.session_state.bottom_x), step=10)
        st.session_state.bottom_y = st.number_input("bottom y", min_value=0, max_value=4000, value=int(st.session_state.bottom_y), step=10)
        st.session_state.bottom_w = st.number_input("bottom width", min_value=100, max_value=4000, value=int(st.session_state.bottom_w), step=10)
        st.session_state.bottom_h = st.number_input("bottom height", min_value=100, max_value=4000, value=int(st.session_state.bottom_h), step=10)

url = st.text_input("YouTube-ссылка на стрим", placeholder="https://www.youtube.com/watch?v=...")

selected_index = st.selectbox(
    "Уже скачанное видео из downloads/",
    options=list(range(len(download_labels))),
    format_func=lambda idx: download_labels[idx],
    index=0,
)

selected_local_video = None
if selected_index > 0:
    selected_local_video = downloaded_videos[selected_index - 1]
    st.success(f"Будет использован локальный файл: {selected_local_video.name}")
elif downloaded_videos:
    st.caption(f"В downloads/ найдено видео: {len(downloaded_videos)}. Можно выбрать файл и не качать заново.")

timecodes = st.text_area(
    "Таймкоды",
    height=260,
    placeholder="00:00:00 🦎 Старт рептилоидной радиостанции\n00:04:39 🐊 Слава Лизардии\n00:12:30 🔥 Суверенитет выше магии",
)

editor_available = hasattr(st, "dialog")

if editor_available:
    @st.dialog("🎛️ Настройка кадра")
    def frame_editor_dialog() -> None:
        frame_editor_block(url, selected_local_video, force_download, timecodes)

    if st.button("🎛️ Открыть визуальный редактор кадра", use_container_width=True):
        frame_editor_dialog()
else:
    with st.expander("🎛️ Визуальный редактор кадра", expanded=False):
        frame_editor_block(url, selected_local_video, force_download, timecodes)

col_a, col_b = st.columns([1, 1])

with col_a:
    preview_clicked = st.button("1. Проверить таймкоды", use_container_width=True)

with col_b:
    run_clicked = st.button("2. Нарезать", type="primary", use_container_width=True)

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

        with st.status("Готовлю видео...", expanded=True) as status:
            video_path, info = resolve_video_source(url, selected_local_video, force_download)
            source_title = str(info.get("title") or video_path.stem)
            source_url = str(info.get("webpage_url") or url.strip())

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
                    top_x=int(st.session_state.top_x),
                    top_y=int(st.session_state.top_y),
                    top_w=int(st.session_state.top_w),
                    top_h=int(st.session_state.top_h),
                    bottom_x=int(st.session_state.bottom_x),
                    bottom_y=int(st.session_state.bottom_y),
                    bottom_w=int(st.session_state.bottom_w),
                    bottom_h=int(st.session_state.bottom_h),
                    top_percent=int(st.session_state.top_percent),
                )

                rows.append(
                    {
                        "file": str(out),
                        "title": make_title(clip, channel_prefix=channel_prefix),
                        "description": make_description(clip, source_title=source_title, source_url=source_url),
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
