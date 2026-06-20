# Сборка Vimaker под Windows (установщик со встроенной локальной LLM)

Готовый установщик ставит приложение **и локальный ИИ-сервер (Ollama)**. Модели
(`gemma3:12b`, ~8 ГБ) можно либо вшить в установщик, либо скачать при
первом запуске.

## Важно про платформу
Windows `.exe` нельзя собрать на macOS/Linux. Есть два пути:

### Вариант A — GitHub Actions (рекомендуется, ничего локально не нужно)
1. Запушить репозиторий на GitHub.
2. Вкладка **Actions → Windows Build → Run workflow**.
   - галочка `bake_models` выключена → модели качаются при первом запуске (установщик ~150–300 МБ);
   - включена → модели вшиты внутрь (установщик ~7 ГБ, работает офлайн сразу).
3. Скачать артефакт **Vimaker-Windows-Installer** (`Vimaker-Setup-0.1.0.exe`).

### Вариант B — на машине с Windows
Нужны: Python 3.12 (x64), [Inno Setup 6](https://jrsoftware.org/isdl.php) (чтобы `iscc`
был в PATH).

```powershell
# модели скачиваются при первом запуске:
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

# или вшить модели в установщик (большой, но офлайн):
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -BakeModels
```

Результат: `dist\installer\Vimaker-Setup-0.1.0.exe`.

## Что внутри
- `packaging/vimaker.spec` — конфиг PyInstaller (замораживает приложение + PySide6/Qt).
- `packaging/build_windows.ps1` — качает Ollama для Windows, (опц.) пуллит модели,
  запускает PyInstaller и Inno Setup.
- `packaging/vimaker.iss` — установщик (ярлыки, иконка, RU/EN языки).
- `.github/workflows/windows-build.yml` — сборка в облаке.

## Как это работает у пользователя
1. Запускает `Vimaker-Setup-*.exe`, ставит как обычную программу.
2. При старте приложение само поднимает встроенный `ollama serve` (окно консоли не
   показывается) и, если моделей нет, скачивает их один раз (виден прогресс в статусе).
3. Дальше всё работает локально и офлайн: превью + двуязычные описание и хэштеги.

Логика старта сервера — `src/vimaker/ollama_boot.py` (`bootstrap()`), вызывается из
`MainWindow._bootstrap_ollama()`.

## ffmpeg
Приложение получает ffmpeg/ffprobe через пакет `static-ffmpeg` (скачивает статические
бинарники в кэш пользователя при первом использовании). Интернет нужен только один раз.
