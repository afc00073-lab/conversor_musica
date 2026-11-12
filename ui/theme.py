"""Sistema de temas y hoja de estilos de Sonora."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from core.config import ACCENTS

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
CHEVRON_PATH = (ASSETS_DIR / "chevron-down.png").as_posix()
CHEVRON_UP_PATH = (ASSETS_DIR / "chevron-up.png").as_posix()


def _rgba(hex_color: str, alpha: float) -> str:
    # Qt interpreta los colores de 8 dígitos como #AARRGGBB (alfa primero).
    color = QColor(hex_color)
    alpha_byte = max(0, min(255, int(round(alpha * 255))))
    return f"#{alpha_byte:02X}{color.red():02X}{color.green():02X}{color.blue():02X}"


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        int(ca.red() + (cb.red() - ca.red()) * t),
        int(ca.green() + (cb.green() - ca.green()) * t),
        int(ca.blue() + (cb.blue() - ca.blue()) * t),
    ).name()


def accent_pair(accent: str) -> tuple[str, str]:
    for first, second in ACCENTS.values():
        if first.lower() == accent.lower():
            return first, second
    return accent, QColor(accent).lighter(125).name()


@dataclass
class Theme:
    mode: str
    accent: str

    def __post_init__(self) -> None:
        self.accent, self.accent2 = accent_pair(self.accent)
        self.is_dark = self.mode == "dark"

        if self.is_dark:
            self.bg = "#0A0D14"
            self.sidebar = "#0C1019"
            self.surface = "#101522"
            self.card = "#131A28"
            self.card_hover = "#182135"
            self.input = "#0D1320"
            self.border = "#222C40"
            self.border_soft = "#1A2334"
            self.border_strong = "#2E3B55"
            self.text = "#EAF0FA"
            self.muted = "#94A1B8"
            self.muted2 = "#66728A"
            self.white = "#FFFFFF"
            self.success = "#34D399"
            self.warning = "#FBBF24"
            self.error = "#FB7185"
            self.shadow = "#05070C"
        else:
            self.bg = "#F3F5FA"
            self.sidebar = "#FFFFFF"
            self.surface = "#FFFFFF"
            self.card = "#FFFFFF"
            self.card_hover = "#F3F6FC"
            self.input = "#F7F9FD"
            self.border = "#DFE5F0"
            self.border_soft = "#E9EDF5"
            self.border_strong = "#C9D3E6"
            self.text = "#101827"
            self.muted = "#5E6B83"
            self.muted2 = "#8D99AF"
            self.white = "#FFFFFF"
            self.success = "#059669"
            self.warning = "#D97706"
            self.error = "#E11D48"
            self.shadow = "#B8C2D6"

        self.accent_hover = _mix(self.accent, "#FFFFFF" if self.is_dark else "#000000", 0.12 if self.is_dark else 0.10)
        self.accent_pressed = _mix(self.accent, "#000000", 0.18)
        self.accent_soft = _rgba(self.accent, 0.15 if self.is_dark else 0.11)
        self.accent_soft2 = _rgba(self.accent, 0.22 if self.is_dark else 0.17)
        self.accent_border = _rgba(self.accent, 0.42)
        self.success_soft = _rgba(self.success, 0.14)
        self.warning_soft = _rgba(self.warning, 0.14)
        self.error_soft = _rgba(self.error, 0.14)
        self.overlay = _rgba("#05080E", 0.72) if self.is_dark else _rgba("#141C2D", 0.32)
        self.gradient = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {self.accent}, stop:1 {self.accent2})"

    @property
    def icon(self) -> str:
        return self.muted

    @property
    def icon_strong(self) -> str:
        return self.text

    def palette(self) -> QPalette:
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(self.bg))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(self.text))
        pal.setColor(QPalette.ColorRole.Base, QColor(self.card))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(self.card_hover))
        pal.setColor(QPalette.ColorRole.Text, QColor(self.text))
        pal.setColor(QPalette.ColorRole.Button, QColor(self.card))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(self.text))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(self.accent))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(self.card))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor(self.text))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(self.muted2))
        pal.setColor(QPalette.ColorRole.Link, QColor(self.accent))
        return pal

    def qss(self) -> str:
        t = self
        return f"""
* {{
    outline: 0;
}}
QWidget {{
    color: {t.text};
    font-family: "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget#Root, QDialog {{
    background-color: {t.bg};
}}
QWidget#Transparent {{ background: transparent; }}
QFrame#Sidebar {{
    background-color: {t.sidebar};
    border-right: 1px solid {t.border_soft};
}}
QFrame#Card, QWidget#Card {{
    background-color: {t.card};
    border: 1px solid {t.border};
    border-radius: 16px;
}}
QFrame#CardSoft {{
    background-color: {t.surface};
    border: 1px solid {t.border_soft};
    border-radius: 14px;
}}
QFrame#Divider {{
    background-color: {t.border_soft};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QLabel {{ background: transparent; }}
