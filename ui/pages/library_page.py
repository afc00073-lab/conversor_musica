"""Biblioteca de descargas completadas."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.config import ConfigStore
from core.history import HistoryStore
from core.manager import DownloadManager
from core.models import MediaFormat
from core.utils import format_bytes, open_in_file_manager, open_media, time_ago
from ui.dialogs import ConfirmDialog
from ui.icons import make_icon
from ui.theme import theme
from ui.thumbs import ThumbnailLoader
from ui.widgets import ElidedLabel, FlowLayout, StatCard, divider, icon_button, placeholder_thumbnail, rounded_thumbnail

ToastFn = Callable[..., None]


class LibraryCard(QFrame):
    playRequested = Signal(int)
    folderRequested = Signal(int)
    favoriteRequested = Signal(int, bool)
    deleteRequested = Signal(int)

    def __init__(self, entry: dict, thumbs: ThumbnailLoader, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedSize(244, 240)
        self.entry = entry
        self.entry_id = int(entry["id"])
        self._thumb_url = ""
        self._has_thumb = False
        self._thumbs = thumbs

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 9)
        layout.setSpacing(6)

        self.thumb = QLabel()
        self.thumb.setFixedSize(224, 118)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.thumb)

        title_row = QHBoxLayout()
        title_row.setSpacing(5)
        self.title = ElidedLabel(entry.get("title") or "Sin título")
        self.title.setObjectName("H3")
        title_row.addWidget(self.title, 1)
        badge = QLabel(str(entry.get("fmt") or "").upper())
        badge.setObjectName("BadgeVideo" if entry.get("fmt") == "mp4" else "Badge")
        title_row.addWidget(badge, 0)
        layout.addLayout(title_row)

        uploader = QLabel(entry.get("uploader") or "Artista desconocido")
        uploader.setObjectName("MutedSmall")
        uploader.setMaximumHeight(16)
        layout.addWidget(uploader)

        meta = QLabel(
            f"{format_bytes(entry.get('size') or 0)}  ·  {time_ago(float(entry.get('completed_at') or 0))}"
        )
        meta.setObjectName("MutedSmall")
        layout.addWidget(meta)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        self.play = icon_button("play", "Reproducir", theme().success, 16)
        self.play.clicked.connect(lambda: self.playRequested.emit(self.entry_id))
        self.folder = icon_button("folder-open", "Abrir carpeta", theme().muted, 16)
        self.folder.clicked.connect(lambda: self.folderRequested.emit(self.entry_id))
        self.favorite = icon_button("heart", "Favorito", theme().muted, 16)
        self.favorite.clicked.connect(self._toggle_favorite)
        remove = icon_button("trash", "Quitar de la biblioteca", theme().muted, 16, danger=True)
        remove.clicked.connect(lambda: self.deleteRequested.emit(self.entry_id))
        actions.addWidget(self.play)
        actions.addWidget(self.folder)
        actions.addStretch()
        actions.addWidget(self.favorite)
        actions.addWidget(remove)
        layout.addLayout(actions)

        exists = bool(entry.get("filepath")) and Path(entry["filepath"]).exists()
        self.play.setEnabled(exists)
        self.folder.setEnabled(bool(entry.get("filepath")))
        if not exists:
            self.play.setToolTip("El archivo ya no está en esta ubicación")
            meta.setText(meta.text() + "  ·  archivo no encontrado")
            meta.setObjectName("WarningText")

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self._update_favorite_icon()
        self._refresh_thumb()

    def _show_menu(self, pos) -> None:
        menu = QMenu(self)
        filepath = self.entry.get("filepath") or ""
        url = self.entry.get("url") or ""

        def add(text: str, slot, icon_name: str = "", color: str = "") -> None:
            action = menu.addAction(make_icon(icon_name, color or theme().muted, 15), text) if icon_name else menu.addAction(text)
            action.triggered.connect(slot)

        if self.play.isEnabled():
            add("Reproducir archivo", lambda: self.playRequested.emit(self.entry_id), "play", theme().success)
        if filepath:
            add("Abrir carpeta", lambda: self.folderRequested.emit(self.entry_id), "folder-open")
            add("Copiar ruta del archivo", lambda: QApplication.clipboard().setText(filepath))
        if url:
            add("Copiar enlace original", lambda: QApplication.clipboard().setText(url), "link")
        menu.addSeparator()
        favorite = bool(self.entry.get("favorite"))
        add(
            "Quitar de favoritos" if favorite else "Añadir a favoritos",
            lambda: self.favoriteRequested.emit(self.entry_id, not favorite),
            "heart",
            theme().accent if favorite else "",
        )
        add("Eliminar de la biblioteca", lambda: self.deleteRequested.emit(self.entry_id), "trash", theme().error)
        menu.exec(self.mapToGlobal(pos))

    def _refresh_thumb(self) -> None:
        url = self.entry.get("thumbnail") or ""
        if url:
            self._thumb_url = url
            self.thumb.setPixmap(placeholder_thumbnail(224, 118, self.entry.get("fmt") == "mp4"))
            self._thumbs.request(f"lib-{self.entry_id}", url)
        else:
            self.thumb.setPixmap(placeholder_thumbnail(224, 118, self.entry.get("fmt") == "mp4"))

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            return
        self._has_thumb = True
        self.thumb.setPixmap(rounded_thumbnail(pixmap, 224, 118, 10))

    def _toggle_favorite(self) -> None:
        self.favoriteRequested.emit(self.entry_id, not bool(self.entry.get("favorite")))

    def _update_favorite_icon(self) -> None:
        favorite = bool(self.entry.get("favorite"))
        self.favorite.setIcon(make_icon("heart", theme().accent if favorite else theme().muted, 16))
        self.favorite.setToolTip("Quitar de favoritos" if favorite else "Añadir a favoritos")

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self.play.isEnabled():
            self.playRequested.emit(self.entry_id)
        super().mouseDoubleClickEvent(event)


class LibraryPage(QWidget):
    def __init__(
        self,
        manager: DownloadManager,
        config: ConfigStore,
        history: HistoryStore,
        thumbs: ThumbnailLoader,
        toast: ToastFn,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.config = config
        self.history = history
        self.thumbs = thumbs
        self._toast = toast
        self.cards: dict[str, LibraryCard] = {}
        self._kind = "all"
        self._favorites = False
        self._sort = "recent"
        self._entries: dict[int, dict] = {}
        self.setObjectName("Transparent")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.stat_total = StatCard("Descargas totales", "0", "download")
        self.stat_size = StatCard("Espacio ocupado", "0 B", "bar-chart")
        self.stat_fav = StatCard("Favoritos", "0", "heart")
        stats_row.addWidget(self.stat_total)
        stats_row.addWidget(self.stat_size)
        stats_row.addWidget(self.stat_fav)
        layout.addLayout(stats_row)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar título, artista o ruta…")
        self.search.setObjectName("Search")
        self.search.setFixedWidth(310)
        self.search.addAction(make_icon("search", theme().muted2, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, text in (("all", "Todo"), ("audio", "Audio"), ("video", "Vídeo")):
            chip = QPushButton(text)
            chip.setProperty("chip", "true")
            chip.setCheckable(True)
            chip.setChecked(key == "all")
            chip.clicked.connect(lambda _, k=key: self._set_kind(k))
            self._group.addButton(chip)
            toolbar.addWidget(chip)

        self.fav_chip = QPushButton("Favoritos")
        self.fav_chip.setProperty("chip", "true")
        self.fav_chip.setCheckable(True)
        self.fav_chip.setIcon(make_icon("heart", theme().muted2, 14))
        self.fav_chip.clicked.connect(self._toggle_favorites)
        toolbar.addWidget(self.fav_chip)

        toolbar.addStretch()
        self.sort_combo = QComboBox()
        self.sort_combo.setFixedWidth(150)
        for label, value in (("Más recientes", "recent"), ("Más antiguos", "oldest"), ("Título A-Z", "title"), ("Mayor tamaño", "size")):
            self.sort_combo.addItem(label, value)
        self.sort_combo.currentIndexChanged.connect(self._on_sort)
        toolbar.addWidget(self.sort_combo)
        refresh = icon_button("refresh", "Actualizar biblioteca", theme().muted, 17)
        refresh.clicked.connect(self.refresh)
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("Transparent")
        self.grid = FlowLayout(container, margin=0, h_spacing=13, v_spacing=13)
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, 1)

        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(7)
        bubble = QLabel()
        bubble.setFixedSize(74, 74)
        bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble.setStyleSheet(f"background-color: {theme().accent_soft}; border-radius: 24px;")
        bubble.setPixmap(make_icon("library", theme().accent, 33).pixmap(33, 33))
        self.empty_title = QLabel("Tu biblioteca está vacía")
        self.empty_title.setObjectName("H2")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_sub = QLabel("Las descargas completadas aparecerán aquí con su portada y metadatos.")
        self.empty_sub.setObjectName("Muted")
        self.empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_sub)
        self.empty.hide()
        layout.addWidget(self.empty, 1)

        timers = QTimer(self)
        timers.setSingleShot(True)
        timers.setInterval(280)
        timers.timeout.connect(self.refresh)
        self._search_timer = timers
        self.search.textChanged.connect(lambda: self._search_timer.start())

        self.thumbs.loaded.connect(self._on_thumb)
        self.manager.libraryChanged.connect(self.refresh)
        self.refresh()

    def _on_search(self, text: str) -> None:
        self._search_timer.start()

    def _set_kind(self, kind: str) -> None:
        self._kind = kind
        self.refresh()

    def _toggle_favorites(self) -> None:
        self._favorites = self.fav_chip.isChecked()
        self.refresh()

    def _on_sort(self, index: int) -> None:
        self._sort = self.sort_combo.itemData(index) or "recent"
        self.refresh()

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self.cards.clear()

    def refresh(self) -> None:
        self._clear_grid()
        try:
            entries = self.history.list(
                search=self.search.text().strip(),
                kind=self._kind,
                favorites=self._favorites,
                sort=self._sort,
            )
        except Exception:
            entries = []
        self._entries = {int(e["id"]): e for e in entries}
        for entry in entries[:240]:
            card = LibraryCard(entry, self.thumbs)
            card.playRequested.connect(self._play)
            card.folderRequested.connect(self._open_folder)
            card.favoriteRequested.connect(self._set_favorite)
            card.deleteRequested.connect(self._delete)
            self.cards[f"lib-{entry['id']}"] = card
            self.grid.addWidget(card)
        has_items = bool(self.cards)
        self.scroll.setVisible(has_items)
        self.empty.setVisible(not has_items)
        stats = self.history.stats()
        self.stat_total.setValue(str(stats.get("count") or 0))
        self.stat_size.setValue(format_bytes(stats.get("total_size") or 0))
        favs = sum(1 for e in self.history.list(favorites=True) if e)
        self.stat_fav.setValue(str(favs))
        if not has_items and (self.search.text().strip() or self._kind != "all" or self._favorites):
            self.empty_title.setText("Sin resultados")
            self.empty_sub.setText("Prueba con otro término o cambia los filtros de la biblioteca.")
        else:
            self.empty_title.setText("Tu biblioteca está vacía")
            self.empty_sub.setText("Las descargas completadas aparecerán aquí con su portada y metadatos.")
        if len(entries) > 240:
            self.empty_sub.setText(f"Mostrando 240 de {len(entries)} resultados.")

    def _on_thumb(self, key: str, pixmap: QPixmap) -> None:
        card = self.cards.get(key)
        if card:
            card.set_thumbnail(pixmap)

    def _play(self, entry_id: int) -> None:
        entry = self._entries.get(entry_id)
        if entry and entry.get("filepath"):
            if Path(entry["filepath"]).exists():
                open_media(entry["filepath"])
            else:
                self._toast("El archivo ya no existe en esa ubicación.", "warning", "Archivo no encontrado")

    def _open_folder(self, entry_id: int) -> None:
        entry = self._entries.get(entry_id)
        if not entry:
            return
        path = entry.get("filepath") or self.config.settings.outdir
        open_in_file_manager(path)

    def _set_favorite(self, entry_id: int, favorite: bool) -> None:
        self.history.set_favorite(entry_id, favorite)
        self.refresh()

    def _delete(self, entry_id: int) -> None:
        entry = self._entries.get(entry_id)
        if not entry:
            return
        dialog = ConfirmDialog(
            "Quitar de la biblioteca",
            f"«{entry.get('title')}» se quitará del historial. El archivo descargado no se eliminará del disco.",
            self,
            "Quitar",
            danger=True,
        )
        if dialog.exec():
            self.history.delete(entry_id)
            self.refresh()
            self._toast("Elemento eliminado de la biblioteca.", "info")

    def refresh_theme(self) -> None:
        self.update()
