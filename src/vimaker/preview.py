"""Render the preview montage: cut each moment, normalize, concat with ffmpeg."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .config import Settings
from .ffmpeg import run_ffmpeg
from .models import Moment, VideoMeta


def build_preview(
    meta: VideoMeta,
    moments: list[Moment],
    settings: Settings,
    out_dir: Path,
    name: str = "preview.mp4",
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_path = out_dir / name

    if not moments:
        raise RuntimeError("No moments selected; cannot build a preview.")

    use_audio = settings.keep_audio and meta.has_audio
    height = settings.montage_height
    fps = settings.montage_fps

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        clip_paths: list[Path] = []
        for i, m in enumerate(moments):
            clip_path = tmp_dir / f"clip_{i:02d}.mp4"
            _cut_normalized(meta.path, m, clip_path, height, fps, use_audio)
            clip_paths.append(clip_path)

        # All clips share identical codec/params -> concat demuxer with stream copy.
        list_file = tmp_dir / "list.txt"
        list_file.write_text("".join(f"file '{p}'\n" for p in clip_paths))
        run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", "-movflags", "+faststart", str(preview_path),
        ])

    return preview_path


def _cut_normalized(
    src: Path, m: Moment, dst: Path, height: int, fps: int, use_audio: bool
) -> None:
    duration = max(0.4, m.clip_end - m.clip_start)
    # scale to even width at target height; force sar/fps/pix_fmt so all clips match.
    vf = f"scale=-2:{height}:flags=bicubic,fps={fps},setsar=1,format=yuv420p"
    args = [
        "-ss", f"{m.clip_start:.3f}", "-i", str(src), "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-video_track_timescale", "90000",
    ]
    if use_audio:
        args += ["-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k"]
    else:
        args += ["-an"]
    args.append(str(dst))
    run_ffmpeg(args)