QLabel#H1 {{
    font-family: "Noto Sans Display", "Noto Sans";
    font-size: 25px;
    font-weight: 700;
    color: {t.text};
}}
QLabel#H2 {{
    font-family: "Noto Sans Display", "Noto Sans";
    font-size: 17px;
    font-weight: 600;
    color: {t.text};
}}
QLabel#H3 {{
    font-size: 13px;
    font-weight: 600;
    color: {t.text};
}}
QLabel#Muted {{ color: {t.muted}; }}
QLabel#MutedSmall {{ color: {t.muted2}; font-size: 11px; }}
QLabel#AccentText {{ color: {t.accent}; font-weight: 600; }}
QLabel#ErrorText {{ color: {t.error}; }}
QLabel#SuccessText {{ color: {t.success}; }}
QLabel#WarningText {{ color: {t.warning}; }}
QLabel#SectionLabel {{
    color: {t.muted2};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.4px;
}}
QLabel#Badge {{
    background-color: {t.accent_soft};
    color: {t.accent};
    border-radius: 7px;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel#BadgeVideo {{
    background-color: {t.warning_soft};
    color: {t.warning};
    border-radius: 7px;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel#BadgeSuccess {{
    background-color: {t.success_soft};
    color: {t.success};
    border-radius: 7px;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel#BadgeError {{
    background-color: {t.error_soft};
    color: {t.error};
    border-radius: 7px;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel#Dot {{
    background-color: {t.accent};
    border-radius: 4px;
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
}}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {t.input};
    color: {t.text};
    border: 1px solid {t.border};
    border-radius: 10px;
    padding: 8px 11px;
    selection-background-color: {t.accent};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {t.accent};
    background-color: {t.card};
}}
QLineEdit:disabled, QComboBox:disabled {{
    color: {t.muted2};
    background-color: {t.border_soft};
}}
QLineEdit#Search {{
    padding-left: 34px;
}}
QComboBox {{
    padding-right: 28px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 28px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: url("{CHEVRON_PATH}");
    width: 12px;
    height: 12px;
}}
QSpinBox, QDoubleSpinBox {{
    padding-right: 27px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    margin: 5px 4px 0 0;
    border: none;
    background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    margin: 0 4px 5px 0;
    border: none;
    background: transparent;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{CHEVRON_UP_PATH}");
    width: 9px;
    height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{CHEVRON_PATH}");
    width: 9px;
    height: 9px;
}}
QComboBox QAbstractItemView {{
    background-color: {t.card};
    border: 1px solid {t.border};
    border-radius: 10px;
    padding: 4px;
    selection-background-color: {t.accent_soft};
    selection-color: {t.accent};
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    border-radius: 6px;
    min-height: 22px;
}}

