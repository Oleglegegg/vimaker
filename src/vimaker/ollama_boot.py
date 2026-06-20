"""Locate, start, and provision a local Ollama server.

In a packaged build the Ollama binary and (optionally) model blobs are shipped
alongside the app. This module:
  - finds the bundled or system `ollama` executable,
  - starts `ollama serve` if nothing is listening on the host,
  - ensures the required vision/text models are present (pulling on first run).

It is safe to call repeatedly; it no-ops when the server is already up and models
are present.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .config import Settings


def _frozen_base() -> Path | None:
    """Directory of bundled resources when frozen by PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return None


def find_ollama() -> str | None:
    """Return a path to an ollama executable: bundled first, then system PATH."""
    base = _frozen_base()
    candidates: list[Path] = []
    if base is not None:
        candidates += [
            base / "ollama" / "ollama.exe",
            base / "ollama" / "ollama",
            base / "ollama.exe",
        ]
    # alongside the executable (installer layout)
    exe_dir = Path(sys.executable).parent
    candidates += [exe_dir / "ollama" / "ollama.exe", exe_dir / "ollama.exe"]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("ollama")


def _host_parts(settings: Settings) -> tuple[str, int]:
    host = settings.ollama_host.replace("http://", "").replace("https://", "")
    h, _, p = host.partition(":")
    return h or "127.0.0.1", int(p or "11434")


def is_up(settings: Settings) -> bool:
    try:
        urllib.request.urlopen(f"{settings.ollama_host}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def installed_models(settings: Settings) -> set[str]:
    try:
        with urllib.request.urlopen(f"{settings.ollama_host}/api/tags", timeout=5) as r:
            data = json.loads(r.read())
        return {m.get("name", "") for m in data.get("models", [])}
    except Exception:
        return set()


def ensure_server(settings: Settings, progress=None) -> subprocess.Popen | None:
    """Start `ollama serve` if not already up. Returns the process (or None)."""
    if is_up(settings):
        return None
    exe = find_ollama()
    if not exe:
        raise RuntimeError(
            "Ollama не найден. Установите Ollama или используйте сборку со встроенным сервером."
        )
    if progress:
        progress("Запуск локального ИИ-сервера…")

    host, port = _host_parts(settings)
    env = dict(os.environ, OLLAMA_HOST=f"{host}:{port}")
    # bundled models dir, if shipped next to the binary
    base = _frozen_base() or Path(sys.executable).parent
    models_dir = base / "ollama" / "models"
    if models_dir.exists():
        env.setdefault("OLLAMA_MODELS", str(models_dir))

    creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    proc = subprocess.Popen(
        [exe, "serve"], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    # wait until it answers
    for _ in range(60):
        if is_up(settings):
            return proc
        time.sleep(0.5)
    raise RuntimeError("Не удалось запустить Ollama-сервер.")


def ensure_models(settings: Settings, progress=None) -> None:
    """Pull the required models if missing (first-run download)."""
    exe = find_ollama()
    if not exe:
        return
    have = installed_models(settings)
    for model in (settings.ollama_model, settings.ollama_text_model):
        if model and not any(m == model or m.startswith(model + ":") for m in have):
            if progress:
                progress(f"Загрузка модели {model} (один раз, может занять время)…")
            host, port = _host_parts(settings)
            env = dict(os.environ, OLLAMA_HOST=f"{host}:{port}")
            subprocess.run([exe, "pull", model], env=env, check=False)


def bootstrap(settings: Settings, progress=None) -> subprocess.Popen | None:
    """Full first-run provisioning: start server + ensure models."""
    proc = ensure_server(settings, progress=progress)
    ensure_models(settings, progress=progress)
    return proc
