"""Acerca de Sonora, créditos y atajos."""

from __future__ import annotations

import platform
import sys

import PySide6
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.config import APP_NAME, APP_TAGLINE, APP_VERSION, GITHUB_URL
from core.downloader import engine_version, ffmpeg_location
from core.utils import config_home, data_home
from ui.icons import make_icon, pixmap_from_svg_file
from ui.theme import theme
from ui.widgets import ElidedLabel, divider, icon_button


class AboutPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Transparent")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        content.setObjectName("Transparent")
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 18, 28, 30)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(30, 28, 30, 28)
        hero_layout.setSpacing(8)
        hero_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo = QLabel()
        logo.setPixmap(pixmap_from_svg_file(str(_icon_path()), 92))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(logo)
        title = QLabel(APP_NAME)
        font = QFont("Noto Sans Display", 30)
        font.setWeight(QFont.Weight.Bold)
        title.setFont(font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(title)
        version = QLabel(f"Versión {APP_VERSION}")
        version.setObjectName("Badge")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(version, 0, Qt.AlignmentFlag.AlignHCenter)
        tagline = QLabel(APP_TAGLINE)
        tagline.setObjectName("Muted")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(tagline)
        description = QLabel(
            "Un conversor de escritorio rápido, bonito y sin anuncios. Pega o arrastra enlaces, "
            "elige formato y deja que la cola haga el resto. Tu música y tus vídeos, organizados y listos."
        )
        description.setObjectName("Muted")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setFixedWidth(640)
        description.setMinimumHeight(50)
        hero_layout.addWidget(description, 0, Qt.AlignmentFlag.AlignHCenter)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()
        repo = QPushButton("Ver repositorio")
        repo.setProperty("variant", "primary")
        repo.setIcon(make_icon("external", "#FFFFFF", 16))
        repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        data = QPushButton("Abrir carpeta de datos")
        data.setProperty("variant", "ghost")
        data.setIcon(make_icon("folder", theme().muted, 16))
        data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_home()))))
        buttons.addWidget(repo)
        buttons.addWidget(data)
        buttons.addStretch()
        hero_layout.addSpacing(6)
        hero_layout.addLayout(buttons)
        layout.addWidget(hero)

        features_title = QLabel("Todo lo que puede hacer")
        features_title.setObjectName("H2")
        layout.addWidget(features_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        features = [
            ("zap", "Cola concurrente", "Varias descargas a la vez con progreso, velocidad y tiempo restante en tiempo real."),
            ("music", "Audio impecable", "MP3 hasta 320 kbps, M4A, FLAC, WAV y OPUS con portada y metadatos incrustados."),
            ("film", "Vídeo hasta 4K", "MP4 con la mejor pista disponible, fusión automática y compatibilidad total."),
            ("list-music", "Playlists y lotes", "Importa listas completas o suelta un .txt con cientos de enlaces de golpe."),
            ("library", "Biblioteca visual", "Historial con portadas, búsqueda, favoritos y acceso directo a tus archivos."),
            ("shield", "Sin anuncios ni cuentas", "Todo ocurre en tu equipo. Sin registro, sin nubes y sin telemetría."),
        ]
        for index, (icon_name, title_text, body) in enumerate(features):
            card = QFrame()
            card.setObjectName("Card")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 13, 14, 13)
            card_layout.setSpacing(11)
            bubble = QLabel()
            bubble.setFixedSize(38, 38)
            bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bubble.setStyleSheet(f"background-color: {theme().accent_soft}; border-radius: 11px;")
            bubble.setPixmap(make_icon(icon_name, theme().accent, 19).pixmap(19, 19))
            card_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(1)
            name = QLabel(title_text)
            name.setObjectName("H3")
            text = QLabel(body)
            text.setObjectName("MutedSmall")
            text.setWordWrap(True)
            col.addWidget(name)
            col.addWidget(text)
            card_layout.addLayout(col, 1)
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        shortcuts = QFrame()
        shortcuts.setObjectName("Card")
        sl = QVBoxLayout(shortcuts)
        sl.setContentsMargins(17, 15, 17, 15)
        sl.setSpacing(7)
        st = QLabel("Atajos de teclado")
        st.setObjectName("H2")
        sl.addWidget(st)
        for keys, action in (
            ("Ctrl + V", "Pegar enlace del portapapeles"),
            ("Ctrl + O", "Importar archivo .txt"),
            ("Ctrl + L", "Enfocar el campo de enlace"),
            ("Ctrl + 1…5", "Cambiar de sección"),
            ("Espacio", "Iniciar o pausar la cola"),
            ("F5", "Reintentar descargas fallidas"),
            ("Ctrl + ,", "Abrir ajustes"),
        ):
            row = QHBoxLayout()
            key = QLabel(keys)
            key.setStyleSheet(
                f"background-color: {theme().input}; border: 1px solid {theme().border}; "
                f"border-radius: 6px; padding: 2px 7px; font-family: 'DejaVu Sans Mono'; font-size: 10px;"
            )
            desc = QLabel(action)
            desc.setObjectName("MutedSmall")
            row.addWidget(key)
            row.addWidget(desc, 1)
            sl.addLayout(row)
        bottom.addWidget(shortcuts, 1)

        info = QFrame()
        info.setObjectName("Card")
        il = QVBoxLayout(info)
        il.setContentsMargins(17, 15, 17, 15)
        il.setSpacing(6)
        it = QLabel("Bajo el capó")
        it.setObjectName("H2")
        il.addWidget(it)
        rows = [
            ("Python", platform.python_version()),
            ("PySide6 / Qt", PySide6.__version__),
            ("yt-dlp", engine_version()),
            ("FFmpeg", "integrado" if ffmpeg_location() else "no encontrado"),
            ("Ajustes", str(config_home())),
        ]
        for label, value in rows:
            row = QHBoxLayout()
            left = QLabel(label)
            left.setObjectName("MutedSmall")
            right = ElidedLabel(value)
            right.setObjectName("MutedSmall")
            right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(left)
            row.addWidget(right, 1)
            il.addLayout(row)
        il.addWidget(divider())
        legal = QLabel(
            "Hecho con cariño para uso personal. Descarga únicamente contenido que tengas derecho a usar y "
            "respeta las condiciones de cada plataforma."
        )
        legal.setObjectName("MutedSmall")
        legal.setWordWrap(True)
        il.addWidget(legal)
        bottom.addWidget(info, 1)
        layout.addLayout(bottom)

        layout.addStretch()


def _icon_path() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parents[2] / "assets" / "icon.svg")
