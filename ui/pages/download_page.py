"""Página principal: añadir enlaces, cola y opciones de conversión."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.config import ConfigStore
from core.downloader import engine_version, ffmpeg_location
from core.manager import DownloadManager
from core.models import DownloadOptions, Job, JobStatus, MediaFormat
from core.utils import (
    extract_urls,
    format_bytes,
    format_duration,
    format_eta,
    format_speed,
    open_in_file_manager,
    open_media,
    time_ago,
)
from ui.dialogs import ConfirmDialog, PlaylistDialog
from ui.icons import make_icon
from ui.theme import theme
from ui.thumbs import ThumbnailLoader
from ui.widgets import (
    ActivitySpinner,
    AnimatedProgressBar,
    DropZone,
    ElidedLabel,
    SettingRow,
    ToggleSwitch,
    divider,
    icon_button,
    placeholder_thumbnail,
    rounded_thumbnail,
)

ToastFn = Callable[..., None]

AUDIO_FORMATS = [
    ("MP3", "mp3"),
    ("M4A", "m4a"),
    ("FLAC", "flac"),
    ("WAV", "wav"),
    ("OPUS", "opus"),
]
VIDEO_FORMATS = [("MP4", "mp4")]
AUDIO_QUALITIES = [
    ("320 kbps · máxima", "320"),
    ("256 kbps · alta", "256"),
    ("192 kbps · equilibrada", "192"),
    ("128 kbps · compacta", "128"),
]
VIDEO_QUALITIES = [
    ("Mejor disponible", "best"),
    ("2160p · 4K", "2160"),
    ("1440p · 2K", "1440"),
    ("1080p · Full HD", "1080"),
    ("720p · HD", "720"),
    ("480p", "480"),
    ("360p", "360"),
]

PLAYLIST_RE = re.compile(r"(?:[?&]list=|/playlist\b)", re.IGNORECASE)
VIDEO_PARAM_RE = re.compile(r"[?&]v=", re.IGNORECASE)
TEXT_EXTENSIONS = {".txt", ".m3u", ".m3u8", ".url", ".csv", ".list"}


def is_playlist_url(url: str) -> bool:
    if not PLAYLIST_RE.search(url):
        return False
    return bool(VIDEO_PARAM_RE.search(url)) is False


def quality_text(fmt: MediaFormat, quality: str) -> str:
    if fmt is MediaFormat.MP4:
        return "Mejor calidad" if quality == "best" else f"{quality}p"
    return f"{quality} kbps"


def status_badge(status: JobStatus) -> tuple[str, str]:
    return {
        JobStatus.QUEUED: ("En cola", "Badge"),
        JobStatus.PROBING: ("Analizando", "Badge"),
        JobStatus.DOWNLOADING: ("Descargando", "Badge"),
        JobStatus.PROCESSING: ("Convirtiendo", "BadgeVideo"),
        JobStatus.DONE: ("Completado", "BadgeSuccess"),
        JobStatus.ERROR: ("Error", "BadgeError"),
        JobStatus.CANCELLED: ("Cancelado", "Badge"),
    }.get(status, ("—", "Badge"))


class JobCard(QFrame):
    cancelRequested = Signal(str)
    retryRequested = Signal(str)
    removeRequested = Signal(str)
    playRequested = Signal(str)
    folderRequested = Signal(str)

    def __init__(self, job: Job, thumbs: ThumbnailLoader, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedHeight(116)
        self.job = job
        self.job_id = job.id
        self._thumbs = thumbs
        self._thumb_url = ""
        self._has_custom_thumb = False

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(13)

        self.thumb = QLabel()
        self.thumb.setFixedSize(106, 66)
        self.thumb.setScaledContents(False)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignVCenter)

        info = QVBoxLayout()
        info.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.title = ElidedLabel(job.display_title)
        self.title.setObjectName("H3")
        top.addWidget(self.title, 1)
        self.badge = QLabel("En cola")
        self.badge.setObjectName("Badge")
        top.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_play = icon_button("play", "Reproducir archivo", theme().success, 16)
        self.btn_folder = icon_button("folder-open", "Abrir carpeta", theme().muted, 16)
        self.btn_cancel = icon_button("x", "Cancelar descarga", theme().muted, 16)
        self.btn_retry = icon_button("refresh", "Reintentar", theme().accent, 16)
        self.btn_remove = icon_button("trash", "Quitar de la cola", theme().muted, 16, danger=True)
        for button in (self.btn_play, self.btn_folder, self.btn_cancel, self.btn_retry, self.btn_remove):
            button.setFixedSize(26, 26)
            top.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        info.addLayout(top)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self.meta = QLabel()
        self.meta.setObjectName("MutedSmall")
        meta_row.addWidget(self.meta)
        meta_row.addStretch()
        self.percent = QLabel("")
        self.percent.setObjectName("MutedSmall")
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.percent.setFixedWidth(46)
        meta_row.addWidget(self.percent)
        info.addLayout(meta_row)

        self.progress = AnimatedProgressBar(height=7)
        info.addWidget(self.progress)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.spinner = ActivitySpinner(size=14)
        bottom.addWidget(self.spinner)
        self.stage = ElidedLabel("")
        self.stage.setObjectName("MutedSmall")
        bottom.addWidget(self.stage, 1)
        self.detail = QLabel("")
        self.detail.setObjectName("MutedSmall")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(self.detail, 0)
        info.addLayout(bottom)

        root.addLayout(info, 1)

        self.btn_cancel.clicked.connect(lambda: self.cancelRequested.emit(self.job_id))
        self.btn_retry.clicked.connect(lambda: self.retryRequested.emit(self.job_id))
        self.btn_remove.clicked.connect(lambda: self.removeRequested.emit(self.job_id))
        self.btn_folder.clicked.connect(lambda: self.folderRequested.emit(self.job_id))
        self.btn_play.clicked.connect(lambda: self.playRequested.emit(self.job_id))

        self.update_from(job)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            return
        self._has_custom_thumb = True
        self.thumb.setPixmap(rounded_thumbnail(pixmap, 106, 66, 9))

    def update_from(self, job: Job) -> None:
        self.job = job
        self.title.setText(job.display_title)
        kind = job.fmt
        quality = quality_text(kind, job.options.quality)
        bits = []
        if job.uploader:
            bits.append(job.uploader)
        if job.duration:
            bits.append(format_duration(job.duration))
        bits.append(quality)
        if job.playlist_title:
            bits.append(job.playlist_title)
        self.meta.setText("  ·  ".join(bits) if bits else "Esperando información del enlace")

        label, name = status_badge(job.status)
        if self.badge.text() != label or self.badge.objectName() != name:
            self.badge.setText(label)
            self.badge.setObjectName(name)
            self.badge.style().unpolish(self.badge)
            self.badge.style().polish(self.badge)

        active = job.status.is_active
        self.spinner.setVisible(active)
        if active:
            self.spinner.start()
        else:
            self.spinner.stop()

        self.btn_play.setVisible(job.status is JobStatus.DONE)
        self.btn_folder.setVisible(job.status is JobStatus.DONE and bool(job.filepath))
        self.btn_cancel.setVisible(job.status in (JobStatus.QUEUED, JobStatus.PROBING, JobStatus.DOWNLOADING, JobStatus.PROCESSING))
        self.btn_retry.setVisible(job.status in (JobStatus.ERROR, JobStatus.CANCELLED))
        self.btn_remove.setVisible(job.status.is_finished)

        self.progress.setVisible(job.status not in (JobStatus.CANCELLED,))
        self.progress.setIndeterminate(job.status in (JobStatus.PROBING, JobStatus.PROCESSING))

        detail = ""
        percent = ""
        if job.status is JobStatus.DONE:
            self.stage.setText("Completado")
            self.stage.setObjectName("SuccessText")
            detail = format_bytes(job.size) if job.size else ""
            percent = "100%"
            self.progress.setValue(100)
        elif job.status is JobStatus.DOWNLOADING:
            self.stage.setText(job.stage or "Descargando")
            self.stage.setObjectName("MutedSmall")
            support = []
            if job.speed:
                support.append(format_speed(job.speed))
            if job.eta:
                support.append(f"quedan {format_eta(job.eta)}")
            elif job.total:
                support.append(f"{format_bytes(job.downloaded)} / {format_bytes(job.total)}")
            detail = "  ·  ".join(support)
            percent = f"{job.progress:.0f}%"
            self.progress.setValue(job.progress)
        elif job.status is JobStatus.PROCESSING:
            self.stage.setText(job.stage or "Procesando archivo")
            self.stage.setObjectName("MutedSmall")
            detail = "No cierres Sonora"
            self.progress.setValue(job.progress)
        elif job.status is JobStatus.PROBING:
            self.stage.setText(job.stage or "Obteniendo información del enlace")
            self.stage.setObjectName("MutedSmall")
            detail = "Un momento…"
            self.progress.setValue(0)
        elif job.status is JobStatus.QUEUED:
            self.stage.setText("En cola" if job.meta_loaded else "Esperando análisis")
            self.stage.setObjectName("MutedSmall")
            detail = quality
            self.progress.setValue(0)
        elif job.status is JobStatus.ERROR:
            self.stage.setText(job.error or "No se pudo completar la descarga")
            self.stage.setToolTip(job.error)
            self.stage.setObjectName("ErrorText")
            detail = "Pulsa reintentar"
            self.progress.setValue(0)
        elif job.status is JobStatus.CANCELLED:
            self.stage.setText("Cancelado")
            self.stage.setObjectName("MutedSmall")
            detail = "Puedes reintentarlo"
            self.progress.setValue(0)

        self.percent.setText(percent)
        self.detail.setText(detail)
        self.stage.style().unpolish(self.stage)
        self.stage.style().polish(self.stage)

        if job.thumbnail_path and Path(job.thumbnail_path).exists():
            pixmap = QPixmap(job.thumbnail_path)
            if not pixmap.isNull():
                self.thumb.setPixmap(rounded_thumbnail(pixmap, 106, 66, 9))
                return
        if job.thumbnail_url:
            if job.thumbnail_url != self._thumb_url:
                self._thumb_url = job.thumbnail_url
                self._thumbs.request(self.job_id, job.thumbnail_url)
            if not self._has_custom_thumb:
                self.thumb.setPixmap(placeholder_thumbnail(106, 66, job.fmt is MediaFormat.MP4))
        elif not self._has_custom_thumb:
            self.thumb.setPixmap(placeholder_thumbnail(106, 66, job.fmt is MediaFormat.MP4))

    def refresh_theme(self) -> None:
        if not self._has_custom_thumb:
            self.thumb.setPixmap(placeholder_thumbnail(106, 66, self.job.fmt is MediaFormat.MP4))

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self.job.status is JobStatus.DONE:
            self.playRequested.emit(self.job_id)
        super().mouseDoubleClickEvent(event)


class EmptyState(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 40, 20, 40)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble = QLabel()
        bubble.setFixedSize(74, 74)
        bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble.setStyleSheet(f"background-color: {theme().accent_soft}; border-radius: 24px;")
        bubble.setPixmap(make_icon("download-cloud", theme().accent, 34).pixmap(34, 34))
        layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title = QLabel("Tu cola está vacía")
        self.title.setObjectName("H2")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = QLabel("Arrastra enlaces aquí o pega una URL para empezar a convertir.")
        self.subtitle.setObjectName("Muted")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        hints = QHBoxLayout()
        hints.setSpacing(8)
        hints.addStretch()
        for text in ("Ctrl + V  pegar", "Ctrl + O  importar .txt", "Arrastrar y soltar"):
            chip = QLabel(text)
            chip.setObjectName("MutedSmall")
            chip.setStyleSheet(
                f"border: 1px solid {theme().border}; border-radius: 8px; padding: 4px 9px; color: {theme().muted2};"
            )
            hints.addWidget(chip)
        hints.addStretch()
        layout.addSpacing(4)
        layout.addLayout(hints)
        self.setMinimumHeight(300)


class DownloadPage(QWidget):
    def __init__(
        self,
        manager: DownloadManager,
        config: ConfigStore,
        thumbs: ThumbnailLoader,
        toast: ToastFn,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.config = config
        self.thumbs = thumbs
        self._toast = toast
        self.cards: dict[str, JobCard] = {}
        self._pending_playlists: dict[str, str] = {}
        self._filter = "all"
        settings = self.config.settings
        self._fmt = MediaFormat.from_value(settings.default_format)
        self._quality = settings.quality_for(self._fmt)

        self.setObjectName("Transparent")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(13)
        self.dropzone = DropZone()
        self.dropzone.textDropped.connect(self.add_from_text)
        self.dropzone.filesDropped.connect(self.add_files)
        self.dropzone.clicked.connect(self._focus_input)
        left.addWidget(self.dropzone)
        left.addWidget(self._build_input_bar())
        left.addLayout(self._build_toolbar())
        left.addWidget(self._build_queue(), 1)
        left.addWidget(self._build_status_bar())
        outer.addLayout(left, 1)
        outer.addWidget(self._build_side_panel(), 0)

        self.thumbs.loaded.connect(self._on_thumb_loaded)
        self.manager.jobAdded.connect(self._on_job_added)
        self.manager.jobUpdated.connect(self._on_job_updated)
        self.manager.jobRemoved.connect(self._on_job_removed)
        self.manager.statsChanged.connect(self._on_stats)
        self.manager.playlistResolved.connect(self._on_playlist_resolved)
        self.manager.playlistFailed.connect(self._on_playlist_failed)
        self.manager.pausedChanged.connect(lambda _: self._refresh_pause_button())
        self._select_format(self._fmt, persist=False)
        self._update_empty_state()
        self._on_stats({})
        self._update_responsive()

        for job in self.manager.ordered_jobs():
            self._on_job_added(job.id)

    # ------------------------------------------------------------ responsivo
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_responsive()

    def _update_responsive(self) -> None:
        """Oculta métricas secundarias cuando la columna se queda estrecha."""
        if not hasattr(self, "status_bar") or not hasattr(self, "eta_box"):
            return
        width = self.status_bar.width()
        if width <= 0:
            return
        self.eta_box.setVisible(width >= 660)
        self.size_box.setVisible(width >= 610)
        self.count_label.setVisible(width >= 560)

    # ------------------------------------------------------------ construcción
    def _build_input_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Card")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(13, 9, 13, 9)
        layout.setSpacing(9)
        icon = QLabel()
        icon.setPixmap(make_icon("link", theme().accent, 19).pixmap(19, 19))
        layout.addWidget(icon)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Pega uno o varios enlaces: YouTube, SoundCloud, Vimeo, playlists…")
        self.url_input.returnPressed.connect(self._add_current)
        layout.addWidget(self.url_input, 1)
        self.paste_button = icon_button("clipboard", "Pegar del portapapeles y añadir", theme().muted, 18)
        self.paste_button.clicked.connect(self._paste_from_clipboard)
        layout.addWidget(self.paste_button)
        self.import_button = icon_button("file-text", "Importar enlaces desde un .txt", theme().muted, 18)
        self.import_button.clicked.connect(self._import_file)
        layout.addWidget(self.import_button)
        self.add_button = QPushButton("Añadir")
        self.add_button.setProperty("variant", "primary")
        self.add_button.setIcon(make_icon("plus", "#FFFFFF", 17))
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self._add_current)
        layout.addWidget(self.add_button)
        return bar

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(7)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        for key, text in (("all", "Todos"), ("active", "En curso"), ("done", "Completados"), ("error", "Con errores")):
            chip = QPushButton(text)
            chip.setProperty("chip", "true")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setChecked(key == "all")
            chip.clicked.connect(lambda _, k=key: self._set_filter(k))
            self._filter_group.addButton(chip)
            row.addWidget(chip)
        self.count_label = QLabel("0 elementos")
        self.count_label.setObjectName("MutedSmall")
        row.addWidget(self.count_label)
        row.addStretch()
        retry = icon_button("refresh", "Reintentar todas las descargas fallidas", theme().muted, 17)
        retry.clicked.connect(self._retry_failed)
        row.addWidget(retry)
        clear = icon_button("eraser", "Vaciar elementos terminados", theme().muted, 17)
        clear.clicked.connect(self._clear_finished)
        row.addWidget(clear)
        return row

    def _build_queue(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("Transparent")
        self.queue_layout = QVBoxLayout(container)
        self.queue_layout.setContentsMargins(0, 0, 6, 8)
        self.queue_layout.setSpacing(8)
        self.queue_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.empty_state = EmptyState()
        self.queue_layout.addWidget(self.empty_state)
        scroll.setWidget(container)
        return scroll

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Card")
        bar.setFixedHeight(82)
        self.status_bar = bar
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 11, 14, 11)
        layout.setSpacing(12)

        progress_col = QVBoxLayout()
        progress_col.setSpacing(5)
        top = QHBoxLayout()
        top.setSpacing(10)
        label = QLabel("Progreso de la cola")
        label.setObjectName("H3")
        top.addWidget(label, 0)
        self.overall_label = ElidedLabel("Sin descargas", mode=Qt.TextElideMode.ElideLeft)
        self.overall_label.setObjectName("MutedSmall")
        self.overall_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.overall_label, 1)
        progress_col.addLayout(top)
        self.overall_bar = AnimatedProgressBar(height=7)
        progress_col.addWidget(self.overall_bar)
        layout.addLayout(progress_col, 1)

        self.speed_box, self.speed_label = self._stat_widget(layout, "zap", "—", 76)
        self.eta_box, self.eta_label = self._stat_widget(layout, "clock", "—", 88)
        self.size_box, self.size_label = self._stat_widget(layout, "bar-chart", "0 B", 64)

        self.cancel_all_button = icon_button("cloud-off", "Cancelar todas las descargas", theme().muted, 18)
        self.cancel_all_button.clicked.connect(self._cancel_all)
        layout.addWidget(self.cancel_all_button)

        self.pause_button = QPushButton("Iniciar cola")
        self.pause_button.setProperty("variant", "primary")
        self.pause_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_button.setMinimumWidth(126)
        self.pause_button.clicked.connect(self._toggle_queue)
        layout.addWidget(self.pause_button)
        return bar

    def _stat_widget(self, layout: QHBoxLayout, icon_name: str, text: str, width: int = 0) -> tuple[QWidget, QLabel]:
        box = QWidget()
        if width:
            box.setFixedWidth(width)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        icon = QLabel()
        icon.setPixmap(make_icon(icon_name, theme().muted2, 14).pixmap(14, 14))
        row.addWidget(icon)
        label = QLabel(text)
        label.setObjectName("MutedSmall")
        row.addWidget(label, 1)
        layout.addWidget(box)
        return box, label

    def _build_side_panel(self) -> QScrollArea:
        settings = self.config.settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(352)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel = QWidget()
        panel.setObjectName("Transparent")
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(12)

        # Formato
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 13, 15, 15)
        layout.setSpacing(9)
        layout.addWidget(self._card_title("sparkles", "Formato de salida", "Elige cómo quieres guardar cada descarga"))
        segments = QFrame()
        segments.setObjectName("CardSoft")
        seg_layout = QHBoxLayout(segments)
        seg_layout.setContentsMargins(4, 4, 4, 4)
        seg_layout.setSpacing(3)
        self.seg_group = QButtonGroup(self)
        self.seg_group.setExclusive(True)
        self.audio_seg = QPushButton("Audio")
        self.audio_seg.setProperty("segment", "true")
        self.audio_seg.setCheckable(True)
        self.audio_seg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.audio_seg.setIcon(make_icon("headphones", theme().muted, 17))
        self.audio_seg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.video_seg = QPushButton("Vídeo")
        self.video_seg.setProperty("segment", "true")
        self.video_seg.setCheckable(True)
        self.video_seg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.video_seg.setIcon(make_icon("film", theme().muted, 17))
        self.video_seg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.seg_group.addButton(self.audio_seg)
        self.seg_group.addButton(self.video_seg)
        self.audio_seg.clicked.connect(lambda: self._switch_kind("audio"))
        self.video_seg.clicked.connect(lambda: self._switch_kind("video"))
        seg_layout.addWidget(self.audio_seg)
        seg_layout.addWidget(self.video_seg)
        layout.addWidget(segments)

        fmt_row = QHBoxLayout()
        fmt_label = QLabel("Contenedor")
        fmt_label.setObjectName("Muted")
        fmt_row.addWidget(fmt_label)
        fmt_row.addStretch()
        self.format_combo = QComboBox()
        self.format_combo.setFixedWidth(136)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self.format_combo)
        layout.addLayout(fmt_row)

        quality_row = QHBoxLayout()
        quality_label = QLabel("Calidad")
        quality_label.setObjectName("Muted")
        quality_row.addWidget(quality_label)
        quality_row.addStretch()
        self.quality_combo = QComboBox()
        self.quality_combo.setFixedWidth(204)
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        quality_row.addWidget(self.quality_combo)
        layout.addLayout(quality_row)
        self.format_hint = QLabel("")
        self.format_hint.setObjectName("MutedSmall")
        self.format_hint.setWordWrap(True)
        layout.addWidget(self.format_hint)
        col.addWidget(card)

        # Destino
        dest = QFrame()
        dest.setObjectName("Card")
        dlayout = QVBoxLayout(dest)
        dlayout.setContentsMargins(15, 13, 15, 14)
        dlayout.setSpacing(8)
        dlayout.addWidget(self._card_title("folder", "Carpeta de destino", "Dónde se guardarán los archivos"))
        self.folder_label = ElidedLabel(settings.outdir)
        self.folder_label.setObjectName("MutedSmall")
        dlayout.addWidget(self.folder_label)
        buttons = QHBoxLayout()
        buttons.setSpacing(7)
        change = QPushButton("Cambiar")
        change.setProperty("variant", "soft")
        change.setCursor(Qt.CursorShape.PointingHandCursor)
        change.clicked.connect(self._choose_folder)
        buttons.addWidget(change)
        open_button = QPushButton("Abrir")
        open_button.setProperty("variant", "ghost")
        open_button.setIcon(make_icon("external", theme().muted, 15))
        open_button.clicked.connect(lambda: open_in_file_manager(self.config.settings.outdir))
        buttons.addWidget(open_button)
        buttons.addStretch()
        dlayout.addLayout(buttons)
        col.addWidget(dest)

        # Opciones
        options = QFrame()
        options.setObjectName("Card")
        olayout = QVBoxLayout(options)
        olayout.setContentsMargins(15, 13, 15, 10)
        olayout.setSpacing(2)
        olayout.addWidget(self._card_title("settings", "Opciones", "Se aplican a las nuevas descargas"))
        for title, subtitle, key in (
            ("Incrustar portada", "Miniatura del vídeo como carátula", "embed_thumbnail"),
            ("Metadatos", "Título, artista, álbum y capítulos", "embed_metadata"),
            ("Normalizar volumen", "Nivel uniforme a -14 LUFS", "normalize_audio"),
            ("SponsorBlock", "Elimina patrocinios y promociones", "sponsorblock"),
            ("Subtítulos", "Descarga .srt en español e inglés", "write_subtitles"),
        ):
            toggle = ToggleSwitch()
            toggle.setChecked(bool(getattr(settings, key)))
            toggle.toggled.connect(lambda checked, k=key: self._toggle_option(k, checked))
            olayout.addWidget(SettingRow(title, subtitle, toggle))
        col.addWidget(options)

        # Cola
        queue = QFrame()
        queue.setObjectName("Card")
        qlayout = QVBoxLayout(queue)
        qlayout.setContentsMargins(15, 13, 15, 13)
        qlayout.setSpacing(8)
        qlayout.addWidget(self._card_title("cpu", "Rendimiento", "Ajusta cómo trabaja la cola"))
        concurrency_row = QHBoxLayout()
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        concurrency_title = QLabel("Descargas simultáneas")
        concurrency_title.setObjectName("H3")
        concurrency_sub = QLabel("Más paralelismo consume más red y CPU")
        concurrency_sub.setObjectName("MutedSmall")
        concurrency_sub.setWordWrap(True)
        text_col.addWidget(concurrency_title)
        text_col.addWidget(concurrency_sub)
        concurrency_row.addLayout(text_col, 1)
        minus = icon_button("minus", "Menos descargas simultáneas", theme().muted, 15)
        minus.setFixedSize(27, 27)
        plus = icon_button("plus", "Más descargas simultáneas", theme().muted, 15)
        plus.setFixedSize(27, 27)
        self.concurrency_value = QLabel(str(settings.concurrency))
        self.concurrency_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.concurrency_value.setFixedWidth(20)
        self.concurrency_value.setStyleSheet("font-weight: 700;")
        minus.clicked.connect(lambda: self._change_concurrency(-1))
        plus.clicked.connect(lambda: self._change_concurrency(1))
        concurrency_row.addWidget(minus)
        concurrency_row.addWidget(self.concurrency_value)
        concurrency_row.addWidget(plus)
        qlayout.addLayout(concurrency_row)
        qlayout.addWidget(divider())
        auto_toggle = ToggleSwitch()
        auto_toggle.setChecked(bool(settings.auto_start))
        auto_toggle.toggled.connect(self._toggle_auto_start)
        qlayout.addWidget(SettingRow("Inicio automático", "Comenzar al añadir enlaces", auto_toggle))
        col.addWidget(queue)

        # Motor
        engine = QFrame()
        engine.setObjectName("Card")
        elayout = QVBoxLayout(engine)
        elayout.setContentsMargins(15, 12, 15, 12)
        elayout.setSpacing(4)
        title_row = QHBoxLayout()
        title = QLabel("Motor de conversión")
        title.setObjectName("H3")
        title_row.addWidget(title)
        title_row.addStretch()
        status = QLabel("● Listo")
        status.setStyleSheet(f"color: {theme().success}; font-size: 11px; font-weight: 600;")
        title_row.addWidget(status)
        elayout.addLayout(title_row)
        ff = "FFmpeg integrado" if ffmpeg_location() else "FFmpeg no encontrado"
        info = QLabel(f"yt-dlp {engine_version()}  ·  {ff}")
        info.setObjectName("MutedSmall")
        elayout.addWidget(info)
        col.addWidget(engine)
        col.addStretch()

        scroll.setWidget(panel)
        return scroll

    def _card_title(self, icon_name: str, title: str, subtitle: str = "") -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 2)
        row.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(make_icon(icon_name, theme().accent, 17).pixmap(17, 17))
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        label = QLabel(title)
        label.setObjectName("H3")
        col.addWidget(label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("MutedSmall")
            sub.setWordWrap(True)
            col.addWidget(sub)
        row.addLayout(col, 1)
        return widget

    # --------------------------------------------------------------- acciones
    def _focus_input(self) -> None:
        self.url_input.setFocus()
        self.url_input.selectAll()

    def _current_options(self) -> DownloadOptions:
        return self.config.settings.options(self._fmt, self._quality)

    def _add_current(self) -> None:
        text = self.url_input.text().strip()
        if not text:
            self.url_input.setFocus()
            return
        added = self.add_from_text(text)
        if added:
            self.url_input.clear()

    def add_from_text(self, text: str) -> bool:
        urls = extract_urls(text)
        if not urls:
            self._toast("No se han encontrado enlaces válidos en el texto.", "warning", "Sin enlaces")
            return False
        urls = urls[:300]
        options = self._current_options()
        playlists: list[str] = []
        normal: list[str] = []
        for url in urls:
            if is_playlist_url(url) or (self.config.settings.include_playlist and PLAYLIST_RE.search(url)):
                playlists.append(url)
            else:
                normal.append(url)
        if normal:
            jobs = self.manager.add_job_urls(normal, options)
            if jobs:
                self._toast(f"{len(jobs)} enlace{'s' if len(jobs) != 1 else ''} añadido{'s' if len(jobs) != 1 else ''} a la cola.", "success", "Cola actualizada")
        for url in playlists:
            request_id = self.manager.resolve_playlist(url, options)
            self._pending_playlists[request_id] = url
        if playlists:
            self._toast("Analizando la lista de reproducción…", "info", "Un momento")
        return bool(normal or playlists)

    def add_files(self, paths: list[str]) -> None:
        found: list[str] = []
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            found.extend(extract_urls(content))
        if found:
            added = self.add_from_text("\n".join(found))
            if added:
                self._toast(f"Se importaron {len(found)} enlaces desde el archivo.", "success", "Importación completada")
        else:
            self._toast("No se encontraron enlaces en los archivos arrastrados.", "warning", "Sin enlaces")

    def _paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text().strip()
        if not text:
            self._toast("El portapapeles está vacío.", "warning", "Nada que pegar")
            return
        if extract_urls(text):
            if self.add_from_text(text):
                self.url_input.clear()
        else:
            self.url_input.setText(text)
            self.url_input.setFocus()
            self._toast("El portapapeles no contiene enlaces.", "warning", "Revisa el texto")

    def _import_file(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Importar enlaces",
            str(Path.home()),
            "Listas y texto (*.txt *.m3u *.m3u8 *.url *.csv);;Todos los archivos (*)",
        )
        if files:
            self.add_files(files)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Elegir carpeta de destino", self.config.settings.outdir)
        if folder:
            self.config.update(outdir=folder)
            self.folder_label.setText(folder)
            try:
                Path(folder).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            self._toast("Carpeta de destino actualizada.", "success")

    def _on_format_changed(self, index: int) -> None:
        if index < 0:
            return
        value = self.format_combo.itemData(index)
        if not value:
            return
        self._fmt = MediaFormat.from_value(value)
        self.config.update(default_format=self._fmt.value)
        self._update_quality_items()
        self._update_format_hint()

    def _on_quality_changed(self, index: int) -> None:
        if index < 0:
            return
        value = self.quality_combo.itemData(index)
        if not value:
            return
        self._quality = value
        if self._fmt is MediaFormat.MP4:
            self.config.update(mp4_quality=value)
        else:
            self.config.update(mp3_quality=value)
        self._update_format_hint()

    def _switch_kind(self, kind: str) -> None:
        if kind == "video":
            self._fmt = MediaFormat.MP4
            self._quality = self.config.settings.mp4_quality
        else:
            default = MediaFormat.from_value(self.config.settings.default_format)
            self._fmt = default if default is not MediaFormat.MP4 else MediaFormat.MP3
            self._quality = self.config.settings.mp3_quality
        self._select_format(self._fmt)

    def _select_format(self, fmt: MediaFormat, persist: bool = True) -> None:
        self._fmt = fmt
        is_video = fmt is MediaFormat.MP4
        self.audio_seg.setChecked(not is_video)
        self.video_seg.setChecked(is_video)
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        for label, value in (VIDEO_FORMATS if is_video else AUDIO_FORMATS):
            self.format_combo.addItem(label, value)
        index = self.format_combo.findData(fmt.value)
        self.format_combo.setCurrentIndex(max(0, index))
        self.format_combo.setEnabled(not is_video)
        self.format_combo.blockSignals(False)
        self._quality = self.config.settings.quality_for(fmt)
        self._update_quality_items()
        self._update_format_hint()
        if persist:
            self.config.update(default_format=fmt.value)

    def _update_quality_items(self) -> None:
        is_video = self._fmt is MediaFormat.MP4
        items = VIDEO_QUALITIES if is_video else AUDIO_QUALITIES
        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()
        for label, value in items:
            self.quality_combo.addItem(label, value)
        index = self.quality_combo.findData(self._quality)
        if index < 0:
            index = 0
            self._quality = self.quality_combo.itemData(0)
        self.quality_combo.setCurrentIndex(index)
        self.quality_combo.blockSignals(False)

    def _update_format_hint(self) -> None:
        fmt = self._fmt
        if fmt is MediaFormat.MP4:
            resolution = "la mejor disponible" if self._quality == "best" else f"{self._quality}p"
            self.format_hint.setText(f"Vídeo MP4 · {resolution} · H.264 + AAC para máxima compatibilidad.")
        elif fmt is MediaFormat.MP3:
            mb_min = (int(self._quality or 320) * 60 / 8) / 1024
            self.format_hint.setText(f"Audio MP3 · {self._quality} kbps · ≈ {mb_min:.1f} MB por minuto.")
        else:
            self.format_hint.setText(f"Audio {fmt.label} · se conservará la mejor calidad disponible del enlace.")

    def _toggle_option(self, key: str, checked: bool) -> None:
        self.config.update(**{key: checked})
        if key in ("embed_thumbnail", "embed_metadata", "normalize_audio", "sponsorblock", "write_subtitles"):
            self._toast(
                f"{'Activado' if checked else 'Desactivado'}: "
                + {
                    "embed_thumbnail": "portada incrustada",
                    "embed_metadata": "metadatos",
                    "normalize_audio": "normalización de volumen",
                    "sponsorblock": "SponsorBlock",
                    "write_subtitles": "subtítulos",
                }[key],
                "info",
            )

    def _toggle_auto_start(self, checked: bool) -> None:
        self.config.update(auto_start=checked)
        self.manager.set_auto_start(checked)

    def _change_concurrency(self, delta: int) -> None:
        current = int(self.config.settings.concurrency)
        value = max(1, min(6, current + delta))
        if value == current:
            return
        self.config.update(concurrency=value)
        self.concurrency_value.setText(str(value))
        self.manager.set_concurrency(value)

    def _set_filter(self, key: str) -> None:
        self._filter = key
        self._apply_filter()

    def _apply_filter(self) -> None:
        visible = 0
        for card in self.cards.values():
            status = card.job.status
            if self._filter == "all":
                show = True
            elif self._filter == "active":
                show = status in (JobStatus.QUEUED, JobStatus.PROBING, JobStatus.DOWNLOADING, JobStatus.PROCESSING)
            elif self._filter == "done":
                show = status is JobStatus.DONE
            else:
                show = status in (JobStatus.ERROR, JobStatus.CANCELLED)
            card.setVisible(show)
            visible += int(show)
        self.empty_state.setVisible(visible == 0)
        self.count_label.setText(f"{len(self.cards)} elemento{'s' if len(self.cards) != 1 else ''}")
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        if self._filter == "all":
            self.empty_state.title.setText("Tu cola está vacía")
            self.empty_state.subtitle.setText("Arrastra enlaces aquí o pega una URL para empezar a convertir.")
        elif self._filter == "active":
            self.empty_state.title.setText("No hay descargas en curso")
            self.empty_state.subtitle.setText("Añade nuevos enlaces o comprueba los elementos completados.")
        elif self._filter == "done":
            self.empty_state.title.setText("Aún no hay nada completado")
            self.empty_state.subtitle.setText("Cuando termine una descarga aparecerá aquí y en tu biblioteca.")
        else:
            self.empty_state.title.setText("Todo ha ido bien")
            self.empty_state.subtitle.setText("No hay errores ni descargas canceladas en la cola.")

    def _retry_failed(self) -> None:
        count = self.manager.retry_failed()
        if count:
            self._toast(f"Reintentando {count} descarga{'s' if count != 1 else ''}.", "info")
        else:
            self._toast("No hay descargas fallidas.", "info")

    def _clear_finished(self) -> None:
        finished = [card.job_id for card in self.cards.values() if card.job.status.is_finished]
        if not finished:
            self._toast("No hay elementos terminados que vaciar.", "info")
            return
        for job_id in finished:
            self.manager.remove(job_id)
        self._toast(f"{len(finished)} elemento{'s' if len(finished) != 1 else ''} eliminado{'s' if len(finished) != 1 else ''} de la cola.", "info")

    def _toggle_queue(self) -> None:
        if self.manager.paused:
            self.manager.resume()
        else:
            active = any(job.status.is_active for job in self.manager.jobs.values())
            queued = any(job.status is JobStatus.QUEUED for job in self.manager.jobs.values())
            if active or queued:
                self.manager.pause()
            else:
                self.manager.start_queue()
        self._refresh_pause_button()

    def _refresh_pause_button(self) -> None:
        active = any(job.status.is_active for job in self.manager.jobs.values())
        queued = any(job.status is JobStatus.QUEUED for job in self.manager.jobs.values())
        if self.manager.paused:
            self.pause_button.setText("Reanudar cola")
            self.pause_button.setIcon(make_icon("play", "#FFFFFF", 16))
            self.pause_button.setEnabled(True)
        elif active:
            self.pause_button.setText("Pausar cola")
            self.pause_button.setIcon(make_icon("pause", "#FFFFFF", 16))
            self.pause_button.setEnabled(True)
        elif queued:
            self.pause_button.setText("Iniciar cola")
            self.pause_button.setIcon(make_icon("play", "#FFFFFF", 16))
            self.pause_button.setEnabled(True)
        else:
            self.pause_button.setText("Iniciar cola")
            self.pause_button.setIcon(make_icon("play", "#FFFFFF", 16))
            self.pause_button.setEnabled(False)

    def _cancel_all(self) -> None:
        active = [job for job in self.manager.jobs.values() if job.status in (JobStatus.QUEUED, JobStatus.PROBING, JobStatus.DOWNLOADING, JobStatus.PROCESSING)]
        if not active:
            self._toast("No hay descargas activas que cancelar.", "info")
            return
        dialog = ConfirmDialog(
            "Cancelar todas las descargas",
            f"Se cancelarán {len(active)} descarga(s) en curso o pendientes. Los archivos ya descargados se conservarán.",
            self,
            "Cancelar todo",
            danger=True,
        )
        if dialog.exec():
            self.manager.cancel_all()
            self._toast("Descargas canceladas.", "warning")

    # ----------------------------------------------------------------- eventos
    def _on_job_added(self, job_id: str) -> None:
        job = self.manager.jobs.get(job_id)
        if not job or job_id in self.cards:
            return
        card = JobCard(job, self.thumbs)
        card.cancelRequested.connect(self.manager.cancel)
        card.retryRequested.connect(self.manager.retry)
        card.removeRequested.connect(self.manager.remove)
        card.folderRequested.connect(lambda jid: self._open_folder(jid))
        card.playRequested.connect(lambda jid: self._play(jid))
        self.cards[job_id] = card
        self.queue_layout.addWidget(card)
        self._apply_filter()
        self._refresh_pause_button()

    def _on_job_updated(self, job_id: str) -> None:
        card = self.cards.get(job_id)
        job = self.manager.jobs.get(job_id)
        if not card or not job:
            return
        card.update_from(job)
        self._apply_filter()
        self._refresh_pause_button()

    def _on_job_removed(self, job_id: str) -> None:
        card = self.cards.pop(job_id, None)
        if card:
            self.queue_layout.removeWidget(card)
            card.deleteLater()
        self._apply_filter()
        self._refresh_pause_button()

    def _on_thumb_loaded(self, job_id: str, pixmap: QPixmap) -> None:
        card = self.cards.get(job_id)
        if card:
            card.set_thumbnail(pixmap)

    def _on_stats(self, stats: dict) -> None:
        overall = float(stats.get("overall") or 0)
        self.overall_bar.setValue(overall)
        total = int(stats.get("total") or 0)
        done = int(stats.get("done") or 0)
        active = int(stats.get("active") or 0)
        queued = int(stats.get("queued") or 0)
        errors = int(stats.get("errors") or 0)
        if total == 0:
            text = "—"
            tooltip = "Sin descargas"
        else:
            text = f"{overall:.0f}%"
            parts = [f"{done} de {total} completados"]
            if active:
                parts.append(f"{active} activa{'s' if active != 1 else ''}")
            if queued:
                parts.append(f"{queued} en cola")
            if errors:
                parts.append(f"{errors} con error")
            tooltip = " · ".join(parts) + f" · {overall:.0f}%"
        self.overall_label.setText(text)
        self.overall_label.setToolTip(tooltip)
        self.speed_label.setText(format_speed(stats.get("speed") or 0))
        self.eta_label.setText(format_eta(stats.get("eta") or 0))
        self.size_label.setText(format_bytes(stats.get("completed_size") or 0))
        self.cancel_all_button.setEnabled(active > 0 or queued > 0)
        self._refresh_pause_button()

    def _on_playlist_resolved(self, request_id: str, info: dict) -> None:
        self._pending_playlists.pop(request_id, None)
        entries = info.get("entries") or []
        if not info.get("is_playlist") or not entries:
            url = info.get("webpage_url") or info.get("url") or ""
            if url:
                self.add_from_text(url)
            return
        dialog = PlaylistDialog(info, self)
        if dialog.exec():
            selected = dialog.selected_entries()
            if selected:
                jobs = self.manager.add_playlist_entries(selected, self._current_options())
                self._toast(f"{len(jobs)} elementos de la lista añadidos a la cola.", "success", "Lista importada")

    def _on_playlist_failed(self, request_id: str, error: str) -> None:
        self._pending_playlists.pop(request_id, None)
        self._toast(error, "error", "No se pudo leer la lista")

    def _open_folder(self, job_id: str) -> None:
        job = self.manager.jobs.get(job_id)
        if job and job.filepath:
            open_in_file_manager(job.filepath)
        else:
            open_in_file_manager(self.config.settings.outdir)

    def _play(self, job_id: str) -> None:
        job = self.manager.jobs.get(job_id)
        if job and job.filepath:
            open_media(job.filepath)

    def refresh_theme(self) -> None:
        for card in self.cards.values():
            card.refresh_theme()
        self.empty_state.title.style().unpolish(self.empty_state.title)
        self.empty_state.title.style().polish(self.empty_state.title)
        self.update()
