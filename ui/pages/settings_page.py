"""Página de ajustes con guardado automático."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import ACCENTS, ConfigStore, Settings
from core.downloader import engine_version, ffmpeg_location, parse_rate_limit
from core.manager import DownloadManager
from core.utils import cache_home, config_home, data_home, open_in_file_manager
from ui.dialogs import ConfirmDialog
from ui.icons import make_icon
from ui.theme import theme
from ui.widgets import ElidedLabel, SettingRow, ToggleSwitch, divider, icon_button

ToastFn = Callable[..., None]


class AccentSwatch(QAbstractButton):
    def __init__(self, accent: str, accent2: str, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.accent = accent
        self.accent2 = accent2
        self.setCheckable(True)
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(3, 3, -3, -3)
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, QColor(self.accent))
        grad.setColorAt(1, QColor(self.accent2))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(rect)
        if self.isChecked():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(theme().text), 2))
            painter.drawEllipse(rect.adjusted(-2, -2, 2, 2))
            icon = make_icon("check", "#FFFFFF", 14, 2.6)
            icon.paint(painter, rect.adjusted(5, 5, -5, -5))


class _UpdateSignals(QObject):
    done = Signal(str)
    failed = Signal(str)


class _EngineUpdateWorker(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = _UpdateSignals()

    def run(self) -> None:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                self.signals.done.emit(engine_version())
            else:
                self.signals.failed.emit((result.stderr or result.stdout or "pip falló")[-400:])
        except Exception as exc:
            self.signals.failed.emit(str(exc)[:400])


class SettingsPage(QWidget):
    def __init__(
        self,
        manager: DownloadManager,
        config: ConfigStore,
        toast: ToastFn,
        theme_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.config = config
        self._toast = toast
        self._theme_changed = theme_changed
        self.setObjectName("Transparent")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        notice = QFrame()
        notice.setObjectName("CardSoft")
        nlayout = QHBoxLayout(notice)
        nlayout.setContentsMargins(12, 8, 12, 8)
        nlayout.setSpacing(8)
        check = QLabel()
        check.setPixmap(make_icon("check-circle", theme().success, 16).pixmap(16, 16))
        nlayout.addWidget(check)
        text = QLabel("Los cambios se guardan automáticamente. Algunas opciones se aplican a las nuevas descargas.")
        text.setObjectName("MutedSmall")
        nlayout.addWidget(text, 1)
        outer.addWidget(notice)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("Transparent")
        columns = QHBoxLayout(content)
        columns.setContentsMargins(0, 2, 8, 10)
        columns.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)
        right = QVBoxLayout()
        right.setSpacing(14)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)

        left.addWidget(self._build_appearance())
        left.addWidget(self._build_downloads())
        left.addWidget(self._build_audio_video())
        left.addStretch()

        right.addWidget(self._build_advanced())
        right.addWidget(self._build_system())
        right.addWidget(self._build_data())
        right.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    # -------------------------------------------------------------- helpers
    def _save(self, **kwargs) -> None:
        self.config.update(**kwargs)

    def _card(self, icon_name: str, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 15, 17, 15)
        layout.setSpacing(6)
        header = QHBoxLayout()
        header.setSpacing(9)
        icon = QLabel()
        icon.setPixmap(make_icon(icon_name, theme().accent, 18).pixmap(18, 18))
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        label = QLabel(title)
        label.setObjectName("H2")
        col.addWidget(label)
        sub = QLabel(subtitle)
        sub.setObjectName("MutedSmall")
        sub.setWordWrap(True)
        col.addWidget(sub)
        header.addLayout(col, 1)
        layout.addLayout(header)
        layout.addSpacing(4)
        return card, layout

    def _combo(self, items: list[tuple[str, str]], current: str, on_change, width: int = 190) -> QComboBox:
        combo = QComboBox()
        combo.setFixedWidth(width)
        for label, value in items:
            combo.addItem(label, value)
        index = combo.findData(current)
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(lambda i: on_change(combo.itemData(i)))
        return combo

    def _toggle(self, checked: bool, on_change, key: str) -> ToggleSwitch:
        toggle = ToggleSwitch()
        toggle.setChecked(checked)
        toggle.toggled.connect(lambda value: self._save(**{key: value}))
        if on_change:
            toggle.toggled.connect(on_change)
        return toggle

    # ------------------------------------------------------------- secciones
    def _build_appearance(self) -> QFrame:
        settings = self.config.settings
        card, layout = self._card("sun", "Apariencia", "Personaliza el aspecto de Sonora")
        theme_row = QWidget()
        row = QHBoxLayout(theme_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        frame = QFrame()
        frame.setObjectName("CardSoft")
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(4, 4, 4, 4)
        frame_layout.setSpacing(3)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self._theme_group = group
        for value, text, icon_name in (("dark", "Oscuro", "moon"), ("light", "Claro", "sun"), ("system", "Sistema", "cpu")):
            button = QPushButton(text)
            button.setProperty("segment", "true")
            button.setCheckable(True)
            button.setIcon(make_icon(icon_name, theme().muted, 15))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(settings.theme == value)
            button.clicked.connect(lambda _, v=value: self._set_theme(v))
            group.addButton(button)
            frame_layout.addWidget(button)
        layout.addWidget(frame)

        accent_row = QWidget()
        accent_layout = QHBoxLayout(accent_row)
        accent_layout.setContentsMargins(0, 2, 0, 4)
        accent_layout.setSpacing(9)
        accent_layout.addWidget(QLabel("Color de acento"))
        accent_layout.addStretch()
        self._accent_group = QButtonGroup(self)
        self._accent_group.setExclusive(True)
        for name, (first, second) in ACCENTS.items():
            swatch = AccentSwatch(first, second, name)
            swatch.setChecked(first.lower() == settings.accent.lower())
            swatch.clicked.connect(lambda _, c=first: self._set_accent(c))
            self._accent_group.addButton(swatch)
            accent_layout.addWidget(swatch)
        layout.addWidget(accent_row)
        return card

    def _set_theme(self, value: str) -> None:
        self._save(theme=value)
        self._theme_changed()

    def _set_accent(self, value: str) -> None:
        self._save(accent=value)
        self._theme_changed()

    def _build_downloads(self) -> QFrame:
        settings = self.config.settings
        card, layout = self._card("download", "Descargas", "Carpeta, nombres y comportamiento de la cola")

        folder_line = QWidget()
        fl = QHBoxLayout(folder_line)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(7)
        self._folder_label = ElidedLabel(settings.outdir)
        self._folder_label.setObjectName("Muted")
        fl.addWidget(self._folder_label, 1)
        change = QPushButton("Cambiar")
        change.setProperty("variant", "soft")
        change.clicked.connect(self._choose_folder)
        fl.addWidget(change)
        layout.addWidget(SettingRow("Carpeta de destino", "Los archivos se guardarán aquí", folder_line))

        template = QLineEdit(settings.filename_template)
        template.setPlaceholderText("%(title)s")
        template.setFixedWidth(210)
        template.setToolTip("Variables disponibles: %(title)s, %(uploader)s, %(id)s, %(playlist_title)s")
        template.editingFinished.connect(lambda: self._save(filename_template=template.text().strip() or "%(title)s"))
        layout.addWidget(SettingRow("Plantilla de nombre", "%(title)s, %(uploader)s, %(id)s…", template))

        concurrency = QSpinBox()
        concurrency.setRange(1, 6)
        concurrency.setValue(settings.concurrency)
        concurrency.setFixedWidth(72)
        concurrency.valueChanged.connect(self._set_concurrency)
        layout.addWidget(SettingRow("Descargas simultáneas", "De 1 a 6 descargas a la vez", concurrency))

        layout.addWidget(divider())
        layout.addWidget(
            SettingRow("Inicio automático", "Comenzar las descargas al añadirlas", self._toggle(settings.auto_start, self._auto_start_changed, "auto_start"))
        )
        layout.addWidget(
            SettingRow(
                "Playlists completas",
                "Los enlaces con ?list= descargan toda la lista",
                self._toggle(settings.include_playlist, None, "include_playlist"),
            )
        )
        layout.addWidget(
            SettingRow(
                "Nombres compatibles",
                "Elimina caracteres especiales y tildes del nombre",
                self._toggle(settings.restrict_filenames, None, "restrict_filenames"),
            )
        )
        return card

    def _set_concurrency(self, value: int) -> None:
        self._save(concurrency=value)
        self.manager.set_concurrency(value)

    def _auto_start_changed(self, value: bool) -> None:
        self.manager.set_auto_start(value)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Elegir carpeta de destino", self.config.settings.outdir)
        if folder:
            self._save(outdir=folder)
            self._folder_label.setText(folder)
            Path(folder).mkdir(parents=True, exist_ok=True)
            self._toast("Carpeta de destino actualizada.", "success")

    def _build_audio_video(self) -> QFrame:
        settings = self.config.settings
        card, layout = self._card("music", "Audio y vídeo", "Valores predeterminados para nuevas descargas")
        formats = [("MP3", "mp3"), ("M4A", "m4a"), ("FLAC", "flac"), ("WAV", "wav"), ("OPUS", "opus"), ("MP4 (vídeo)", "mp4")]
        format_combo = self._combo(formats, settings.default_format, lambda v: self._save(default_format=v), 150)
        layout.addWidget(SettingRow("Formato predeterminado", "Se preselecciona en el descargador", format_combo))

        audio_qualities = [("320 kbps · máxima", "320"), ("256 kbps", "256"), ("192 kbps", "192"), ("128 kbps", "128")]
        mp3_combo = self._combo(audio_qualities, settings.mp3_quality, lambda v: self._save(mp3_quality=v), 170)
        layout.addWidget(SettingRow("Calidad de audio", "Bitrate para MP3, M4A y OPUS", mp3_combo))

        video_qualities = [("Mejor disponible", "best"), ("2160p · 4K", "2160"), ("1440p", "1440"), ("1080p", "1080"), ("720p", "720"), ("480p", "480"), ("360p", "360")]
        mp4_combo = self._combo(video_qualities, settings.mp4_quality, lambda v: self._save(mp4_quality=v), 170)
        layout.addWidget(SettingRow("Calidad de vídeo", "Altura máxima para MP4", mp4_combo))

        layout.addWidget(divider())
        layout.addWidget(
            SettingRow("Portada incrustada", "Miniatura como carátula del archivo", self._toggle(settings.embed_thumbnail, None, "embed_thumbnail"))
        )
        layout.addWidget(
            SettingRow("Metadatos", "Título, artista, álbum y capítulos", self._toggle(settings.embed_metadata, None, "embed_metadata"))
        )
        layout.addWidget(
            SettingRow("Normalizar volumen", "Loudness uniforme a -14 LUFS", self._toggle(settings.normalize_audio, None, "normalize_audio"))
        )
        layout.addWidget(
            SettingRow("SponsorBlock", "Elimina patrocinios del audio y el vídeo", self._toggle(settings.sponsorblock, None, "sponsorblock"))
        )
        layout.addWidget(
            SettingRow("Descargar subtítulos", "Archivos .srt junto al vídeo", self._toggle(settings.write_subtitles, None, "write_subtitles"))
        )

        langs = QLineEdit(settings.subtitle_langs)
        langs.setPlaceholderText("es,en")
        langs.setFixedWidth(120)
        langs.editingFinished.connect(lambda: self._save(subtitle_langs=langs.text().strip() or "es,en"))
        layout.addWidget(SettingRow("Idiomas de subtítulos", "Códigos separados por comas", langs))

        trim_row = QWidget()
        trim_layout = QHBoxLayout(trim_row)
        trim_layout.setContentsMargins(0, 0, 0, 0)
        trim_layout.setSpacing(6)
        self.trim_start = QDoubleSpinBox()
        self.trim_start.setRange(0, 36000)
        self.trim_start.setDecimals(1)
        self.trim_start.setSuffix(" s")
        self.trim_start.setValue(float(settings.trim_start or 0))
        self.trim_start.setFixedWidth(90)
        self.trim_end = QDoubleSpinBox()
        self.trim_end.setRange(0, 36000)
        self.trim_end.setDecimals(1)
        self.trim_end.setSuffix(" s")
        self.trim_end.setValue(float(settings.trim_end or 0))
        self.trim_end.setFixedWidth(90)
        trim_layout.addWidget(QLabel("Desde"))
        trim_layout.addWidget(self.trim_start)
        trim_layout.addWidget(QLabel("hasta"))
        trim_layout.addWidget(self.trim_end)
        self.trim_start.valueChanged.connect(lambda v: self._save(trim_start=float(v)))
        self.trim_end.valueChanged.connect(lambda v: self._save(trim_end=float(v)))
        layout.addWidget(SettingRow("Recortar audio/vídeo", "0 = sin recorte; tiempo en segundos", trim_row))
        return card

    def _build_advanced(self) -> QFrame:
        settings = self.config.settings
        card, layout = self._card("cpu", "Avanzado", "Opciones para enlaces difíciles o redes lentas")

        cookies_row = QWidget()
        cookies_layout = QHBoxLayout(cookies_row)
        cookies_layout.setContentsMargins(0, 0, 0, 0)
        cookies_layout.setSpacing(6)
        self.cookies_label = ElidedLabel(Path(settings.cookies_file).name if settings.cookies_file else "Sin archivo")
        self.cookies_label.setObjectName("MutedSmall")
        self.cookies_label.setMinimumWidth(150)
        cookies_layout.addWidget(self.cookies_label, 1)
        pick = icon_button("file-text", "Seleccionar cookies.txt", theme().muted, 16)
        pick.clicked.connect(self._choose_cookies)
        clear = icon_button("x", "Quitar cookies", theme().muted, 16)
        clear.clicked.connect(self._clear_cookies)
        cookies_layout.addWidget(pick)
        cookies_layout.addWidget(clear)
        layout.addWidget(SettingRow("Cookies del navegador", "Para vídeos con restricción de edad", cookies_row))

        proxy = QLineEdit(settings.proxy)
        proxy.setPlaceholderText("http://127.0.0.1:8080")
        proxy.setFixedWidth(220)
        proxy.editingFinished.connect(lambda: self._save(proxy=proxy.text().strip()))
        layout.addWidget(SettingRow("Proxy", "Se aplica a yt-dlp", proxy))

        rate = QLineEdit(settings.rate_limit)
        rate.setPlaceholderText("p. ej. 2M o 500K")
        rate.setFixedWidth(130)
        rate.editingFinished.connect(lambda: self._validate_rate(rate))
        layout.addWidget(SettingRow("Límite de velocidad", "Vacío = sin límite", rate))
        self._rate_input = rate

        retries = QSpinBox()
        retries.setRange(0, 10)
        retries.setValue(settings.retries)
        retries.setFixedWidth(72)
        retries.valueChanged.connect(lambda v: self._save(retries=v))
        layout.addWidget(SettingRow("Reintentos de red", "Por fragmento o descarga", retries))

        layout.addWidget(divider())
        engine_row = QWidget()
        engine_layout = QHBoxLayout(engine_row)
        engine_layout.setContentsMargins(0, 0, 0, 0)
        engine_layout.setSpacing(8)
        self.engine_label = QLabel(f"yt-dlp {engine_version()}")
        self.engine_label.setObjectName("MutedSmall")
        engine_layout.addWidget(self.engine_label, 1)
        self.update_button = QPushButton("Actualizar motor")
        self.update_button.setProperty("variant", "ghost")
        self.update_button.setIcon(make_icon("refresh", theme().muted, 15))
        self.update_button.clicked.connect(self._update_engine)
        engine_layout.addWidget(self.update_button)
        layout.addWidget(SettingRow("Motor de descarga", "Actualiza yt-dlp a la última versión", engine_row))

        ff = ffmpeg_location() or "No encontrado"
        ff_label = ElidedLabel(ff)
        ff_label.setObjectName("MutedSmall")
        ff_label.setToolTip(ff)
        ff_label.setMinimumWidth(160)
        layout.addWidget(SettingRow("FFmpeg", "Binario usado para convertir y unir pistas", ff_label))
        return card

    def _choose_cookies(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "Seleccionar cookies.txt", str(Path.home()), "Cookies (*.txt);;Todos los archivos (*)")
        if file:
            self._save(cookies_file=file)
            self.cookies_label.setText(Path(file).name)
            self._toast("Archivo de cookies configurado.", "success")

    def _clear_cookies(self) -> None:
        self._save(cookies_file="")
        self.cookies_label.setText("Sin archivo")

    def _validate_rate(self, widget: QLineEdit) -> None:
        value = widget.text().strip()
        if value and parse_rate_limit(value) is None:
            self._toast("Formato no válido. Usa por ejemplo 2M, 500K o 800000.", "warning", "Límite de velocidad")
            widget.setText(self.config.settings.rate_limit)
            return
        self._save(rate_limit=value)

    def _update_engine(self) -> None:
        self.update_button.setEnabled(False)
        self.update_button.setText("Actualizando…")
        worker = _EngineUpdateWorker()
        worker.signals.done.connect(self._engine_updated)
        worker.signals.failed.connect(self._engine_failed)
        QThreadPool.globalInstance().start(worker)
        self._update_worker = worker

    def _engine_updated(self, version: str) -> None:
        self.update_button.setEnabled(True)
        self.update_button.setText("Actualizar motor")
        self.engine_label.setText(f"yt-dlp {version} (reinicia para aplicar)")
        self._toast("yt-dlp se ha actualizado. Reinicia Sonora para usar la nueva versión.", "success", "Motor actualizado")

    def _engine_failed(self, error: str) -> None:
        self.update_button.setEnabled(True)
        self.update_button.setText("Actualizar motor")
        self._toast(error, "error", "No se pudo actualizar")

    def _build_system(self) -> QFrame:
        settings = self.config.settings
        card, layout = self._card("bell", "Sistema", "Notificaciones y comportamiento de la ventana")
        layout.addWidget(
            SettingRow("Notificaciones", "Avisar al completar una descarga", self._toggle(settings.notifications, None, "notifications"))
        )
        layout.addWidget(
            SettingRow(
                "Vigilar el portapapeles",
                "Añade automáticamente enlaces copiados",
                self._toggle(settings.clipboard_watch, None, "clipboard_watch"),
            )
        )
        layout.addWidget(
            SettingRow("Cerrar a la bandeja", "Sonora sigue en segundo plano al cerrar", self._toggle(settings.close_to_tray, None, "close_to_tray"))
        )
        return card

    def _build_data(self) -> QFrame:
        card, layout = self._card("terminal", "Datos y mantenimiento", "Rutas y restablecimiento de la aplicación")
        for label, path in (("Ajustes", config_home()), ("Historial", data_home()), ("Caché", cache_home())):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            elided = ElidedLabel(str(path))
            elided.setObjectName("MutedSmall")
            elided.setToolTip(str(path))
            row_layout.addWidget(elided, 1)
            open_button = icon_button("folder-open", f"Abrir {label.lower()}", theme().muted, 15)
            open_button.clicked.connect(lambda _, p=path: open_in_file_manager(p))
            row_layout.addWidget(open_button)
            layout.addWidget(SettingRow(label, "", row))

        layout.addWidget(divider())
        danger_row = QWidget()
        danger_layout = QHBoxLayout(danger_row)
        danger_layout.setContentsMargins(0, 0, 0, 0)
        danger_layout.addStretch()
        reset = QPushButton("Restablecer ajustes")
        reset.setProperty("variant", "danger")
        reset.clicked.connect(self._reset)
        danger_layout.addWidget(reset)
        layout.addWidget(SettingRow("Volver a los valores de fábrica", "No borra las descargas ni la biblioteca", danger_row))
        return card

    def _reset(self) -> None:
        dialog = ConfirmDialog(
            "Restablecer ajustes",
            "Se restaurarán todos los ajustes por defecto. Las descargas, la biblioteca y el historial se conservarán.",
            self,
            "Restablecer",
            danger=True,
        )
        if not dialog.exec():
            return
        self.config.settings = Settings()
        self.config.save()
        self.manager.set_concurrency(self.config.settings.concurrency)
        self.manager.set_auto_start(self.config.settings.auto_start)
        self._toast("Ajustes restablecidos. Algunos cambios se aplicarán al reiniciar.", "success")
        self._theme_changed()

    def refresh_theme(self) -> None:
        for swatch in self._accent_group.buttons():
            swatch.update()
        self.update()
