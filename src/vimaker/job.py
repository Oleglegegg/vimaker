"""Per-video Job state and composable pipeline steps.

A Job carries everything computed for one video so the GUI can:
  - run the full pipeline once (build_preview_step + metadata steps),
  - regenerate just the preview (new variation), the description, or the hashtags,
without recomputing the expensive vision facts unless needed.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .config import Settings, load_settings
from .ffmpeg import ffprobe_meta
from .keyframes import extract_keyframes
from .metadata import (
    extract_facts, generate_description, generate_hashtags, is_available,
)
from .models import Moment, Scene, VideoMeta
from .preview import build_preview
from .scenes import detect_scenes
from .select import select_moments


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    video: Path
    status: JobStatus = JobStatus.PENDING
    error: str = ""

    # computed pipeline state
    out_dir: Path | None = None
    meta: VideoMeta | None = None
    scenes: list[Scene] = field(default_factory=list)
    motion_mode: bool = False
    keyframes: list[Path] = field(default_factory=list)
    facts: str = ""
    preview_path: Path | None = None
    variation: int = 0

    # outputs
    description_ru: str = ""
    description_en: str = ""
    hashtags_ru: list[str] = field(default_factory=list)
    hashtags_en: list[str] = field(default_factory=list)

    # prompts used (from active preset; can be overridden per regen)
    desc_prompt: str = ""
    tags_prompt: str = ""

    # per-video montage settings (None -> use the global default from Settings)
    target_len: float | None = None    # preview length, seconds
    num_clips: int | None = None       # number of scenes/moments
    keep_audio: bool = True            # include audio in the montage

    # per-video text/hashtag settings (None -> use the global default from Settings)
    hashtag_count: int | None = None   # how many hashtags
    hashtag_words: int | None = None   # max words per hashtag
    desc_words: int | None = None      # target description length (words)
    desc_words_tol: int | None = None  # +/- tolerance

    @property
    def name(self) -> str:
        return self.video.name

    def cleanup(self) -> None:
        """Remove this job's temp output directory (preview + keyframes)."""
        if self.out_dir is not None:
            import shutil
            shutil.rmtree(self.out_dir, ignore_errors=True)
            self.out_dir = None


def _job_settings(job: Job, settings: Settings) -> Settings:
    """Apply this job's per-video overrides on top of the global settings."""
    overrides: dict = {"keep_audio": job.keep_audio}
    for field_name in ("target_len", "num_clips", "hashtag_count", "hashtag_words",
                       "desc_words", "desc_words_tol"):
        val = getattr(job, field_name)
        if val is not None:
            overrides[field_name] = val
    return settings.model_copy(update=overrides)


def _ensure_out(job: Job) -> Path:
    if job.out_dir is None:
        job.out_dir = Path(tempfile.mkdtemp(prefix="vimaker_"))
    return job.out_dir


def analyze(job: Job, settings: Settings, progress=None) -> None:
    """Probe + scene/moment detection + preview + keyframes + vision facts."""
    settings = _job_settings(job, settings)
    # re-analysis (e.g. retry of a failed job): start from a clean temp dir
    job.cleanup()
    job.variation = 0
    job.facts = ""
    out_dir = _ensure_out(job)

    def step(m: str) -> None:
        if progress:
            progress(m)

    step("Анализ видео")
    job.meta = ffprobe_meta(job.video)

    step("Поиск сцен и моментов")
    job.scenes, job.motion_mode = detect_scenes(job.meta, settings)

    build_preview_step(job, settings, progress=progress)

    step("Извлечение кадров")
    moments = _current_moments(job, settings)
    job.keyframes = extract_keyframes(job.meta, moments, settings, out_dir)

    if settings.use_ollama and is_available(settings):
        step("Распознавание содержимого (vision)")
        job.facts = extract_facts(job.keyframes, settings)


def _current_moments(job: Job, settings: Settings) -> list[Moment]:
    return select_moments(
        job.scenes, job.meta, settings,
        motion_mode=job.motion_mode, variation=job.variation,
    )


def build_preview_step(job: Job, settings: Settings, progress=None) -> Path:
    """(Re)build only the preview montage for the job's current variation.

    Each build writes a uniquely-named file (preview_<variation>.mp4) so a media
    player still holding the previous file can't block the overwrite, and stale
    previews are removed to keep the temp dir small.
    """
    if progress:
        progress("Сборка превью")
    settings = _job_settings(job, settings)
    out_dir = _ensure_out(job)
    moments = _current_moments(job, settings)
    name = f"preview_{job.variation}.mp4"
    new_path = build_preview(job.meta, moments, settings, out_dir, name=name)
    # remove the previous preview file (different name) to avoid temp-dir buildup
    if job.preview_path and job.preview_path != new_path and job.preview_path.exists():
        try:
            job.preview_path.unlink()
        except OSError:
            pass
    job.preview_path = new_path
    return job.preview_path


def regenerate_preview(job: Job, settings: Settings, progress=None) -> Path:
    """Pick a different selection and rebuild the preview."""
    job.variation += 1
    path = build_preview_step(job, settings, progress=progress)
    # keyframes follow the new moments so re-described metadata matches the preview
    js = _job_settings(job, settings)
    job.keyframes = extract_keyframes(job.meta, _current_moments(job, js), js, _ensure_out(job))
    return path


def _ensure_facts(job: Job, settings: Settings) -> None:
    """Make sure we have vision facts; refuse if the video wasn't analyzed yet."""
    if job.facts:
        return
    if not job.keyframes:
        raise RuntimeError("Видео ещё не проанализировано — сначала запустите обработку.")
    job.facts = extract_facts(job.keyframes, settings)


def regenerate_description(job: Job, settings: Settings, progress=None) -> tuple[str, str]:
    if progress:
        progress("Генерация описания")
    js = _job_settings(job, settings)
    _ensure_facts(job, js)
    ru, en = generate_description(
        job.facts, js, desc_prompt=job.desc_prompt,
        duration=job.meta.duration if job.meta else 0.0,
    )
    job.description_ru, job.description_en = ru, en
    return ru, en


def regenerate_hashtags(job: Job, settings: Settings, progress=None) -> tuple[list[str], list[str]]:
    if progress:
        progress("Генерация хэштегов")
    js = _job_settings(job, settings)
    _ensure_facts(job, js)
    ru, en = generate_hashtags(job.facts, js, tags_prompt=job.tags_prompt)
    job.hashtags_ru, job.hashtags_en = ru, en
    return ru, en


def _with_retry(fn, attempts: int = 2):
    """Run a text-generation step, retrying once on empty/garbled model output."""
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as exc:  # malformed/empty JSON -> retry once
            last = exc
    if last:
        raise last


def run_full(job: Job, settings: Settings | None = None, progress=None) -> Job:
    """Full pipeline for one job: analyze (incl. preview) + description + hashtags.

    The preview is the expensive, deterministic artifact; if only the LLM text steps
    fail, we keep the preview and still mark the job DONE (with an error note) rather
    than discarding everything.
    """
    settings = settings or load_settings()
    try:
        job.status = JobStatus.RUNNING
        analyze(job, settings, progress=progress)
        if job.facts:
            try:
                _with_retry(lambda: regenerate_description(job, settings, progress=progress))
                _with_retry(lambda: regenerate_hashtags(job, settings, progress=progress))
            except Exception as exc:
                job.error = f"Текст не сгенерирован: {exc}"
        job.status = JobStatus.DONE
    except Exception as exc:
        import traceback
        job.status = JobStatus.FAILED
        job.error = f"{exc}\n\n{traceback.format_exc()}"
    return job
