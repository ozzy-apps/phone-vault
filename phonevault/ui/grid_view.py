"""Card grid of files, in the style of Inca's library browser."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate

from ..core.models import CATEGORY_INFO, Confidence, Kind
from . import icons
from .file_view import FILE_ROLE
from .themes import Theme
from .thumbnails import ThumbnailCache

GRID_SIZES = {"S": 104, "M": 148, "L": 208}
_KIND_ICON = {Kind.IMAGE: "image", Kind.VIDEO: "video", Kind.AUDIO: "audio"}


class GridDelegate(QStyledItemDelegate):
    def __init__(self, thumbs: ThumbnailCache, theme: Theme, parent=None):
        super().__init__(parent)
        self.thumbs = thumbs
        self.theme = theme
        self.cell = GRID_SIZES["M"]

    def sizeHint(self, option, index):
        fm = QFontMetrics(option.font)
        return QSize(self.cell, self.cell + fm.height() + 12)

    def paint(self, p: QPainter, option, index):
        f = index.data(FILE_ROLE)
        if f is None:
            return
        t = self.theme
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(option.rect).adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        if selected or hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.sel_soft) if selected else t.q("raised", 0.5))
            p.drawRoundedRect(r, 6, 6)

        side = r.width() - 10
        tile = QRectF(r.left() + 5, r.top() + 5, side, side)
        clip = QPainterPath()
        clip.addRoundedRect(tile, 5, 5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.field))
        p.drawPath(clip)

        img = self.thumbs.get(f)
        if img is not None:
            iw, ih = img.width(), img.height()
            scale = max(tile.width() / iw, tile.height() / ih)
            sw, sh = tile.width() / scale, tile.height() / scale
            src = QRectF((iw - sw) / 2, (ih - sh) / 2, sw, sh)
            p.save()
            p.setClipPath(clip)
            p.drawImage(tile, img, src)
            p.restore()
        else:
            edge = int(side * 0.3)
            pm = icons.pixmap(_KIND_ICON.get(f.kind, "file"), t.text_muted, edge)
            p.drawPixmap(int(tile.center().x() - edge / 2), int(tile.center().y() - edge / 2), pm)
            if f.kind not in _KIND_ICON and f.ext:
                p.setPen(QColor(t.text_muted))
                ext_font = QFont(option.font)
                ext_font.setPointSizeF(ext_font.pointSizeF() * 0.8)
                p.setFont(ext_font)
                p.drawText(QRectF(tile.left(), tile.center().y() + edge * 0.6, tile.width(), edge),
                           Qt.AlignHCenter | Qt.AlignTop, f.ext.upper())

        p.setPen(QPen(t.q("accent", 0.85), 1.5) if selected else QPen(QColor(t.border), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(clip)

        # category marker
        dot = QPointF(tile.left() + 10, tile.bottom() - 10)
        p.setPen(QPen(QColor(t.field), 2))
        p.setBrush(QColor(CATEGORY_INFO[f.category].color))
        p.drawEllipse(dot, 4.5, 4.5)
        if f.confidence == Confidence.GUESS:
            p.setBrush(QColor(t.warning))
            p.drawEllipse(QPointF(tile.right() - 10, tile.top() + 10), 4, 4)
        if f.backed_up:
            c = QPointF(tile.right() - 12, tile.bottom() - 12)
            p.setPen(QPen(QColor(t.field), 2))
            p.setBrush(QColor(t.accent))
            p.drawEllipse(c, 7, 7)
            p.setPen(QPen(QColor(t.accent_text), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPolyline([QPointF(c.x() - 3.2, c.y() + 0.2), QPointF(c.x() - 0.8, c.y() + 2.6),
                            QPointF(c.x() + 3.4, c.y() - 2.4)])

        # name
        p.setPen(QColor(t.text))
        p.setFont(option.font)
        fm = QFontMetrics(option.font)
        text_rect = QRectF(r.left() + 4, tile.bottom() + 4, r.width() - 8, fm.height() + 2)
        p.drawText(text_rect, Qt.AlignHCenter | Qt.AlignVCenter,
                   fm.elidedText(f.name, Qt.ElideMiddle, int(text_rect.width())))
        p.restore()


class FileGrid(QListView):
    def __init__(self, thumbs: ThumbnailCache, theme: Theme, parent=None):
        super().__init__(parent)
        self.setObjectName("Grid")
        self.delegate = GridDelegate(thumbs, theme, self)
        self.setItemDelegate(self.delegate)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setSpacing(0)
        self.setWrapping(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.verticalScrollBar().setSingleStep(24)
        thumbs.ready.connect(lambda _key: self.viewport().update())
        self.set_cell("M")

    def set_theme(self, theme: Theme) -> None:
        self.delegate.theme = theme
        self.viewport().update()

    def set_cell(self, size_key: str, scale: float = 1.0) -> None:
        self._base = int(GRID_SIZES.get(size_key, GRID_SIZES["M"]) * scale)
        self._fit()

    def _fit(self) -> None:
        """Stretch cells so each row fills the width, like a justified card grid."""
        base = getattr(self, "_base", GRID_SIZES["M"])
        width = max(1, self.viewport().width() - 2)
        cols = max(1, width // base)
        cell = width // cols
        self.delegate.cell = cell
        fm = QFontMetrics(self.font())
        size = QSize(cell, cell + fm.height() + 12)
        if self.gridSize() != size:
            self.setGridSize(size)
            self.doItemsLayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()
