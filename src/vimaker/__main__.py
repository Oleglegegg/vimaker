"""Typer CLI: `vimaker run <video> [--out DIR]` and `vimaker gui`.

The desktop GUI (`vimaker-gui` / `vimaker gui`) is the primary interface; this CLI
shares the same Job pipeline for headless/testing use.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from .config import load_settings
from .ffmpeg import ffprobe_meta
from .job import Job, run_full

app = typer.Typer(add_completion=False, help="Video -> preview + description + hashtags.")
console = Console()


@app.command()
def run(
    video: Path = typer.Argument(..., exists=True, dir_okay=False, help="Local video file."),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="Output directory."),
) -> None:
    """Build the preview montage and generate bilingual description + hashtags."""
    job = Job(video=video)
    run_full(job, progress=lambda m: console.log(m))
    if job.status.value == "failed":
        console.print(f"[red]Failed:[/] {job.error}")
        raise typer.Exit(1)

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if job.preview_path and job.preview_path.exists():
        import shutil
        dest = out / "preview.mp4"
        shutil.copyfile(job.preview_path, dest)
    payload = {
        "description_ru": job.description_ru,
        "description_en": job.description_en,
        "hashtags_ru": job.hashtags_ru,
        "hashtags_en": job.hashtags_en,
    }
    (out / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    job.cleanup()

    console.rule("[bold green]Done")
    console.print(f"[bold]Preview:[/] {out / 'preview.mp4'}")
    console.rule("Описание (RU)")
    console.print(job.description_ru or "[dim](пусто)[/]")
    console.print(f"\n[bold]Хэштеги:[/] {' '.join(job.hashtags_ru)}")
    console.print(f"\n[dim]result.json -> {out / 'result.json'}[/]")


@app.command()
def gui() -> None:
    """Launch the desktop application."""
    from .gui.app import main
    main()


@app.command()
def probe(video: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Print ffprobe metadata for a video (debug helper)."""
    console.print(ffprobe_meta(video))


@app.command("check")
def check() -> None:
    """Report environment readiness (ffmpeg, Ollama)."""
    import urllib.request

    from .ffmpeg import _resolve

    settings = load_settings()
    try:
        ffmpeg, ffprobe = _resolve()
        console.print(f"ffmpeg:    {ffmpeg}")
        console.print(f"ffprobe:   {ffprobe}")
    except Exception as exc:
        console.print(f"ffmpeg:    [red]unavailable ({exc})[/]")
    try:
        urllib.request.urlopen(f"{settings.ollama_host}/api/tags", timeout=2)
        console.print(f"Ollama:    [green]running[/] ({settings.ollama_host})")
        console.print(f"  models:  vision={settings.ollama_model}, text={settings.ollama_text_model}")
    except Exception:
        console.print(f"Ollama:    [red]not reachable[/] at {settings.ollama_host}")


if __name__ == "__main__":
    app()
