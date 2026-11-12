"""Ventana principal de Sonora."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import APP_NAME, APP_VERSION, GITHUB_URL, ConfigStore
from core.history import HistoryStore
from core.manager import DownloadManager
from core.models import JobStatus
from core.utils import extract_urls, format_bytes, is_probably_url, open_in_file_manager
from ui.dialogs import ConfirmDialog
from ui.icons import make_icon, pixmap_from_svg_file
from ui.pages.about_page import AboutPage
from ui.pages.download_page import DownloadPage, is_playlist_url
from ui.pages.library_page import LibraryPage
from ui.pages.log_page import LogPage
from ui.pages.settings_page import SettingsPage
from ui.theme import apply_theme, build_theme, theme
from ui.thumbs import ThumbnailLoader
from ui.widgets import ActivitySpinner, ToastManager, icon_button

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
ICON_PATH = ASSET_DIR / "icon.svg"

PAGE_META = {
    "download": ("Conversor", "Añade enlaces y conviértelos a MP3 o MP4"),
    "library": ("Biblioteca", "Todo lo que has descargado, siempre a mano"),
    "log": ("Registro", "Actividad del motor de descarga en tiempo real"),
    "settings": ("Ajustes", "Personaliza Sonora a tu manera"),
    "about": ("Acerca de", "Información, atajos y créditos"),
}
PAGE_ICONS = {
    "download": "download",
    "library": "library",
    "log": "terminal",
    "settings": "settings",
    "about": "info",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = ConfigStore()
        self.history = HistoryStore()
        self.thumbs = ThumbnailLoader(self)
        self.manager = DownloadManager(self.config, self.history, self)
        self._last_stats: dict = {}
        self._current_key = "download"
        self._rebuild_scheduled = False
        self._quitting = False
        self._tray_notice_shown = False
        self._last_clipboard = ""
        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, QPushButton] = {}

        self.setWindowTitle(f"{APP_NAME} — Conversor de música y vídeo")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(1180, 700)
        self.resize(1320, 850)
        self.setAcceptDrops(True)
        self._restore_geometry()

        self._apply_theme(rebuild=False)
        self._build_central()
        self._install_shortcuts()
        self._build_tray()
        self._connect_manager()
        self._navigate(self.config.settings.last_page if self.config.settings.last_page in PAGE_META else "download", remember=False)

        self._clipboard_timer = QTimer(self)
        self._clipboard_timer.setInterval(1100)
        self._clipboard_timer.timeout.connect(self._watch_clipboard)
        self._clipboard_timer.start()
        self._last_clipboard = QGuiApplication.clipboard().text()

        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _: self._on_system_theme_changed())

    # ------------------------------------------------------------- estructura
    def _build_central(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        content = QWidget()
        content.setObjectName("Transparent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 18, 24, 18)
        content_layout.setSpacing(12)
        content_layout.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        layout.addWidget(content, 1)

        self._pages = {}
        self._pages["download"] = DownloadPage(self.manager, self.config, self.thumbs, self.toast)
        self._pages["library"] = LibraryPage(self.manager, self.config, self.history, self.thumbs, self.toast)
        self._pages["log"] = LogPage(self.manager, self.toast)
        self._pages["settings"] = SettingsPage(self.manager, self.config, self.toast, self._theme_changed)
        self._pages["about"] = AboutPage()
        for page in self._pages.values():
            self.stack.addWidget(page)

        old = self.centralWidget()
        self.setCentralWidget(root)
        if old is not None:
            old.deleteLater()
        if hasattr(self, "toasts"):
            for toast in list(self.toasts.toasts):
                toast.deleteLater()
        self.toasts = ToastManager(self)
        self._apply_stats(self._last_stats)
        if isinstance(self._pages.get("download"), DownloadPage) and self._last_stats:
            self._pages["download"]._on_stats(self._last_stats)
        self._navigate(self._current_key, remember=False)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(224)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(6)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(pixmap_from_svg_file(str(ICON_PATH), 38))
        logo.setFixedSize(38, 38)
        logo_row.addWidget(logo)
        logo_col = QVBoxLayout()
        logo_col.setSpacing(0)
        name = QLabel(APP_NAME)
        name_font = QFont("Noto Sans Display", 18)
        name_font.setWeight(QFont.Weight.Bold)
        name.setFont(name_font)
        tag = QLabel("CONVERSOR")
        tag.setStyleSheet(f"color: {theme().muted2}; font-size: 9px; font-weight: 700; letter-spacing: 2px;")
        logo_col.addWidget(name)
        logo_col.addWidget(tag)
        logo_row.addLayout(logo_col, 1)
        layout.addLayout(logo_row)
        layout.addSpacing(16)

        section = QLabel("PRINCIPAL")
        section.setObjectName("SectionLabel")
        layout.addWidget(section)
        layout.addSpacing(2)

        self._nav_buttons = {}
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for key, icon_name in PAGE_ICONS.items():
            button = QPushButton("  " + PAGE_META[key][0])
            button.setProperty("nav", "true")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(make_icon(icon_name, theme().muted, 18))
            button.setIconSize(QSize(18, 18))
            button.setFixedHeight(40)
            button.clicked.connect(lambda _, k=key: self._navigate(k))
            self._nav_group.addButton(button)
            self._nav_buttons[key] = button
            layout.addWidget(button)

        layout.addSpacing(12)
        session_label = QLabel("ESTA SESIÓN")
        session_label.setObjectName("SectionLabel")
        layout.addWidget(session_label)
        session_card = QFrame()
        session_card.setObjectName("SidebarCard")
        sc = QVBoxLayout(session_card)
        sc.setContentsMargins(12, 10, 12, 10)
        sc.setSpacing(6)

        row = QHBoxLayout()
        label = QLabel("Completados")
        label.setObjectName("MutedSmall")
        self.session_done = QLabel("0")
        self.session_done.setStyleSheet("font-weight: 700;")
        row.addWidget(label)
        row.addStretch()
        row.addWidget(self.session_done)
        sc.addLayout(row)

        row2 = QHBoxLayout()
        label2 = QLabel("Descargado")
        label2.setObjectName("MutedSmall")
        self.session_size = QLabel("0 B")
        self.session_size.setStyleSheet("font-weight: 700;")
        row2.addWidget(label2)
        row2.addStretch()
        row2.addWidget(self.session_size)
        sc.addLayout(row2)

        self.session_queue = QLabel("Sin actividad")
        self.session_queue.setObjectName("MutedSmall")
        self.session_queue.setWordWrap(True)
        sc.addWidget(self.session_queue)
        layout.addWidget(session_card)
        layout.addStretch()

        self.sidebar_theme = QPushButton()
        self.sidebar_theme.setProperty("variant", "ghost")
        self.sidebar_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_theme.setFixedHeight(38)
        self.sidebar_theme.clicked.connect(self.toggle_theme)
        layout.addWidget(self.sidebar_theme)
        self._update_theme_button()

        version = QLabel(f"v{APP_VERSION}  ·  hecho con ♥")
        version.setObjectName("MutedSmall")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setCursor(Qt.CursorShape.PointingHandCursor)
        version.mouseReleaseEvent = lambda _: self._navigate("about")  # type: ignore[assignment]
        layout.addWidget(version)
        return sidebar

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Transparent")
        bar.setFixedHeight(66)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.page_title = QLabel("Conversor")
        self.page_title.setObjectName("H1")
        self.page_subtitle = QLabel("")
        self.page_subtitle.setObjectName("Muted")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        layout.addLayout(titles, 1)

        self.activity_chip = QFrame()
        self.activity_chip.setObjectName("CardSoft")
        chip_layout = QHBoxLayout(self.activity_chip)
        chip_layout.setContentsMargins(11, 6, 12, 6)
        chip_layout.setSpacing(7)
        self.activity_spinner = ActivitySpinner(size=14)
        chip_layout.addWidget(self.activity_spinner)
        self.activity_label = QLabel("0 activas")
        self.activity_label.setObjectName("MutedSmall")
        chip_layout.addWidget(self.activity_label)
        self.activity_chip.hide()
        layout.addWidget(self.activity_chip)

        new_button = QPushButton("Nueva descarga")
        new_button.setProperty("variant", "soft")
        new_button.setIcon(make_icon("plus", theme().accent, 15))
        new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        new_button.clicked.connect(self._new_download)
        layout.addWidget(new_button)

        theme_button = icon_button("sun" if theme().is_dark else "moon", "Cambiar tema", theme().muted, 18)
        theme_button.setFixedSize(36, 36)
        theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(theme_button)

        repo_button = icon_button("external", "Abrir repositorio en GitHub", theme().muted, 18)
        repo_button.setFixedSize(36, 36)
        repo_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        layout.addWidget(repo_button)
        return bar

    # ------------------------------------------------------------------ tema
    def _effective_mode(self) -> str:
        mode = self.config.settings.theme
        if mode == "system":
            scheme = QGuiApplication.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        return "light" if mode == "light" else "dark"

    def _apply_theme(self, rebuild: bool = True) -> None:
        palette = build_theme(self._effective_mode(), self.config.settings.accent)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, palette)
        if rebuild and self.centralWidget() is not None:
            self._schedule_rebuild()
        self._update_theme_button()

    def _schedule_rebuild(self) -> None:
        if self._rebuild_scheduled:
            return
        self._rebuild_scheduled = True
        QTimer.singleShot(30, self._rebuild_ui)

    def _rebuild_ui(self) -> None:
        self._rebuild_scheduled = False
        key = self._current_key
        log_entries = list(self._pages["log"].entries) if "log" in self._pages else []
        input_text = ""
        download_page = self._pages.get("download")
        if isinstance(download_page, DownloadPage):
            input_text = download_page.url_input.text()
        library_search = ""
        library_page = self._pages.get("library")
        if isinstance(library_page, LibraryPage):
            library_search = library_page.search.text()

        self._build_central()
        if "log" in self._pages:
            self._pages["log"].entries = log_entries
            self._pages["log"]._render()
        if isinstance(self._pages.get("download"), DownloadPage) and input_text:
            self._pages["download"].url_input.setText(input_text)
        if isinstance(self._pages.get("library"), LibraryPage) and library_search:
            self._pages["library"].search.setText(library_search)
        self._navigate(key, remember=False)

    def _theme_changed(self) -> None:
        self._apply_theme(rebuild=True)

    def _on_system_theme_changed(self) -> None:
        if self.config.settings.theme == "system":
            self._apply_theme(rebuild=True)

    def toggle_theme(self) -> None:
        new_mode = "light" if self._effective_mode() == "dark" else "dark"
        self.config.update(theme=new_mode)
        self._apply_theme(rebuild=True)

    def _update_theme_button(self) -> None:
        if not hasattr(self, "sidebar_theme"):
            return
        is_dark = self._effective_mode() == "dark"
        self.sidebar_theme.setText("  Modo claro" if is_dark else "  Modo oscuro")
        self.sidebar_theme.setIcon(make_icon("sun" if is_dark else "moon", theme().muted, 17))

    # --------------------------------------------------------------- navegar
    def _navigate(self, key: str, remember: bool = True) -> None:
        if key not in self._pages:
            key = "download"
        self._current_key = key
        self.stack.setCurrentWidget(self._pages[key])
        title, subtitle = PAGE_META[key]
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        for nav_key, button in self._nav_buttons.items():
            active = nav_key == key
            button.setChecked(active)
            button.setIcon(make_icon(PAGE_ICONS[nav_key], theme().accent if active else theme().muted, 18))
        if key == "library" and isinstance(self._pages.get("library"), LibraryPage):
            self._pages["library"].refresh()
        if remember:
            self.config.update(last_page=key)
        if key == "download":
            QTimer.singleShot(60, lambda: self._pages["download"].url_input.setFocus())

    def _new_download(self) -> None:
        self._show_window()
        self._navigate("download")
        page = self._pages.get("download")
        if isinstance(page, DownloadPage):
            page.url_input.setFocus()
            page.url_input.selectAll()

    def _show_window(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    # --------------------------------------------------------------- señales
    def _connect_manager(self) -> None:
        self.manager.statsChanged.connect(self._apply_stats)
        self.manager.jobCompleted.connect(self._on_completed)
        self.manager.jobFailed.connect(self._on_failed)
        self.manager.pausedChanged.connect(lambda _: self._update_tray_menu())

    def _apply_stats(self, stats: dict) -> None:
        self._last_stats = stats
        if not stats:
            stats = {"done": 0, "active": 0, "queued": 0, "completed_size": 0, "speed": 0}
        if hasattr(self, "session_done"):
            self.session_done.setText(str(stats.get("done") or 0))
            self.session_size.setText(format_bytes(stats.get("completed_size") or 0))
            active = int(stats.get("active") or 0)
            queued = int(stats.get("queued") or 0)
            errors = int(stats.get("errors") or 0)
            if active:
                text = f"{active} descarga{'s' if active != 1 else ''} activa{'s' if active != 1 else ''}"
                if queued:
                    text += f" · {queued} en cola"
            elif queued:
                text = f"{queued} en cola · esperando inicio"
            elif errors:
                text = f"{errors} con error · revisa la cola"
            else:
                text = "Sin actividad"
            self.session_queue.setText(text)
            if self.manager.paused:
                self.session_queue.setText("Cola pausada")
        if hasattr(self, "activity_chip"):
            active = int(stats.get("active") or 0)
            queued = int(stats.get("queued") or 0)
            if active:
                self.activity_chip.show()
                self.activity_label.setText(f"{active} activa{'s' if active != 1 else ''}")
                self.activity_spinner.start()
            elif queued:
                self.activity_chip.show()
                self.activity_label.setText(f"{queued} en cola")
                self.activity_spinner.stop()
            else:
                self.activity_chip.hide()
                self.activity_spinner.stop()
        self._update_tray_menu()

    def _on_completed(self, job_id: str) -> None:
        job = self.manager.jobs.get(job_id)
        if not job:
            return
        self.toast(f"«{job.display_title}» ya está listo.", "success", "Descarga completada")
        if self.config.settings.notifications and self.tray.isVisible() and not self.isActiveWindow():
            self.tray.showMessage(
                "Descarga completada",
                f"{job.display_title}\n{format_bytes(job.size)} · {job.fmt.label}",
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )
        if isinstance(self._pages.get("library"), LibraryPage):
            self._pages["library"].refresh()

    def _on_failed(self, job_id: str, error: str) -> None:
        job = self.manager.jobs.get(job_id)
        title = job.display_title if job else "Descarga"
        self.toast(f"{error}", "error", f"Falló: {title[:48]}")

    # ------------------------------------------------------------ bandeja
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(QIcon(str(ICON_PATH)), self)
        self.tray.setToolTip(f"{APP_NAME} · conversor de música y vídeo")
        self.tray_menu = QMenu()
        show_action = QAction("Mostrar Sonora", self)
        show_action.triggered.connect(self._show_window)
        new_action = QAction("Nueva descarga…", self)
        new_action.triggered.connect(self._new_download)
        self.tray_pause_action = QAction("Pausar cola", self)
        self.tray_pause_action.triggered.connect(self._tray_toggle_queue)
        library_action = QAction("Abrir biblioteca", self)
        library_action.triggered.connect(lambda: (self._show_window(), self._navigate("library")))
        folder_action = QAction("Abrir carpeta de descargas", self)
        folder_action.triggered.connect(lambda: open_in_file_manager(self.config.settings.outdir))
        settings_action = QAction("Ajustes", self)
        settings_action.triggered.connect(lambda: (self._show_window(), self._navigate("settings")))
        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self._quit_app)
        self.tray_menu.addAction(show_action)
        self.tray_menu.addAction(new_action)
        self.tray_menu.addAction(library_action)
        self.tray_menu.addAction(folder_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.tray_pause_action)
        self.tray_menu.addAction(settings_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(quit_action)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self._show_window)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and self.isActiveWindow():
                self.hide()
            else:
                self._show_window()

    def _tray_toggle_queue(self) -> None:
        if self.manager.paused:
            self.manager.resume()
        else:
            self.manager.pause()
        self._update_tray_menu()

    def _update_tray_menu(self) -> None:
        if not hasattr(self, "tray_pause_action"):
            return
        self.tray_pause_action.setText("Reanudar cola" if self.manager.paused else "Pausar cola")
        active = int(self._last_stats.get("active") or 0)
        self.tray.setToolTip(f"{APP_NAME} · {active} descarga{'s' if active != 1 else ''} activa{'s' if active != 1 else ''}" if active else f"{APP_NAME} · listo")

    # ---------------------------------------------------------------- atajos
    def _install_shortcuts(self) -> None:
        def add(keys: str, handler) -> None:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(handler)

        add("Ctrl+V", self._shortcut_paste)
        add("Ctrl+O", self._shortcut_import)
        add("Ctrl+L", lambda: (self._navigate("download"), self._pages["download"].url_input.setFocus()))
        add("Ctrl+1", lambda: self._navigate("download"))
        add("Ctrl+2", lambda: self._navigate("library"))
        add("Ctrl+3", lambda: self._navigate("log"))
        add("Ctrl+4", lambda: self._navigate("settings"))
        add("Ctrl+5", lambda: self._navigate("about"))
        add("Ctrl+,", lambda: self._navigate("settings"))
        add("F5", self._shortcut_retry)
        add("Ctrl+Shift+T", self.toggle_theme)
        add("Space", self._shortcut_space)

    def _text_focus(self) -> QWidget | None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit)):
            return focus
        return None

    def _shortcut_paste(self) -> None:
        focus = self._text_focus()
        if focus is not None:
            focus.paste()
            return
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            self.toast("El portapapeles está vacío.", "warning", "Nada que pegar")
            return
        self._navigate("download")
        self._pages["download"].add_from_text(text)

    def _shortcut_import(self) -> None:
        self._navigate("download")
        self._pages["download"]._import_file()

    def _shortcut_retry(self) -> None:
        count = self.manager.retry_failed()
        if count:
            self.toast(f"Reintentando {count} descarga{'s' if count != 1 else ''}.", "info")
        else:
            self.toast("No hay descargas fallidas.", "info")

    def _shortcut_space(self) -> None:
        if self._text_focus() is not None:
            return
        self.manager.toggle_pause()

    # ------------------------------------------------------------- portapapeles
    def _watch_clipboard(self) -> None:
        if not self.config.settings.clipboard_watch:
            return
        text = QGuiApplication.clipboard().text().strip()
        if not text or text == self._last_clipboard:
            return
        self._last_clipboard = text
        if len(text) > 4000 or not extract_urls(text):
            return
        if is_playlist_url(text):
            self.toast("Hay una lista en el portapapeles. Pégala en el conversor para elegir los elementos.", "info")
            return
        page = self._pages.get("download")
        if isinstance(page, DownloadPage):
            added = page.add_from_text(text)
            if added:
                self.toast("Enlace detectado en el portapapeles y añadido a la cola.", "info", "Portapapeles")

    # -------------------------------------------------------------- arrastrar
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        page = self._pages.get("download")
        if not isinstance(page, DownloadPage):
            return
        handled = False
        if mime.hasUrls():
            paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
            remote = [url.toString() for url in mime.urls() if not url.isLocalFile()]
            if paths:
                page.add_files(paths)
                handled = True
            if remote:
                handled = page.add_from_text("\n".join(remote)) or handled
        if not handled and mime.hasText():
            handled = page.add_from_text(mime.text())
        if handled:
            self._show_window()
            self._navigate("download")
            event.acceptProposedAction()

    # -------------------------------------------------------------- ventana
    def toast(self, message: str, kind: str = "info", title: str = "") -> None:
        self.toasts.show(message, kind, title)

    def _restore_geometry(self) -> None:
        data = self.config.settings.window_geometry
        if data:
            try:
                self.restoreGeometry(QByteArray.fromBase64(data.encode("ascii")))
            except Exception:
                pass

    def _save_state(self) -> None:
        try:
            geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.config.update(window_geometry=geometry, last_page=self._current_key)
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._quitting:
            self._save_state()
            self.manager.shutdown()
            self.tray.hide()
            event.accept()
            return
        if self.config.settings.close_to_tray and self.tray.isVisible():
            self._save_state()
            self.hide()
            if not self._tray_notice_shown:
                self._tray_notice_shown = True
                if self.config.settings.notifications:
                    self.tray.showMessage(
                        "Sonora sigue en segundo plano",
                        "Las descargas continuarán. Haz clic en el icono de la bandeja para volver.",
                        QSystemTrayIcon.MessageIcon.Information,
                        5000,
                    )
            event.ignore()
            return
        active = any(job.status.is_active or job.status is JobStatus.QUEUED for job in self.manager.jobs.values())
        if active:
            dialog = ConfirmDialog(
                "Hay descargas en curso",
                "Si sales ahora se cancelarán las descargas activas y pendientes. ¿Quieres salir de todos modos?",
                self,
                "Salir igualmente",
                danger=True,
            )
            if not dialog.exec():
                event.ignore()
                return
        self._save_state()
        self.manager.shutdown()
        self.tray.hide()
        event.accept()

    def _quit_app(self) -> None:
        self._quitting = True
        self.close()
        QApplication.instance().quit()
