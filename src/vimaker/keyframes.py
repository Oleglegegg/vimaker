"""Extract downscaled keyframes to feed the local vision model."""

from __future__ import annotations

from pathlib import Path

import cv2

from .config import Settings
from .ffmpeg import grab_frame
from .models import Moment, VideoMeta


def extract_keyframes(
    meta: VideoMeta, moments: list[Moment], settings: Settings, out_dir: Path
) -> list[Path]:
    """Save up to keyframe_max downscaled JPEGs for analysis.

    Uses the montage moments plus first/last frame, then tops up with evenly-spaced
    samples across the whole video so the vision model sees more of the content
    (independent of how many scenes the preview has).
    """
    frames_dir = out_dir / "keyframes"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # adapt frame count to video length: ~1 frame per keyframe_secs, clamped
    by_length = round(meta.duration / max(1.0, settings.keyframe_secs))
    cap = max(settings.keyframe_min, min(settings.keyframe_max, by_length))

    timestamps = [0.5] + [m.scene.mid for m in moments] + [max(0.0, meta.duration - 0.5)]
    # top up with a uniform grid across the timeline to reach keyframe_max
    if meta.duration > 1.0:
        grid = [meta.duration * (i + 0.5) / cap for i in range(cap)]
        timestamps += grid

    # de-dupe close timestamps (>1s apart), keep chronological order, cap count
    picked: list[float] = []
    for t in sorted(timestamps):
        if all(abs(t - p) > 1.0 for p in picked):
            picked.append(t)
    picked = picked[:cap]

    paths: list[Path] = []
    for i, t in enumerate(picked):
        frame = grab_frame(meta.path, t)
        if frame is None:
            continue
        frame = _downscale(frame, settings.keyframe_size)
        path = frames_dir / f"kf_{i:02d}.jpg"
        cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        paths.append(path)
    return paths


def _downscale(frame, longest: int):
    h, w = frame.shape[:2]
    scale = longest / max(h, w)
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return frame
