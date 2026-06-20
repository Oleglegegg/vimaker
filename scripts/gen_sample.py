"""Generate a synthetic multi-scene test video at samples/sample.mp4.

Seven visually distinct 4s segments (each with a tone) -> clear scene cuts for
verifying scene detection + diverse-moment selection. Uses the same ffmpeg the
pipeline uses (static-ffmpeg or PATH).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vimaker.ffmpeg import ffmpeg_bin  # noqa: E402

PATTERNS = [
    "testsrc2=s=640x360:r=30",
    "smptebars=s=640x360:r=30",
    "color=c=navy:s=640x360:r=30",
    "mandelbrot=s=640x360:r=30",
    "color=c=darkgreen:s=640x360:r=30",
    "rgbtestsrc=s=640x360:r=30",
    "color=c=maroon:s=640x360:r=30",
]
FREQS = [300, 400, 500, 600, 700, 800, 900]


def main() -> None:
    ff = ffmpeg_bin()
    out = ROOT / "samples" / "sample.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        print(f"sample already exists: {out}")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        segs = []
        for i, (pat, freq) in enumerate(zip(PATTERNS, FREQS)):
            seg = tmp_dir / f"seg_{i}.mp4"
            subprocess.run([
                ff, "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", pat,
                "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=4",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-t", "4",
                "-c:a", "aac", "-ar", "48000", "-ac", "2", str(seg),
            ], check=True)
            segs.append(seg)
        listf = tmp_dir / "list.txt"
        listf.write_text("".join(f"file '{s}'\n" for s in segs))
        subprocess.run([
            ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(listf), "-c", "copy", str(out),
        ], check=True)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