QPushButton {{
    background-color: {t.card_hover};
    color: {t.text};
    border: 1px solid {t.border};
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {t.border_soft};
    border-color: {t.border_strong};
}}
QPushButton:pressed {{
    background-color: {t.border};
}}
QPushButton:disabled {{
    color: {t.muted2};
    background-color: transparent;
    border-color: {t.border_soft};
}}
QPushButton[variant="primary"] {{
    background-color: {t.accent};
    color: #FFFFFF;
    border: 1px solid {t.accent};
    font-weight: 700;
}}
QPushButton[variant="primary"]:hover {{
    background-color: {t.accent_hover};
    border-color: {t.accent_hover};
}}
QPushButton[variant="primary"]:pressed {{
    background-color: {t.accent_pressed};
    border-color: {t.accent_pressed};
}}
QPushButton[variant="primary"]:disabled {{
    background-color: {t.accent_soft};
    color: {t.muted2};
    border-color: transparent;
}}
QPushButton[variant="soft"] {{
    background-color: {t.accent_soft};
    color: {t.accent};
    border: 1px solid transparent;
    font-weight: 600;
}}
QPushButton[variant="soft"]:hover {{
    background-color: {t.accent_soft2};
}}
QPushButton[variant="ghost"] {{
    background-color: transparent;
    border: 1px solid {t.border};
    color: {t.muted};
}}
QPushButton[variant="ghost"]:hover {{
    border-color: {t.accent_border};
    color: {t.accent};
    background-color: {t.accent_soft};
}}
QPushButton[variant="danger"] {{
    background-color: {t.error_soft};
    color: {t.error};
    border: 1px solid transparent;
    font-weight: 600;
}}
QPushButton[variant="danger"]:hover {{
    border-color: {t.error};
}}
QPushButton[variant="icon"] {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 5px;
    color: {t.muted};
}}
QPushButton[variant="icon"]:hover {{
    background-color: {t.card_hover};
    border-color: {t.border_soft};
    color: {t.text};
}}
QPushButton[variant="iconDanger"] {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 5px;
}}
QPushButton[variant="iconDanger"]:hover {{
    background-color: {t.error_soft};
    border-color: transparent;
}}
QPushButton[nav="true"] {{
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 9px;
    padding: 10px 12px;
    color: {t.muted};
    text-align: left;
    font-weight: 500;
}}
QPushButton[nav="true"]:hover {{
    background-color: {t.card_hover};
    color: {t.text};
}}
QPushButton[nav="true"]:checked {{
    background-color: {t.accent_soft};
    color: {t.accent};
    border-left: 3px solid {t.accent};
    font-weight: 700;
}}
QPushButton[chip="true"] {{
    background-color: transparent;
    border: 1px solid {t.border};
    border-radius: 999px;
    padding: 5px 13px;
    color: {t.muted};
    font-size: 12px;
    font-weight: 500;
}}
QPushButton[chip="true"]:hover {{
    color: {t.text};
    border-color: {t.border_strong};
}}
QPushButton[chip="true"]:checked {{
    background-color: {t.accent_soft};
    color: {t.accent};
    border-color: {t.accent_border};
    font-weight: 700;
}}
QPushButton[segment="true"] {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 10px 12px;
    color: {t.muted};
    font-weight: 600;
}}
QPushButton[segment="true"]:hover {{
    background-color: {t.card_hover};
    color: {t.text};
}}
QPushButton[segment="true"]:checked {{
    background-color: {t.card};
    border-color: {t.accent_border};
    color: {t.accent};
    font-weight: 700;
}}
QPushButton[link="true"] {{
    background: transparent;
    border: none;
    color: {t.accent};
    padding: 2px 4px;
    font-weight: 600;
}}
QPushButton[link="true"]:hover {{
    color: {t.accent_hover};
    text-decoration: underline;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {t.border_strong};
    min-height: 34px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t.muted2};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {t.border_strong};
    min-width: 34px;
    border-radius: 4px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

QToolTip {{
    background-color: {t.card};
    color: {t.text};
    border: 1px solid {t.border};
    border-radius: 8px;
    padding: 6px 9px;
}}
QMenu {{
    background-color: {t.card};
    border: 1px solid {t.border};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 26px 7px 12px;
    border-radius: 6px;
    color: {t.text};
}}
QMenu::item:selected {{
    background-color: {t.accent_soft};
    color: {t.accent};
}}
QMenu::separator {{
    height: 1px;
    background: {t.border_soft};
    margin: 5px 8px;
}}
QCheckBox {{
    spacing: 8px;
    color: {t.text};
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid {t.border_strong};
    background: {t.input};
}}
QCheckBox::indicator:hover {{
    border-color: {t.accent};
}}
QCheckBox::indicator:checked {{
    background-color: {t.accent};
    border-color: {t.accent};
}}
QListWidget {{
    background: transparent;
    border: none;
    outline: 0;
}}
QListWidget::item {{
    background: {t.card};
    border: 1px solid {t.border_soft};
    border-radius: 9px;
    padding: 7px 9px;
    margin: 2px 0;
    color: {t.text};
}}
QListWidget::item:selected {{
    background: {t.accent_soft};
    color: {t.text};
    border-color: {t.accent_border};
}}
QListWidget::item:hover {{
    border-color: {t.border_strong};
}}
QProgressBar {{
    background-color: {t.border_soft};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {t.accent};
    border-radius: 4px;
}}
QSlider::groove:horizontal {{
    height: 5px;
    border-radius: 3px;
    background: {t.border};
}}
QSlider::sub-page:horizontal {{
    background: {t.accent};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {t.white};
    border: 3px solid {t.accent};
    width: 15px;
    height: 15px;
    margin: -7px 0;
    border-radius: 9px;
}}
QDialog QLabel#DialogTitle {{
    font-size: 19px;
    font-weight: 700;
}}
QFrame#Toast {{
    background-color: {t.card};
    border: 1px solid {t.border_strong};
    border-radius: 12px;
}}
QFrame#SidebarCard {{
    background-color: {t.card};
    border: 1px solid {t.border_soft};
    border-radius: 13px;
}}
QFrame#HeroCard {{
    background-color: {t.surface};
    border: 1px solid {t.border};
    border-radius: 18px;
}}
QFrame#OptionRow {{
    background: transparent;
    border: none;
}}
"""


_current: Theme | None = None


def build_theme(mode: str = "dark", accent: str = "#7C5CFF") -> Theme:
    return Theme(mode=mode, accent=accent)


def theme() -> Theme:
    global _current
    if _current is None:
        _current = build_theme()
    return _current


def set_theme(new_theme: Theme) -> None:
    global _current
    _current = new_theme


def apply_theme(app: QApplication, new_theme: Theme) -> None:
    set_theme(new_theme)
    app.setStyleSheet(new_theme.qss())
    app.setPalette(new_theme.palette())


def preferred_font() -> QFont:
    font = QFont("Noto Sans", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def heading_font(size: int = 18, weight: int = 700) -> QFont:
    font = QFont("Noto Sans Display", size)
    font.setWeight(QFont.Weight(weight))
    return font
