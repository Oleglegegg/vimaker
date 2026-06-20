"""Pick N moments spread over time, showing how the video changed.

Two modes, chosen upstream:
- multi-scene: in each temporal bucket take the scene whose color histogram is most
  different (greedy max-min) from those already chosen -> visual variety.
- motion mode (single continuous take): in each temporal bucket take the moment with
  the highest motion energy -> the most dynamic moments instead of arbitrary points.
Both split the timeline into N equal buckets so the montage always covers the whole
clip start-to-finish.
"""

from __future__ import annotations

import numpy as np

from .config import Settings
from .models import Moment, Scene, VideoMeta


def select_moments(
    scenes: list[Scene], meta: VideoMeta, settings: Settings,
    motion_mode: bool = False, variation: int = 0,
) -> list[Moment]:
    """Pick montage moments. `variation` > 0 yields a different-but-valid selection
    (for the GUI "regenerate preview" button): in motion mode it takes the Nth-ranked
    motion peak per bucket instead of the top one; in scene mode it shifts the seed."""
    if not scenes:
        return []

    n = min(settings.num_clips, len(scenes))
    duration = meta.duration
    bucket_edges = np.linspace(0.0, duration, n + 1)

    chosen: list[Scene] = []
    for i in range(n):
        lo, hi = bucket_edges[i], bucket_edges[i + 1]
        candidates = [s for s in scenes if lo <= s.mid < hi] or _nearest(scenes, (lo + hi) / 2)
        if motion_mode:
            ranked = sorted(candidates, key=lambda s: s.motion, reverse=True)
            pick = ranked[variation % len(ranked)]
        else:
            pick = _most_diverse(candidates, chosen, skip=variation)
        if pick is not None and pick not in chosen:
            chosen.append(pick)

    # Backfill: empty/duplicate buckets can leave us short of the requested count.
    # Honor "scenes in preview" by topping up from the most distinct unused scenes.
    if len(chosen) < n:
        remaining = [s for s in scenes if s not in chosen]
        remaining.sort(key=lambda s: s.mid)
        for s in remaining:
            if len(chosen) >= n:
                break
            chosen.append(s)

    chosen.sort(key=lambda s: s.mid)
    return [_to_moment(s, settings) for s in chosen]


def _nearest(scenes: list[Scene], t: float) -> list[Scene]:
    return [min(scenes, key=lambda s: abs(s.mid - t))]


def _most_diverse(candidates: list[Scene], chosen: list[Scene], skip: int = 0) -> Scene | None:
    if not candidates:
        return None
    if not chosen:
        # Seed each empty bucket with its middle-most candidate (offset by variation).
        return candidates[(len(candidates) // 2 + skip) % len(candidates)]
    chosen_hists = np.stack([c.hist for c in chosen])
    # Rank candidates by max-min distance; `skip` picks a lower-ranked alternative.
    scored = sorted(
        candidates,
        key=lambda c: float(np.linalg.norm(chosen_hists - c.hist, axis=1).min()),
        reverse=True,
    )
    return scored[skip % len(scored)]


def _to_moment(scene: Scene, settings: Settings) -> Moment:
    """Center a clip_len window on the scene, clamped inside the scene bounds."""
    clip_len = min(settings.clip_len, max(0.4, scene.length))
    start = scene.mid - clip_len / 2.0
    start = max(scene.start, start)
    end = min(scene.end, start + clip_len)
    start = max(scene.start, end - clip_len)
    return Moment(scene=scene, clip_start=max(0.0, start), clip_end=end)
