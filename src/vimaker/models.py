"""Lightweight data carriers passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class VideoMeta:
    path: Path
    duration: float          # seconds
    width: int
    height: int
    fps: float
    has_audio: bool


@dataclass
class Scene:
    start: float             # seconds
    end: float               # seconds
    mid: float               # representative timestamp, seconds
    hist: np.ndarray         # normalized HSV histogram feature
    motion: float = 0.0      # mean frame-to-frame change around mid (single-take videos)

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass
class Moment:
    """A scene chosen for the montage, with its clip window."""

    scene: Scene
    clip_start: float
    clip_end: float
