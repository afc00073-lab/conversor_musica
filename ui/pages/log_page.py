"""Registro de actividad del motor de descarga."""

from __future__ import annotations

import html
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.downloader import engine_version, ffmpeg_location
from core.manager import DownloadManager
from ui.icons import make_icon
from ui.theme import theme
from ui.widgets import ToggleSwitch, icon_button

ToastFn = Callable[..., None]

LEVELS = {
    "debug": ("Depuración", "#7C879E"),
    "info": ("Info", "#8CE99A"),
    "success": ("OK", "#34D399"),
    "warning": ("Aviso", "#FBBF24"),
    "error": ("Error", "#FB7185"),
}


class LogPage(QWidget):
    def __init__(self, manager: DownloadManager, toast: ToastFn, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._toast = toast
        self.entries: list[tuple[str, str, str]] = []
        self._level_filter = "all"
        self._search = ""
        self.setObjectName("Transparent")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        stats.addWidget(self._info_box("cpu", "Motor yt-dlp", engine_version(), theme().success))
        ff = "Integrado y listo" if ffmpeg_location() else "No encontrado"
        stats.addWidget(self._info_box("volume", "FFmpeg", ff, theme().success if ffmpeg_location() else theme().error))
        js = next((name for name in ("deno", "node", "bun", "qjs") if shutil.which(name)), "")
        stats.addWidget(
            self._info_box(
                "terminal",
                "Runtime JavaScript",
                js or "Opcional · no detectado",
                theme().success if js else theme().warning,
            )
        )
        layout.addLayout(stats)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar mensajes…")
        self.search.setFixedWidth(260)
        self.search.addAction(make_icon("search", theme().muted2, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search)

        self.level_combo = QComboBox()
        self.level_combo.setFixedWidth(135)
        for label, value in (("Todo", "all"), ("Información", "info"), ("Avisos", "warning"), ("Errores", "error")):
            self.level_combo.addItem(label, value)
        self.level_combo.currentIndexChanged.connect(self._on_level)
        toolbar.addWidget(self.level_combo)
        toolbar.addStretch()

        autoscroll_label = QLabel("Auto-scroll")
        autoscroll_label.setObjectName("MutedSmall")
        toolbar.addWidget(autoscroll_label)
        self.autoscroll = ToggleSwitch()
        self.autoscroll.setChecked(True)
        toolbar.addWidget(self.autoscroll)

        copy = icon_button("clipboard", "Copiar registro", theme().muted, 16)
        copy.clicked.connect(self._copy)
        toolbar.addWidget(copy)
        save = icon_button("download", "Guardar registro en un archivo", theme().muted, 16)
        save.clicked.connect(self._save)
        toolbar.addWidget(save)
        clear = icon_button("eraser", "Limpiar registro", theme().muted, 16)
        clear.clicked.connect(self.clear)
        toolbar.addWidget(clear)
        layout.addLayout(toolbar)

        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(QFont("DejaVu Sans Mono", 9))
        self.view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.view.document().setMaximumBlockCount(3000)
        layout.addWidget(self.view, 1)

        self.manager.logMessage.connect(self.append)
        self.append("info", "Sonora iniciada. Esperando enlaces…")

    def _info_box(self, icon_name: str, title: str, value: str, color: str) -> QFrame:
        box = QFrame()
        box.setObjectName("CardSoft")
        row = QHBoxLayout(box)
        row.setContentsMargins(13, 9, 13, 9)
        row.setSpacing(9)
        icon = QLabel()
        icon.setPixmap(make_icon(icon_name, theme().accent, 17).pixmap(17, 17))
        row.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        label = QLabel(title)
        label.setObjectName("MutedSmall")
        value_label = QLabel(value)
        value_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
        col.addWidget(label)
        col.addWidget(value_label)
        row.addLayout(col, 1)
        return box

    def _on_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self._render()

    def _on_level(self, index: int) -> None:
        self._level_filter = self.level_combo.itemData(index) or "all"
        self._render()

    def append(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = (message or "").strip()
        if not message:
            return
        self.entries.append((timestamp, level, message))
        if len(self.entries) > 1200:
            self.entries = self.entries[-1200:]
        if self._matches(level, message):
            self._append_html(timestamp, level, message)
            if self.autoscroll.isChecked():
                self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def _matches(self, level: str, message: str) -> bool:
        if self._level_filter == "info" and level not in ("info", "success", "debug"):
            return False
        if self._level_filter == "warning" and level != "warning":
            return False
        if self._level_filter == "error" and level != "error":
            return False
        if self._search and self._search not in message.lower():
            return False
        return True

    def _append_html(self, timestamp: str, level: str, message: str) -> None:
        label, color = LEVELS.get(level, ("Info", theme().muted))
        safe = html.escape(message).replace("\n", "<br>")
        self.view.append(
            f'<span style="color:{theme().muted2}">{timestamp}</span> '
            f'<span style="color:{color};font-weight:700">[{label}]</span> '
            f'<span style="color:{theme().text}">{safe}</span>'
        )

    def _render(self) -> None:
        self.view.clear()
        for timestamp, level, message in self.entries:
            if self._matches(level, message):
                self._append_html(timestamp, level, message)
        if self.autoscroll.isChecked():
            self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def clear(self) -> None:
        self.entries.clear()
        self.view.clear()

    def _copy(self) -> None:
        self.view.selectAll()
        self.view.copy()
        cursor = self.view.textCursor()
        cursor.clearSelection()
        self.view.setTextCursor(cursor)
        self._toast("Registro copiado al portapapeles.", "info")

    def _save(self) -> None:
        default = str(Path.home() / f"sonora-registro-{datetime.now():%Y%m%d-%H%M}.log")
        file, _ = QFileDialog.getSaveFileName(self, "Guardar registro", default, "Registro (*.log *.txt)")
        if not file:
            return
        lines = [f"{ts} [{lvl}] {msg}" for ts, lvl, msg in self.entries]
        Path(file).write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._toast("Registro guardado correctamente.", "success")

    def refresh_theme(self) -> None:
        self._render()
