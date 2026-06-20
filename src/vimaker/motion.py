"""Motion analysis for single-take / static-camera videos.

When PySceneDetect finds no real cuts (one continuous shot), color histograms are
nearly identical and useless for picking "different moments". Instead we sample
frames densely and measure motion energy (mean abs-diff between consecutive
downscaled grayscale frames). Peaks in motion = the moments where something
actually changes (pose / action), which is exactly what the montage should show.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .ffmpeg import hsv_hist
from .models import Scene


def motion_scenes(
    video: Path, duration: float, sample_fps: float, clip_len: float,
    max_samples: int = 200,
) -> list[Scene]:
    """Densely sample the video and return candidate Scenes scored by motion.

    Each candidate is a `clip_len`-wide window centered on a sample point; its
    `motion` field holds the mean frame-to-frame change around that point.

    To stay fast and bounded on LONG videos, the total number of samples is capped
    at `max_samples`: the step grows with duration so a 1-minute and a 2-hour clip
    both cost roughly the same. We only need the strongest motion peaks, so coarser
    sampling on long videos doesn't hurt moment selection.
    """
    cap = cv2.VideoCapture(str(video))
    candidates: list[Scene] = []
    try:
        step = max(0.2, 1.0 / max(0.1, sample_fps))
        if duration / step > max_samples:        # long video -> widen the step
            step = duration / max_samples
        prev_small = None
        t = 0.0
        while t < duration:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                t += step
                continue
            small = cv2.cvtColor(
                cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA),
                cv2.COLOR_BGR2GRAY,
            )
            motion = 0.0
            if prev_small is not None:
                motion = float(np.mean(cv2.absdiff(small, prev_small)))
            prev_small = small

            half = clip_len / 2.0
            start = max(0.0, t - half)
            end = min(duration, t + half)
            candidates.append(
                Scene(start=start, end=end, mid=t, hist=hsv_hist(frame), motion=motion)
            )
            t += step
    finally:
        cap.release()

    # First sample has no predecessor -> give it the median motion so it isn't
    # artificially favored or penalized.
    if len(candidates) > 1:
        med = float(np.median([c.motion for c in candidates[1:]]))
        candidates[0].motion = med
    return candidates
