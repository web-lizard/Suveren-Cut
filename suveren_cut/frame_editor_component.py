from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_COMPONENT_DIR = Path(__file__).resolve().parent / "frame_editor_component"

_frame_editor = components.declare_component(
    "suveren_frame_editor",
    path=str(_COMPONENT_DIR),
)


def frame_editor(
    *,
    image_path: str | Path,
    src_w: int,
    src_h: int,
    crop: dict[str, Any],
    key: str | None = None,
) -> dict[str, Any] | None:
    image_path = Path(image_path)
    raw = image_path.read_bytes()
    image_data = "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")

    return _frame_editor(
        image_data=image_data,
        src_w=int(src_w),
        src_h=int(src_h),
        crop=crop,
        key=key,
        default=None,
    )
