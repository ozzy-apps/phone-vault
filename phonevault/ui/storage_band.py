from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..core.models import CATEGORIES_IN_ORDER, CATEGORY_INFO, Category, MediaFile, human_size
from .themes import Theme


class StorageBand(QWidget):
    """Horizontal bar: share of storage per category. Hover for details, click to filter."""

    category_clicked = Signal(object)

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._sizes: dict[Category, int] = {}
        self._counts: dict[Category, int] = {}
        self._highlight: set[Category] | None = None
        self._segments: list[tuple[QRectF, Category]] = []
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(14)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def set_scale(self, scale: float) -> None:
        self.setFixedHeight(max(10, round(14 * scale)))

    def set_files(self, files: list[MediaFile]) -> None:
        self._sizes, self._counts = {}, {}
        for f in files:
            self._sizes[f.category] = self._sizes.get(f.category, 0) + f.size
            self._counts[f.category] = self._counts.get(f.category, 0) + 1
        self.update()

    def set_highlight(self, cats: set[Category] | None) -> None:
        self._highlight = cats
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, r.height() / 2.4, r.height() / 2.4)
        p.setClipPath(clip)
        p.fillRect(r, QColor(self.theme.surface_alt))
        total = sum(self._sizes.values())
        self._segments = []
        if not total:
            return
        x = 0.0
        gap = 1.5
        for cat in CATEGORIES_IN_ORDER:
            size = self._sizes.get(cat, 0)
            if not size:
                continue
            w = max(3.0, r.width() * size / total)
            seg = QRectF(x, 0, w, r.height())
            color = QColor(CATEGORY_INFO[cat].color)
            if self._highlight is not None and cat not in self._highlight:
                color.setAlphaF(0.28)
            p.fillRect(seg.adjusted(0, 0, -gap, 0), color)
            self._segments.append((seg, cat))
            x += w

    def _cat_at(self, x: float) -> Category | None:
        for seg, cat in self._segments:
            if seg.left() <= x < seg.right():
                return cat
        return None

    def mouseMoveEvent(self, e):
        cat = self._cat_at(e.position().x())
        if cat is None:
            QToolTip.hideText()
            return
        total = sum(self._sizes.values()) or 1
        size = self._sizes[cat]
        text = (f"{CATEGORY_INFO[cat].label}: {human_size(size)} ({size / total:.0%}) · "
                f"{self._counts[cat]:,} files")
        QToolTip.showText(e.globalPosition().toPoint(), text, self)

    def mousePressEvent(self, e):
        cat = self._cat_at(e.position().x())
        if cat is not None:
            self.category_clicked.emit(cat)
