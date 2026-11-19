"""App mark and category markers."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .themes import Theme


def paint_mark(p: QPainter, rect: QRectF, accent: QColor, base: QColor) -> None:
    """A phone outline with a vault dial: the app icon."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    s = min(rect.width(), rect.height())
    r = QRectF(rect.center().x() - s / 2, rect.center().y() - s / 2, s, s)
    p.setPen(Qt.NoPen)
    p.setBrush(base)
    p.drawRoundedRect(r, s * 0.24, s * 0.24)
    body = QRectF(r.left() + s * 0.27, r.top() + s * 0.14, s * 0.46, s * 0.72)
    p.setPen(QPen(accent, max(1.5, s * 0.07)))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(body, s * 0.09, s * 0.09)
    c = QPointF(body.center().x(), body.center().y() - s * 0.02)
    p.setPen(QPen(accent, max(1.2, s * 0.055)))
    p.drawEllipse(c, s * 0.12, s * 0.12)
    p.setPen(QPen(accent, max(1.2, s * 0.055), Qt.SolidLine, Qt.RoundCap))
    p.drawLine(c, QPointF(c.x(), c.y() - s * 0.07))
    p.drawLine(QPointF(body.center().x() - s * 0.05, body.bottom() - s * 0.08),
               QPointF(body.center().x() + s * 0.05, body.bottom() - s * 0.08))
    p.restore()


def app_icon(theme: Theme, size: int = 256) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_mark(p, QRectF(0, 0, size, size), QColor(theme.accent), QColor(theme.surface_alt))
    p.end()
    return QIcon(pm)


class AppMark(QWidget):
    def __init__(self, theme: Theme, size: int = 28, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setFixedSize(size, size)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_mark_size(self, size: int) -> None:
        self.setFixedSize(size, size)

    def paintEvent(self, _e):
        p = QPainter(self)
        paint_mark(p, QRectF(self.rect()), QColor(self._theme.accent), QColor(self._theme.surface_alt))


def swatch(color: str, size: QSize = QSize(12, 12)) -> QPixmap:
    pm = QPixmap(size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(0, 0, size.width(), size.height()), 3, 3)
    p.end()
    return pm


def theme_preview(theme: Theme, size: QSize = QSize(40, 22)) -> QPixmap:
    pm = QPixmap(size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    w, h = size.width(), size.height()
    p.setPen(QPen(QColor(theme.border), 1))
    p.setBrush(QColor(theme.bg))
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 4, 4)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.surface_alt))
    p.drawRoundedRect(QRectF(4, 4, w * 0.45, h - 8), 2, 2)
    p.setBrush(QColor(theme.accent))
    p.drawRoundedRect(QRectF(w * 0.58, 4, w * 0.34, h - 8), 2, 2)
    p.end()
    return pm
