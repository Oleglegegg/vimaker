"""Thin wrappers around ffmpeg / ffprobe and OpenCV frame grabbing.

ffmpeg/ffprobe are resolved in this order:
  1. binaries already on PATH (e.g. a system/brew install),
  2. the `static-ffmpeg` package, which fetches static binaries into the env.
This keeps the project self-contained — no brew / system install required.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

from .models import VideoMeta

_FFMPEG: str | None = None
_FFPROBE: str | None = None


def _resolve() -> tuple[str, str]:
    """Return (ffmpeg, ffprobe) absolute paths, fetching them if needed."""
    global _FFMPEG, _FFPROBE
    if _FFMPEG and _FFPROBE:
        return _FFMPEG, _FFPROBE

    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ff and fp:
        _FFMPEG, _FFPROBE = ff, fp
        return _FFMPEG, _FFPROBE

    try:
        from static_ffmpeg import run as _sff

        _FFMPEG, _FFPROBE = _sff.get_or_fetch_platform_executables_else_raise()
        return _FFMPEG, _FFPROBE
    except Exception as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "ffmpeg/ffprobe not found on PATH and static-ffmpeg fetch failed "
            f"({exc}). Install ffmpeg or `uv add static-ffmpeg`."
        ) from exc


def ffprobe_meta(video: Path) -> VideoMeta:
    """Read duration / resolution / fps / audio presence via ffprobe."""
    _, ffprobe = _resolve()
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-show_entries", "stream=codec_type,width,height,avg_frame_rate,r_frame_rate",
        "-of", "json", str(video),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    data = json.loads(out)

    duration = float(data.get("format", {}).get("duration", 0.0) or 0.0)
    width = height = 0
    fps = 0.0
    has_audio = False
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and width == 0:
            width = int(stream.get("width", 0) or 0)
            height = int(stream.get("height", 0) or 0)
            fps = _parse_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
        elif stream.get("codec_type") == "audio":
            has_audio = True

    if duration <= 0:
        raise RuntimeError(f"Could not read a valid duration from {video}")
    return VideoMeta(
        path=video, duration=duration, width=width, height=height,
        fps=fps or 30.0, has_audio=has_audio,
    )


def _parse_rate(rate: str | None) -> float:
    if not rate or "/" not in rate:
        return 0.0
    num, den = rate.split("/", 1)
    try:
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    except ValueError:
        return 0.0


def grab_frame(video: Path, t: float) -> np.ndarray | None:
    """Grab a single BGR frame near timestamp `t` (seconds) using OpenCV."""
    cap = cv2.VideoCapture(str(video))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def hsv_hist(frame: np.ndarray, bins: tuple[int, int, int] = (8, 8, 4)) -> np.ndarray:
    """Normalized HSV color histogram, flattened — a cheap deterministic feature."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, list(bins), [0, 180, 0, 256, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    return hist.astype(np.float32)


def run_ffmpeg(args: list[str]) -> None:
    """Run an ffmpeg command, raising with stderr on failure."""
    ffmpeg, _ = _resolve()
    proc = subprocess.run([ffmpeg, "-y", "-loglevel", "error", *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(args)}\n{proc.stderr}")


def ffmpeg_bin() -> str:
    """Absolute path to the resolved ffmpeg binary (for sample generation, etc.)."""
    return _resolve()[0]
