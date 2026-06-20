# PyInstaller spec for Vimaker (Windows desktop build).
#
# Produces a one-folder app (dist/Vimaker/) including:
#   - the frozen Python app + PySide6 (Qt6 + multimedia),
#   - static ffmpeg/ffprobe (resolved at runtime by static_ffmpeg, or bundle yourself),
#   - the bundled Ollama server + (optionally) pre-pulled model blobs, placed under
#     dist/Vimaker/ollama/ by the build script (see packaging/build_windows.ps1).
#
# Build on Windows:  pyinstaller packaging/vimaker.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

datas = [("../src/vimaker/gui/assets", "vimaker/gui/assets")]
# scenedetect / cv2 ship data; pull anything needed
hiddenimports = collect_submodules("scenedetect")

a = Analysis(
    ["../src/vimaker/gui_main.py"],
    pathex=["../src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports + ["vimaker.gui.app"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Vimaker",
    debug=False,
    strip=False,
    upx=False,
    console=False,                       # GUI app: no console window
    icon="../src/vimaker/gui/assets/icon.ico",
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="Vimaker",
)
