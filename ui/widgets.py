"""Componentes visuales reutilizables de Sonora."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

from ui.icons import make_icon
from ui.theme import theme


def icon_button(name: str, tooltip: str = "", color: str | None = None, size: int = 18, danger: bool = False) -> QPushButton:
    btn = QPushButton()
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setIcon(make_icon(name, color or theme().muted, size))
    btn.setFixedSize(32, 32)
    btn.setIconSize(QSize(size, size))
    btn.setProperty("variant", "iconDanger" if danger else "icon")
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    return btn


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None, mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight):
        super().__init__(parent)
        self._full_text = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._apply_elide()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        available = max(10, self.width() - 2)
        elided = QFontMetrics(self.font()).elidedText(self._full_text, self._mode, available)
        super().setText(elided)


class AnimatedProgressBar(QWidget):
    """Barra de progreso redondeada con degradado y modo indeterminado."""

    def __init__(self, parent: QWidget | None = None, height: int = 8) -> None:
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._value = 0.0
        self._display = 0.0
        self._indeterminate = False
        self._phase = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def _on_anim(self, value) -> None:
        self._display = float(value)
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.018) % 1.0
        self.update()

    def value(self) -> float:
        return self._value

    def setValue(self, value: float, animate: bool = True) -> None:  # noqa: N802
        value = max(0.0, min(100.0, float(value)))
        if abs(value - self._value) < 0.05:
            return
        self._value = value
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._display)
            self._anim.setEndValue(value)
            self._anim.start()
        else:
            self._display = value
            self.update()

    def setIndeterminate(self, active: bool) -> None:  # noqa: N802
        if self._indeterminate == active:
            return
        self._indeterminate = active
        if active:
            self._phase = 0.0
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme()
        rect = QRectF(self.rect())
        radius = rect.height() / 2
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QColor(t.border_soft))

        if self._indeterminate:
            width = rect.width() * 0.32
            travel = rect.width() + width
            x = -width + travel * self._phase
            span = QRectF(max(0, x), 0, min(width, rect.width()), rect.height())
            span = span.intersected(rect)
            if span.width() > 0:
                grad = QLinearGradient(span.topLeft(), span.topRight())
                grad.setColorAt(0, QColor(t.accent).lighter(115))
                grad.setColorAt(0.5, QColor(t.accent2))
                grad.setColorAt(1, QColor(t.accent).lighter(115))
                painter.setBrush(grad)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(span, radius, radius)
            return

        if self._display > 0:
            fill = QRectF(rect.left(), rect.top(), max(radius * 2, rect.width() * self._display / 100.0), rect.height())
            fill = fill.intersected(rect)
            grad = QLinearGradient(fill.topLeft(), fill.topRight())
            grad.setColorAt(0, QColor(t.accent))
            grad.setColorAt(1, QColor(t.accent2))
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(fill, radius, radius)
            glow = QColor(t.accent)
            glow.setAlpha(38)
            painter.setBrush(glow)
            painter.drawRoundedRect(fill.adjusted(-1, -2, 1, 2), radius + 1, radius + 1)


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._offset = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _on_anim(self, value) -> None:
        self._offset = float(value)
        self.update()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme()
        track = QRectF(1, 1, self.width() - 2, self.height() - 2)
        radius = track.height() / 2
        if self.isChecked():
            grad = QLinearGradient(track.topLeft(), track.topRight())
            grad.setColorAt(0, QColor(t.accent))
            grad.setColorAt(1, QColor(t.accent2))
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(QColor(t.border_strong if self.isEnabled() else t.border))
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track, radius, radius)

        margin = 3.0
        diameter = self.height() - margin * 2
        travel = self.width() - margin * 2 - diameter
        x = margin + travel * self._offset
        knob = QRectF(x, margin, diameter, diameter)
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(knob)


class ActivitySpinner(QWidget):
    def __init__(self, parent: QWidget | None = None, size: int = 16) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(28)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme()
        color = QColor(t.accent)
        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.drawArc(rect, int(-self._angle * 16), int(250 * 16))


class DropZone(QFrame):
    textDropped = Signal(str)
    filesDropped = Signal(list)
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(148)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._dragging = False
        self._hover = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 20, 26, 20)
        layout.setSpacing(20)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(62, 62)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        self._title = QLabel("Arrastra enlaces, listas o archivos .txt")
        self._title.setObjectName("H2")
        self._subtitle = QLabel("Pega una URL y pulsa Añadir · también puedes soltar texto o una lista .m3u")
        self._subtitle.setObjectName("Muted")
        self._subtitle.setWordWrap(True)

        self._chips = QWidget()
        chips = QHBoxLayout(self._chips)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(6)
        for text in ("MP3 · 320 kbps", "MP4 · hasta 4K", "Playlists", "Portada + metadatos"):
            chip = QLabel(text)
            chip.setObjectName("Badge")
            chips.addWidget(chip)
        chips.addStretch()
        text_col.addWidget(self._title)
        text_col.addWidget(self._subtitle)
        text_col.addSpacing(5)
        text_col.addWidget(self._chips)
        layout.addLayout(text_col, 1)

        self._hint = QLabel("Suelta aquí")
        self._hint.setObjectName("AccentText")
        layout.addWidget(self._hint, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self._refresh_icon()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = self.width()
        self._hint.setVisible(width >= 600)
        self._chips.setVisible(width >= 480)

    def _refresh_icon(self) -> None:
        color = theme().accent if (self._dragging or self._hover) else theme().muted
        self._icon_label.setPixmap(make_icon("download-cloud", color, 40).pixmap(40, 40))

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()
            self._dragging = True
            self._refresh_icon()
            self.update()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._dragging = False
        self._refresh_icon()
        self.update()

    def dropEvent(self, event) -> None:  # noqa: N802
        self._dragging = False
        self._refresh_icon()
        self.update()
        mime = event.mimeData()
        if mime.hasUrls():
            paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths)
                event.acceptProposedAction()
                return
            remote = [url.toString() for url in mime.urls() if not url.isLocalFile()]
            if remote:
                self.textDropped.emit("\n".join(remote))
                event.acceptProposedAction()
                return
        if mime.hasText():
            self.textDropped.emit(mime.text())
            event.acceptProposedAction()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._refresh_icon()
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._refresh_icon()
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme()
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 17
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        base = QColor(t.card)
        if self._dragging:
            base = QColor(t.accent)
            base.setAlpha(28)
        elif self._hover:
            base = QColor(t.accent)
            base.setAlpha(14)
        painter.fillPath(path, base)

        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if self._dragging:
            grad.setColorAt(0, QColor(t.accent))
            grad.setColorAt(1, QColor(t.accent2))
            pen = QPen(grad, 2.0, Qt.PenStyle.DashLine)
        else:
            color = QColor(t.accent_border if self._hover else t.border)
            pen = QPen(color, 1.4, Qt.PenStyle.DashLine)
        pen.setDashPattern([6, 5])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Halo inferior sutil
        glow = QLinearGradient(rect.left(), rect.bottom() - 40, rect.right(), rect.bottom())
        glow.setColorAt(0, QColor(0, 0, 0, 0))
        glow.setColorAt(0.5, QColor(t.accent))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(0.06 if t.is_dark else 0.04)
        painter.fillRect(QRectF(rect.left(), rect.bottom() - 2, rect.width(), 2), glow)
        painter.setOpacity(1.0)


class Toast(QFrame):
    closed = Signal(object)

    def __init__(self, parent: QWidget, title: str, message: str, kind: str = "info") -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(348)
        self._closing = False
        t = theme()
        color, icon_name = {
            "success": (t.success, "check-circle"),
            "error": (t.error, "alert"),
            "warning": (t.warning, "alert"),
            "info": (t.accent, "sparkles"),
        }.get(kind, (t.accent, "info"))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 10, 12)
        layout.setSpacing(11)
        icon = QLabel()
        icon.setPixmap(make_icon(icon_name, color, 22).pixmap(22, 22))
        icon.setFixedSize(24, 24)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-weight: 700; color: {color};")
        message_label = QLabel(message)
        message_label.setObjectName("Muted")
        message_label.setWordWrap(True)
        message_label.setMaximumWidth(264)
        text_col.addWidget(title_label)
        text_col.addWidget(message_label)
        layout.addLayout(text_col, 1)

        close = icon_button("x", "Cerrar")
        close.setFixedSize(24, 24)
        close.clicked.connect(self.dismiss)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.valueChanged.connect(lambda v: self._effect.setOpacity(float(v)))
        self._fade.start()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._timer.start(4200)

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        fade = QVariantAnimation(self)
        fade.setDuration(140)
        fade.setStartValue(self._effect.opacity())
        fade.setEndValue(0.0)
        fade.valueChanged.connect(lambda v: self._effect.setOpacity(float(v)))
        fade.finished.connect(self._finish)
        self._fade_out = fade
        fade.start()

    def _finish(self) -> None:
        self.closed.emit(self)
        self.hide()
        self.deleteLater()


class ToastManager:
    def __init__(self, parent: QWidget) -> None:
        self.parent = parent
        self.toasts: list[Toast] = []
        self.margin = 22

    def show(self, message: str, kind: str = "info", title: str = "") -> None:
        default_titles = {"success": "Hecho", "error": "Algo falló", "warning": "Atención", "info": "Sonora"}
        toast = Toast(self.parent, title or default_titles.get(kind, "Sonora"), message, kind)
        toast.closed.connect(self._remove)
        toast.adjustSize()
        self.toasts.append(toast)
        while len(self.toasts) > 3:
            self.toasts[0].dismiss()
            self.toasts.pop(0)
        toast.show()
        toast.raise_()
        self.reposition()

    def _remove(self, toast: Toast) -> None:
        if toast in self.toasts:
            self.toasts.remove(toast)
        self.reposition()

    def reposition(self) -> None:
        y = self.parent.height() - self.margin
        for toast in reversed(self.toasts):
            height = toast.sizeHint().height()
            toast.resize(toast.width(), max(56, height))
            y -= toast.height()
            toast.move(self.parent.width() - toast.width() - self.margin, y)
            y -= 8


class StatCard(QFrame):
    def __init__(self, title: str, value: str = "—", icon_name: str = "bar-chart", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedHeight(82)
        t = theme()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        bubble = QLabel()
        bubble.setFixedSize(40, 40)
        bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble.setStyleSheet(f"background-color: {t.accent_soft}; border-radius: 12px;")
        bubble.setPixmap(make_icon(icon_name, t.accent, 20).pixmap(20, 20))
        layout.addWidget(bubble)
        col = QVBoxLayout()
        col.setSpacing(0)
        label = QLabel(title)
        label.setObjectName("MutedSmall")
        self._value = QLabel(value)
        font = QFont("Noto Sans Display", 17)
        font.setWeight(QFont.Weight.Bold)
        self._value.setFont(font)
        col.addWidget(label)
        col.addWidget(self._value)
        layout.addLayout(col, 1)

    def setValue(self, value: str) -> None:  # noqa: N802
        self._value.setText(value)


class FlowLayout(QLayout):
    """Layout fluido tipo grid que reacomoda las tarjetas al redimensionar."""

    def __init__(self, parent: QWidget | None = None, margin: int = 0, h_spacing: int = 14, v_spacing: int = 14) -> None:
        super().__init__(parent)
        self._items: list[QWidgetItem] = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            if widget is None or widget.isHidden():
                continue
            width = item.sizeHint().width()
            height = item.sizeHint().height()
            if x + width > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y += line_height + self._v_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), QSize(width, height)))
            x += width + self._h_spacing
            line_height = max(line_height, height)
        return y + line_height - rect.y() + margins.bottom()


class SettingRow(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        control: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("OptionRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(1)
        label = QLabel(title)
        label.setObjectName("H3")
        col.addWidget(label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("MutedSmall")
            sub.setWordWrap(True)
            col.addWidget(sub)
        layout.addLayout(col, 1)
        if control is not None:
            layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)

    def add_control(self, control: QWidget) -> None:
        self.layout().addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)


def section_header(title: str, subtitle: str = "") -> QWidget:
    w = QWidget()
    col = QVBoxLayout(w)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(1)
    label = QLabel(title)
    label.setObjectName("H2")
    col.addWidget(label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("MutedSmall")
        col.addWidget(sub)
    return w


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


def rounded_thumbnail(pixmap: QPixmap, width: int, height: int, radius: int = 9) -> QPixmap:
    if pixmap.isNull():
        return pixmap
    scaled = pixmap.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 2)
    cropped = scaled.copy(x, y, width, height)
    result = QPixmap(width, height)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return result


def placeholder_thumbnail(width: int, height: int, is_video: bool = False) -> QPixmap:
    t = theme()
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), 9, 9)
    grad = QLinearGradient(0, 0, width, height)
    start = QColor(t.accent)
    start.setAlpha(52)
    grad.setColorAt(0, start)
    grad.setColorAt(1, QColor(t.border_soft))
    painter.fillPath(path, grad)
    icon_name = "film" if is_video else "music"
    icon = make_icon(icon_name, t.accent, max(18, min(34, height // 2))).pixmap(34, 34)
    painter.drawPixmap((width - icon.width()) // 2, (height - icon.height()) // 2, icon)
    painter.end()
    return pixmap
