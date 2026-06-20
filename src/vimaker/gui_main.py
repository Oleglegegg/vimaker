"""Windowed entry point for packaged builds (PyInstaller targets this).

Launches the desktop GUI directly, with no CLI/argument parsing, so double-clicking
the installed app opens the studio window.
"""

from __future__ import annotations


def main() -> None:
    from .gui.app import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
