"""Vimaker desktop app (PySide6) — modern dark UI.

Workflow:
  - Add one or many videos -> they queue and process sequentially.
  - Switch between videos in the list to view each result.
  - Per field: copy, and regenerate (preview / description / hashtags) independently.
  - Prompt presets (RU) selectable up top; managed in the Presets tab.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)

from ..config import load_settings
from ..job import (
    Job, JobStatus, regenerate_description, regenerate_hashtags, regenerate_preview,
)
from ..prefs import Preset, Prefs, load_prefs, save_prefs
from .theme import QSS
from .worker import QueueWorker, TaskWorker, run_on_thread

APP_NAME = "Vimaker"
ASSETS = Path(__file__).resolve().parent / "assets"


def app_icon() -> QIcon:
    icon = QIcon()
    for px in (16, 32, 64, 128, 256, 512):
        p = ASSETS / f"icon_{px}.png"
        if p.exists():
            icon.addFile(str(p))
    return icon


_STATUS_ICON = {
    JobStatus.PENDING: "•",
    JobStatus.RUNNING: "⏳",
    JobStatus.DONE: "✅",
    JobStatus.FAILED: "❌",
}


def _card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName("H2")
        lay.addWidget(lbl)
    return frame, lay


class FieldBox(QWidget):
    """A labeled text field with Copy + Regenerate buttons."""

    def __init__(self, title: str, on_regen, small: bool = False) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        header = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setObjectName("H2")
        header.addWidget(lbl)
        header.addStretch(1)
        self.copy_btn = QPushButton("📋 Копировать")
        self.copy_btn.setObjectName("Mini")
        self.copy_btn.clicked.connect(self._copy)
        self.regen_btn = QPushButton("↻ Перегенерировать")
        self.regen_btn.setObjectName("Mini")
        self.regen_btn.clicked.connect(on_regen)
        header.addWidget(self.regen_btn)
        header.addWidget(self.copy_btn)
        lay.addLayout(header)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("—")
        self.edit.setFixedHeight(64 if small else 96)
        lay.addWidget(self.edit)

    def text(self) -> str:
        return self.edit.toPlainText()

    def set_text(self, t: str) -> None:
        self.edit.setPlainText(t)

    def set_busy(self, busy: bool) -> None:
        self.regen_btn.setEnabled(not busy)
        self.regen_btn.setText("⏳…" if busy else "↻ Перегенерировать")

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text())


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


class DropListWidget(QListWidget):
    """Job list that also accepts drag-and-dropped video files."""

    files_dropped = Signal(list)  # list[str] of paths

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self._hint = "Перетащите видео сюда\nили нажмите «＋ Добавить видео»"

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.count() == 0:
            from PySide6.QtGui import QColor, QPainter
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#7a7a92"))
            painter.drawText(self.viewport().rect(),
                             Qt.AlignmentFlag.AlignCenter, self._hint)
            painter.end()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls:
            super().dropEvent(event)
            return
        paths: list[str] = []
        for url in urls:
            p = Path(url.toLocalFile())
            if p.is_dir():
                paths += [str(f) for f in sorted(p.iterdir())
                          if f.suffix.lower() in VIDEO_EXTS]
            elif p.suffix.lower() in VIDEO_EXTS:
                paths.append(str(p))
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1240, 800)
        self.settings = load_settings()
        self.prefs: Prefs = load_prefs()
        self.jobs: list[Job] = []
        self.current: int = -1
        self._queue_worker: QueueWorker | None = None
        self._queue_running = False
        self._ollama_proc = None

        tabs = QTabWidget()
        tabs.addTab(self._build_main_tab(), "Студия")
        tabs.addTab(self._build_presets_tab(), "Пресеты промптов")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.addWidget(tabs)

        self._bootstrap_ollama()

    def _bootstrap_ollama(self) -> None:
        """Start the local AI server (bundled in packaged builds) off the UI thread."""
        from ..ollama_boot import bootstrap

        self.status.setText("Подготовка локального ИИ…")

        def task(progress):
            return bootstrap(self.settings, progress=progress)

        def done(proc):
            self._ollama_proc = proc
            self.status.setText("✅ Готов к работе")

        def _silent_fail(_msg):  # don't block the app if Ollama isn't available
            self.status.setText("⚠ ИИ-сервер недоступен — тексты не будут сгенерированы")

        worker = TaskWorker(task)
        worker.progress.connect(lambda m: self.status.setText(f"⏳ {m}"))
        worker.done.connect(done)
        worker.failed.connect(_silent_fail)
        run_on_thread(self, worker)

    # ============================================================== main tab
    def _build_main_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(10)

        # top bar: logo + name + preset selector + status
        top = QHBoxLayout()
        logo = QLabel()
        logo_px = ASSETS / "icon_64.png"
        if logo_px.exists():
            logo.setPixmap(QPixmap(str(logo_px)).scaled(
                32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        top.addWidget(logo)
        title = QLabel(APP_NAME)
        title.setObjectName("H1")
        top.addWidget(title)
        top.addSpacing(16)
        top.addWidget(QLabel("Пресет:"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(190)
        self.preset_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._reload_preset_combo()
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        top.addWidget(self.preset_combo)
        top.addSpacing(12)
        self.no_audio_check = QCheckBox("Без аудио")
        self.no_audio_check.setToolTip("Генерировать превью без звуковой дорожки")
        top.addWidget(self.no_audio_check)
        top.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("Status")
        top.addWidget(self.status)
        outer.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)

        # --- left: queue ---
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("＋ Добавить видео")
        add_btn.setObjectName("Primary")
        add_btn.setToolTip("Можно выбрать несколько файлов сразу, "
                           "либо перетащить видео в список ниже")
        add_btn.clicked.connect(self._add_videos)
        self.start_btn = QPushButton("▶ Старт очереди")
        self.start_btn.clicked.connect(self._start_queue)
        self.start_btn.setEnabled(False)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(self.start_btn)
        left_lay.addLayout(btn_row)
        self.job_list = DropListWidget()
        self.job_list.currentRowChanged.connect(self._on_select_job)
        self.job_list.files_dropped.connect(self._add_paths)
        self._update_drop_hint()
        left_lay.addWidget(self.job_list, stretch=1)
        clear_btn = QPushButton("Очистить список")
        clear_btn.setObjectName("Ghost")
        clear_btn.clicked.connect(self._clear_jobs)
        left_lay.addWidget(clear_btn)
        split.addWidget(left)

        # --- right: details (scrollable) ---
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setSpacing(10)

        # preview card (with its own length / scene settings)
        prev_card, prev_lay = _card("Превью")

        set_row = QHBoxLayout()
        set_row.addWidget(QLabel("Длительность, сек:"))
        self.len_spin = QDoubleSpinBox()
        self.len_spin.setRange(2.0, 60.0)
        self.len_spin.setSingleStep(1.0)
        self.len_spin.setDecimals(0)
        self.len_spin.setValue(self.settings.target_len)
        self.len_spin.valueChanged.connect(self._on_video_settings_changed)
        set_row.addWidget(self.len_spin)
        set_row.addSpacing(18)
        set_row.addWidget(QLabel("Сцен:"))
        self.scenes_spin = QSpinBox()
        self.scenes_spin.setRange(2, 20)
        self.scenes_spin.setValue(self.settings.num_clips)
        self.scenes_spin.valueChanged.connect(self._on_video_settings_changed)
        set_row.addWidget(self.scenes_spin)
        set_row.addStretch(1)
        prev_lay.addLayout(set_row)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(320)
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        prev_lay.addWidget(self.video_widget)

        prev_btns = QHBoxLayout()
        self.play_btn = QPushButton("▶ / ⏸")
        self.play_btn.clicked.connect(self._toggle_play)
        # single button: rebuilds the preview from the current settings, picking a
        # fresh selection of moments each time.
        self.regen_prev_btn = QPushButton("↻ Перегенерировать превью")
        self.regen_prev_btn.clicked.connect(self._regen_preview)
        self.download_btn = QPushButton("⬇ Скачать превью")
        self.download_btn.setObjectName("Primary")
        self.download_btn.clicked.connect(self._download_preview)
        prev_btns.addWidget(self.play_btn)
        prev_btns.addWidget(self.regen_prev_btn)
        prev_btns.addStretch(1)
        prev_btns.addWidget(self.download_btn)
        prev_lay.addLayout(prev_btns)
        rl.addWidget(prev_card)

        # --- description card (with its own length settings) ---
        desc_card, desc_lay = _card("Описание")
        d_row = QHBoxLayout()
        d_row.addWidget(QLabel("Слов:"))
        self.descwords_spin = QSpinBox()
        self.descwords_spin.setRange(10, 200)
        self.descwords_spin.setValue(self.settings.desc_words)
        self.descwords_spin.valueChanged.connect(self._on_text_settings_changed)
        d_row.addWidget(self.descwords_spin)
        d_row.addWidget(QLabel("±"))
        self.desctol_spin = QSpinBox()
        self.desctol_spin.setRange(0, 60)
        self.desctol_spin.setValue(self.settings.desc_words_tol)
        self.desctol_spin.valueChanged.connect(self._on_text_settings_changed)
        d_row.addWidget(self.desctol_spin)
        d_row.addStretch(1)
        desc_lay.addLayout(d_row)
        self.f_desc_ru = FieldBox("RU", self._regen_desc)
        self.f_desc_en = FieldBox("EN", self._regen_desc)
        desc_lay.addWidget(self.f_desc_ru)
        desc_lay.addWidget(self.f_desc_en)
        rl.addWidget(desc_card)

        # --- hashtags card (with its own count / words settings) ---
        tags_card, tags_lay = _card("Хэштеги")
        t_row = QHBoxLayout()
        t_row.addWidget(QLabel("Количество:"))
        self.tagcount_spin = QSpinBox()
        self.tagcount_spin.setRange(1, 40)
        self.tagcount_spin.setValue(self.settings.hashtag_count)
        self.tagcount_spin.valueChanged.connect(self._on_text_settings_changed)
        t_row.addWidget(self.tagcount_spin)
        t_row.addSpacing(18)
        t_row.addWidget(QLabel("Слов в теге:"))
        self.tagwords_spin = QSpinBox()
        self.tagwords_spin.setRange(1, 4)
        self.tagwords_spin.setValue(self.settings.hashtag_words)
        self.tagwords_spin.valueChanged.connect(self._on_text_settings_changed)
        t_row.addWidget(self.tagwords_spin)
        t_row.addStretch(1)
        tags_lay.addLayout(t_row)
        self.f_tags_ru = FieldBox("RU", self._regen_tags, small=True)
        self.f_tags_en = FieldBox("EN", self._regen_tags, small=True)
        tags_lay.addWidget(self.f_tags_ru)
        tags_lay.addWidget(self.f_tags_en)
        rl.addWidget(tags_card)
        rl.addStretch(1)

        right_scroll.setWidget(right)
        split.addWidget(right_scroll)
        split.setSizes([330, 900])
        outer.addWidget(split, stretch=1)

        self._set_details_enabled(False)
        return w

    # ============================================================ presets tab
    def _build_presets_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(QLabel("Пресет:"))
        self.preset_edit_combo = QComboBox()
        self.preset_edit_combo.addItems([p.name for p in self.prefs.presets])
        self.preset_edit_combo.currentTextChanged.connect(self._load_preset_into_editor)
        row.addWidget(self.preset_edit_combo, stretch=1)
        new_btn = QPushButton("＋ Новый")
        new_btn.clicked.connect(self._new_preset)
        del_btn = QPushButton("🗑 Удалить")
        del_btn.setObjectName("Ghost")
        del_btn.clicked.connect(self._delete_preset)
        row.addWidget(new_btn)
        row.addWidget(del_btn)
        lay.addLayout(row)

        c1, l1 = _card("Промпт для описания (на русском)")
        self.desc_prompt_edit = QPlainTextEdit()
        self.desc_prompt_edit.setFixedHeight(150)
        l1.addWidget(self.desc_prompt_edit)
        lay.addWidget(c1)

        c2, l2 = _card("Промпт для хэштегов (на русском)")
        self.tags_prompt_edit = QPlainTextEdit()
        self.tags_prompt_edit.setFixedHeight(150)
        l2.addWidget(self.tags_prompt_edit)
        lay.addWidget(c2)

        save_row = QHBoxLayout()
        save_btn = QPushButton("💾 Сохранить пресет")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save_preset)
        self.preset_status = QLabel("")
        self.preset_status.setObjectName("Muted")
        save_row.addWidget(save_btn)
        save_row.addWidget(self.preset_status)
        save_row.addStretch(1)
        lay.addLayout(save_row)
        lay.addStretch(1)

        self._load_preset_into_editor(self.prefs.active)
        return w

    # ================================================================ actions
    def _reload_preset_combo(self) -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems([p.name for p in self.prefs.presets])
        self.preset_combo.setCurrentText(self.prefs.active)
        self.preset_combo.blockSignals(False)

    def _on_preset_changed(self, name: str) -> None:
        self.prefs.active = name
        save_prefs(self.prefs)

    def _active_prompts(self) -> tuple[str, str]:
        p = self.prefs.get(self.preset_combo.currentText())
        return p.desc_prompt, p.tags_prompt

    def _add_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выберите видео (можно несколько)", str(Path.home()),
            "Видео (*.mp4 *.mov *.MOV *.mkv *.avi *.webm *.m4v);;Все файлы (*.*)",
        )
        self._add_paths(paths)

    def _add_paths(self, paths: list[str]) -> None:
        """Add one or many videos to the queue (from the dialog or drag-and-drop)."""
        desc_p, tags_p = self._active_prompts()
        added = 0
        existing = {str(j.video) for j in self.jobs}
        for path in paths:
            if str(path) in existing:
                continue
            job = Job(
                video=Path(path), desc_prompt=desc_p, tags_prompt=tags_p,
                target_len=float(self.len_spin.value()),
                num_clips=int(self.scenes_spin.value()),
                keep_audio=not self.no_audio_check.isChecked(),
                desc_words=int(self.descwords_spin.value()),
                desc_words_tol=int(self.desctol_spin.value()),
                hashtag_count=int(self.tagcount_spin.value()),
                hashtag_words=int(self.tagwords_spin.value()),
            )
            self.jobs.append(job)
            self._add_job_item(job)
            existing.add(str(path))
            added += 1
        if added:
            self.start_btn.setEnabled(True)
            self._update_drop_hint()
            if self.current < 0:
                self.job_list.setCurrentRow(0)
            self.status.setText(f"Добавлено видео: {added}")

    def _update_drop_hint(self) -> None:
        """Repaint so the empty-state placeholder shows/hides correctly."""
        self.job_list.viewport().update()

    def _add_job_item(self, job: Job) -> None:
        item = QListWidgetItem(f"{_STATUS_ICON[job.status]}  {job.name}")
        self.job_list.addItem(item)

    def _refresh_job_item(self, idx: int) -> None:
        job = self.jobs[idx]
        self.job_list.item(idx).setText(f"{_STATUS_ICON[job.status]}  {job.name}")

    def _clear_jobs(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())  # release any temp preview file before deletion
        for job in self.jobs:
            job.cleanup()
        self.jobs.clear()
        self.job_list.clear()
        self.current = -1
        self._set_details_enabled(False)
        self.start_btn.setEnabled(False)
        self._update_drop_hint()

    def closeEvent(self, event) -> None:
        """Stop in-flight work, then clean up temp output dirs on exit."""
        self.player.stop()
        self.player.setSource(QUrl())
        if self._queue_worker is not None:
            self._queue_worker.stop()
        # wait for any running worker threads so cleanup doesn't race file writes
        for thread, _worker in list(getattr(self, "_threads", [])):
            try:
                thread.quit()
                thread.wait(3000)
            except RuntimeError:
                pass  # C++ object already gone
        for job in self.jobs:
            job.cleanup()
        super().closeEvent(event)

    def _start_queue(self) -> None:
        pending = [j for j in self.jobs if j.status in (JobStatus.PENDING, JobStatus.FAILED)]
        if not pending:
            self.status.setText("Нет видео в очереди")
            return
        self.start_btn.setEnabled(False)
        self._queue_running = True
        self._lock_editing(True)        # avoid mutating a Job while a worker reads it
        self.status.setText("Очередь запущена…")
        self._queue_worker = QueueWorker(self.jobs)
        self._queue_worker.job_started.connect(self._on_job_started)
        self._queue_worker.job_progress.connect(self._on_job_progress)
        self._queue_worker.job_done.connect(self._on_job_done)
        self._queue_worker.all_done.connect(self._on_queue_done)
        run_on_thread(self, self._queue_worker)

    def _on_job_started(self, idx: int) -> None:
        self.jobs[idx].status = JobStatus.RUNNING
        self._refresh_job_item(idx)

    def _on_job_progress(self, idx: int, stage: str) -> None:
        self.status.setText(f"[{idx + 1}/{len(self.jobs)}] {self.jobs[idx].name}: {stage}…")

    def _on_job_done(self, idx: int, job: Job) -> None:
        # run_full mutates the same Job object in place, so no reassignment needed.
        self._refresh_job_item(idx)
        if idx == self.current:
            self._show_job(idx)

    def _on_queue_done(self) -> None:
        self._queue_running = False
        self._queue_worker = None
        self.status.setText("✅ Очередь обработана")
        self.start_btn.setEnabled(True)
        self._lock_editing(False)
        if 0 <= self.current < len(self.jobs):
            self._show_job(self.current)   # re-enable controls for the selected job

    def _lock_editing(self, locked: bool) -> None:
        """Disable per-video inputs + regen while the queue worker owns the Jobs."""
        for w in (self.len_spin, self.scenes_spin, self.no_audio_check,
                  self.descwords_spin, self.desctol_spin,
                  self.tagcount_spin, self.tagwords_spin):
            w.setEnabled(not locked)
        if locked:
            self._set_details_enabled(False)

    def _on_select_job(self, idx: int) -> None:
        if 0 <= idx < len(self.jobs):
            self.current = idx
            self._show_job(idx)

    def _show_job(self, idx: int) -> None:
        job = self.jobs[idx]
        done = job.status == JobStatus.DONE
        # while the queue owns the Jobs, keep editing/regen locked
        self._set_details_enabled(done and not self._queue_running)
        # sync per-video settings controls from the job (without retriggering signals)
        s = self.settings
        for w, val in ((self.len_spin, job.target_len or s.target_len),
                       (self.scenes_spin, job.num_clips or s.num_clips),
                       (self.descwords_spin, job.desc_words or s.desc_words),
                       (self.desctol_spin, job.desc_words_tol
                        if job.desc_words_tol is not None else s.desc_words_tol),
                       (self.tagcount_spin, job.hashtag_count or s.hashtag_count),
                       (self.tagwords_spin, job.hashtag_words or s.hashtag_words)):
            w.blockSignals(True)
            w.setValue(val)
            w.blockSignals(False)
        self.no_audio_check.blockSignals(True)
        self.no_audio_check.setChecked(not job.keep_audio)
        self.no_audio_check.blockSignals(False)

        self.f_desc_ru.set_text(job.description_ru)
        self.f_desc_en.set_text(job.description_en)
        self.f_tags_ru.set_text(" ".join(job.hashtags_ru))
        self.f_tags_en.set_text(" ".join(job.hashtags_en))
        if job.status == JobStatus.FAILED:
            self.status.setText(f"❌ {job.name}: ошибка")
        self.player.stop()
        if done and job.preview_path and job.preview_path.exists():
            self.player.setSource(QUrl.fromLocalFile(str(job.preview_path)))
            self.player.play()

    def _set_details_enabled(self, on: bool) -> None:
        for wdg in (self.play_btn, self.regen_prev_btn, self.download_btn,
                    self.f_desc_ru, self.f_desc_en, self.f_tags_ru, self.f_tags_en):
            wdg.setEnabled(on)

    def _on_video_settings_changed(self, *_) -> None:
        """Persist edited preview length / scene count onto the current job."""
        job = self._job()
        if not job:
            return
        job.target_len = float(self.len_spin.value())
        job.num_clips = int(self.scenes_spin.value())
        job.keep_audio = not self.no_audio_check.isChecked()

    def _on_text_settings_changed(self, *_) -> None:
        """Persist edited description-length / hashtag settings onto the current job.

        Takes effect on the next text (re)generation — use the field's
        «Перегенерировать» button to apply to an already-processed video.
        """
        job = self._job()
        if not job:
            return
        job.desc_words = int(self.descwords_spin.value())
        job.desc_words_tol = int(self.desctol_spin.value())
        job.hashtag_count = int(self.tagcount_spin.value())
        job.hashtag_words = int(self.tagwords_spin.value())

    # --- per-field regeneration (run off-thread) ---
    def _job(self) -> Job | None:
        return self.jobs[self.current] if 0 <= self.current < len(self.jobs) else None

    def _run_task(self, fn, on_done, busy_widget=None) -> None:
        if busy_widget:
            busy_widget.set_busy(True)
        worker = TaskWorker(fn)
        worker.progress.connect(lambda m: self.status.setText(f"⏳ {m}…"))

        def _finish(result):
            if busy_widget:
                busy_widget.set_busy(False)
            on_done(result)
            self.status.setText("✅ Готово")

        def _fail(msg):
            if busy_widget:
                busy_widget.set_busy(False)
            QMessageBox.critical(self, "Ошибка", msg)
            self.status.setText("❌ Ошибка")

        worker.done.connect(_finish)
        worker.failed.connect(_fail)
        run_on_thread(self, worker)

    def _regen_preview(self) -> None:
        """Rebuild the preview from the current length/scene settings, picking a
        fresh selection of moments each click."""
        job = self._job()
        if not job or job.meta is None:
            return
        self._on_video_settings_changed()   # capture latest length / scenes / audio
        self.regen_prev_btn.setEnabled(False)
        self.regen_prev_btn.setText("⏳…")

        def task(progress):
            return regenerate_preview(job, self.settings, progress=progress)

        def done(path):
            self.regen_prev_btn.setEnabled(True)
            self.regen_prev_btn.setText("↻ Перегенерировать превью")
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.play()

        self._run_task(task, done)

    def _regen_desc(self) -> None:
        job = self._job()
        if not job:
            return
        job.desc_prompt, _ = self._active_prompts()
        self._run_task(
            lambda progress: regenerate_description(job, self.settings, progress=progress),
            lambda res: (self.f_desc_ru.set_text(res[0]), self.f_desc_en.set_text(res[1])),
            busy_widget=self.f_desc_ru,
        )

    def _regen_tags(self) -> None:
        job = self._job()
        if not job:
            return
        _, job.tags_prompt = self._active_prompts()
        self._run_task(
            lambda progress: regenerate_hashtags(job, self.settings, progress=progress),
            lambda res: (self.f_tags_ru.set_text(" ".join(res[0])),
                         self.f_tags_en.set_text(" ".join(res[1]))),
            busy_widget=self.f_tags_ru,
        )

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _download_preview(self) -> None:
        job = self._job()
        if not job or not job.preview_path:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Сохранить превью",
            str(Path.home() / f"{Path(job.name).stem}_preview.mp4"), "MP4 (*.mp4)",
        )
        if dest:
            shutil.copyfile(job.preview_path, dest)
            self.status.setText(f"✅ Сохранено: {dest}")

    # --- presets management ---
    def _load_preset_into_editor(self, name: str) -> None:
        p = self.prefs.get(name)
        self.desc_prompt_edit.setPlainText(p.desc_prompt)
        self.tags_prompt_edit.setPlainText(p.tags_prompt)

    def _new_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Новый пресет", "Название пресета:")
        if ok and name.strip():
            self.prefs.upsert(Preset(name.strip(), "", ""))
            save_prefs(self.prefs)
            self._sync_preset_combos(select=name.strip())

    def _delete_preset(self) -> None:
        name = self.preset_edit_combo.currentText()
        self.prefs.delete(name)
        save_prefs(self.prefs)
        self._sync_preset_combos()

    def _save_preset(self) -> None:
        name = self.preset_edit_combo.currentText()
        self.prefs.upsert(Preset(
            name,
            self.desc_prompt_edit.toPlainText().strip(),
            self.tags_prompt_edit.toPlainText().strip(),
        ))
        save_prefs(self.prefs)
        self.preset_status.setText("💾 Сохранено")
        self._sync_preset_combos(select=name)

    def _sync_preset_combos(self, select: str | None = None) -> None:
        names = [p.name for p in self.prefs.presets]
        for combo in (self.preset_edit_combo, self.preset_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            combo.blockSignals(False)
        target = select or self.prefs.active
        if target in names:
            self.preset_edit_combo.setCurrentText(target)
            self.preset_combo.setCurrentText(target)
        self._load_preset_into_editor(self.preset_edit_combo.currentText())


def main() -> None:
    app = QApplication([])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
