"""Diálogos propios de Sonora."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.utils import format_duration
from ui.icons import make_icon
from ui.theme import theme


class PlaylistDialog(QDialog):
    def __init__(self, info: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Seleccionar elementos de la lista")
        self.setModal(True)
        self.setMinimumSize(720, 560)
        self.resize(780, 640)
        self.entries = info.get("entries") or []
        self._selected_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(make_icon("list-music", theme().accent, 28).pixmap(28, 28))
        header.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel(info.get("title") or "Lista de reproducción")
        title.setObjectName("H2")
        title.setWordWrap(True)
        subtitle = QLabel(
            f"{len(self.entries)} elementos · {info.get('uploader') or 'YouTube'} · "
            f"{format_duration(sum(float(e.get('duration') or 0) for e in self.entries))}"
        )
        subtitle.setObjectName("Muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        layout.addLayout(header)

        search = QLineEdit()
        search.setObjectName("Search")
        search.setPlaceholderText("Buscar en la lista…")
        search.addAction(make_icon("search", theme().muted2, 16), QLineEdit.ActionPosition.LeadingPosition)
        search.textChanged.connect(self._filter)
        layout.addWidget(search)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for index, entry in enumerate(self.entries, 1):
            label = f"{index:02d}   {entry.get('title') or 'Sin título'}"
            duration = format_duration(entry.get("duration") or 0)
            item = QListWidgetItem(f"{label}     ·  {duration}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget, 1)

        footer = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setObjectName("Muted")
        footer.addWidget(self.count_label)
        footer.addStretch()

        select_all = QPushButton("Seleccionar todo")
        select_all.setProperty("variant", "ghost")
        select_all.clicked.connect(lambda: self._set_all(True))
        select_none = QPushButton("Quitar selección")
        select_none.setProperty("variant", "ghost")
        select_none.clicked.connect(lambda: self._set_all(False))
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.reject)
        self.add_button = QPushButton()
        self.add_button.setProperty("variant", "primary")
        self.add_button.setIcon(make_icon("download", "#FFFFFF", 17))
        self.add_button.clicked.connect(self.accept)
        for widget in (select_all, select_none):
            footer.addWidget(widget)
        footer.addSpacing(10)
        footer.addWidget(cancel)
        footer.addWidget(self.add_button)
        layout.addLayout(footer)

        self._update_count()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        self._selected_count = sum(
            1 for i in range(self.list_widget.count()) if self.list_widget.item(i).checkState() == Qt.CheckState.Checked
        )
        self._update_count()

    def _update_count(self) -> None:
        count = 0
        for index in range(self.list_widget.count()):
            if self.list_widget.item(index).checkState() == Qt.CheckState.Checked:
                count += 1
        self._selected_count = count
        self.count_label.setText(f"{count} de {self.list_widget.count()} seleccionados")
        self.add_button.setText(f"Añadir {count} a la cola" if count else "Añadir a la cola")
        self.add_button.setEnabled(count > 0)

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if not item.isHidden():
                item.setCheckState(state)

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def selected_entries(self) -> list[dict]:
        selected: list[dict] = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                entry = item.data(Qt.ItemDataRole.UserRole)
                if entry:
                    selected.append(entry)
        return selected


class ConfirmDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: str,
        parent: QWidget | None = None,
        confirm_text: str = "Confirmar",
        danger: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        icon = QLabel()
        icon_name = "alert" if danger else "info"
        color = theme().error if danger else theme().accent
        icon.setPixmap(make_icon(icon_name, color, 26).pixmap(26, 26))
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        header.addWidget(title_label, 1)
        layout.addLayout(header)

        body = QLabel(message)
        body.setObjectName("Muted")
        body.setWordWrap(True)
        layout.addWidget(body)

        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(confirm_text)
        confirm.setProperty("variant", "danger" if danger else "primary")
        confirm.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(confirm)
        layout.addLayout(footer)


class LinkDialog(QDialog):
    """Añadir varias URLs pegadas en un cuadro de texto."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Añadir enlaces")
        self.setMinimumSize(560, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = QLabel("Pega uno o varios enlaces")
        title.setObjectName("H2")
        subtitle = QLabel("Un enlace por línea. También puedes pegar texto con enlaces mezclados.")
        subtitle.setObjectName("Muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        self.input = QLineEdit()
        self.input.setPlaceholderText("https://www.youtube.com/watch?v=…")
        layout.addWidget(self.input)
        self.text = QLineEdit()  # compat placeholder
        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.reject)
        add = QPushButton("Añadir")
        add.setProperty("variant", "primary")
        add.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(add)
        layout.addLayout(footer)

    def text_value(self) -> str:
        return self.input.text()
