# Vimaker Windows build script.
#
# Produces dist\Vimaker\ (app + bundled Ollama) and dist\installer\Vimaker-Setup-*.exe
#
# Prerequisites on the Windows build machine:
#   - Python 3.12 (x64)
#   - Inno Setup 6 (iscc on PATH)  ->  https://jrsoftware.org/isdl.php
#   - Internet access (to fetch Ollama + optionally pull models)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1            # download models on first run
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -BakeModels # pre-bundle models in the installer
param(
    [switch]$BakeModels = $false
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Creating build venv" -ForegroundColor Cyan
python -m venv .build-venv
$py = ".\.build-venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -e .
& $py -m pip install pyinstaller pillow

Write-Host "==> Ensuring icon.ico" -ForegroundColor Cyan
& $py -c "from PIL import Image; im=Image.open('src/vimaker/gui/assets/icon.png').convert('RGBA'); im.save('src/vimaker/gui/assets/icon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

Write-Host "==> Downloading Ollama for Windows" -ForegroundColor Cyan
$ollamaDir = "packaging\ollama"
New-Item -ItemType Directory -Force -Path $ollamaDir | Out-Null
$zip = "$ollamaDir\ollama-windows-amd64.zip"
if (-not (Test-Path "$ollamaDir\ollama.exe")) {
    Invoke-WebRequest -Uri "https://ollama.com/download/ollama-windows-amd64.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $ollamaDir -Force
    Remove-Item $zip
}

if ($BakeModels) {
    Write-Host "==> Pre-pulling models into the bundle (large!)" -ForegroundColor Cyan
    $env:OLLAMA_MODELS = (Resolve-Path "$ollamaDir").Path + "\models"
    New-Item -ItemType Directory -Force -Path $env:OLLAMA_MODELS | Out-Null
    Start-Process -FilePath "$ollamaDir\ollama.exe" -ArgumentList "serve" -PassThru | Out-Null
    Start-Sleep -Seconds 5
    & "$ollamaDir\ollama.exe" pull gemma3:12b
    Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force
}

Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm packaging\vimaker.spec

Write-Host "==> Copying Ollama into the app folder" -ForegroundColor Cyan
Copy-Item -Recurse -Force $ollamaDir "dist\Vimaker\ollama"

Write-Host "==> Building installer with Inno Setup" -ForegroundColor Cyan
iscc packaging\vimaker.iss

Write-Host "==> Done. Installer in dist\installer\" -ForegroundColor Green
