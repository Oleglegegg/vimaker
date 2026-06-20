"""Scene detection (PySceneDetect) with a uniform-sampling fallback.

Each scene gets a representative HSV histogram so downstream selection can pick
visually diverse moments without any ML model.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from .config import Settings
from .ffmpeg import grab_frame, hsv_hist
from .models import Scene, VideoMeta
from .motion import motion_scenes

console = Console(stderr=True)


def detect_scenes(meta: VideoMeta, settings: Settings) -> tuple[list[Scene], bool]:
    """Return (scenes, motion_mode).

    With enough real cuts, scenes are color-keyed for diversity selection. For a
    single continuous take (too few cuts), fall back to dense motion sampling so we
    can pick the most dynamic moments instead of arbitrary uniform points.
    """
    raw = _pyscenedetect(meta.path, settings.scene_threshold)

    if len(raw) < settings.min_scenes_for_detect:
        console.log(
            f"[yellow]Only {len(raw)} scene cut(s) detected; "
            f"switching to motion-based sampling (single-take video).[/]"
        )
        scenes = motion_scenes(
            meta.path, meta.duration, settings.motion_sample_fps, settings.clip_len
        )
        return scenes, True

    scenes: list[Scene] = []
    for start, end in raw:
        mid = (start + end) / 2.0
        frame = grab_frame(meta.path, mid)
        if frame is None:
            continue
        scenes.append(Scene(start=start, end=end, mid=mid, hist=hsv_hist(frame)))
    return scenes, False


def _pyscenedetect(video: Path, threshold: float) -> list[tuple[float, float]]:
    try:
        from scenedetect import ContentDetector, detect
    except Exception as exc:  # pragma: no cover - import guard
        console.log(f"[yellow]PySceneDetect unavailable ({exc}); using uniform sampling.[/]")
        return []
    try:
        scene_list = detect(str(video), ContentDetector(threshold=threshold))
    except Exception as exc:  # pragma: no cover - decode issues
        console.log(f"[yellow]Scene detection failed ({exc}); using uniform sampling.[/]")
        return []
    return [(s.get_seconds(), e.get_seconds()) for s, e in scene_list]
