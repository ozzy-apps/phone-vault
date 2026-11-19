"""Sidebar navigation lists, painted like Inca's library sidebar:
uppercase section labels, rounded selection, right-aligned monospace counts."""

from __future__ import annotations

from collections import Counter, defaultdict

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QAbstractItemView, QStyle, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem

from ..core.models import CATEGORIES_IN_ORDER, CATEGORY_INFO, GROUPS, Category, Confidence, MediaFile, human_size
from .themes import Theme

ROLE = Qt.UserRole + 1
COUNT_ROLE = Qt.UserRole + 2
SIZE_ROLE = Qt.UserRole + 3
COLOR_ROLE = Qt.UserRole + 4


class _NavDelegate(QStyledItemDelegate):
    def __init__(self, nav: "NavList"):
        super().__init__(nav)
        self.nav = nav

    def sizeHint(self, option, index):
        kind = (index.data(ROLE) or ("item", None))[0]
        fm = QFontMetrics(option.font)
        return QSize(option.rect.width(), int(fm.height() * (2.1 if kind == "section" else 1.85)))

    def paint(self, p: QPainter, option, index):
        t = self.nav.theme
        kind = (index.data(ROLE) or ("item", None))[0]
        r = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if kind == "section":
            f = QFont(option.font)
            f.setPointSizeF(f.pointSizeF() * 0.8)
            f.setWeight(QFont.DemiBold)
            f.setLetterSpacing(QFont.PercentageSpacing, 108)
            p.setFont(f)
            p.setPen(QColor(t.text_muted))
            p.drawText(r.adjusted(8, 0, -8, -3), Qt.AlignLeft | Qt.AlignBottom, index.data(Qt.DisplayRole).upper())
            p.restore()
            return

        box = r.adjusted(2, 1, -2, -1)
        if option.state & QStyle.State_Selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.sel_strong))
            p.drawRoundedRect(box, 4, 4)
        elif option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(t.q("raised", 0.45))
            p.drawRoundedRect(box, 4, 4)

        x = box.left() + 8
        color = index.data(COLOR_ROLE)
        if color:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, box.center().y() - 4.5, 9, 9), 2.5, 2.5)
            x += 17

        mono = self.nav.mono or option.font
        mfm = QFontMetrics(mono)
        right = box.right() - 8
        size = index.data(SIZE_ROLE) or ""
        count = index.data(COUNT_ROLE) or ""
        p.setFont(mono)
        p.setPen(QColor(t.text_muted))
        if size:
            w = mfm.horizontalAdvance("000.0 MB")
            p.drawText(QRectF(right - w, box.top(), w, box.height()), Qt.AlignRight | Qt.AlignVCenter, size)
            right -= w + 10
        if count:
            w = max(mfm.horizontalAdvance("0000"), mfm.horizontalAdvance(count))
            p.drawText(QRectF(right - w, box.top(), w, box.height()), Qt.AlignRight | Qt.AlignVCenter, count)
            right -= w + 10

        p.setFont(option.font)
        p.setPen(QColor(t.text))
        fm = QFontMetrics(option.font)
        label = fm.elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, int(right - x))
        p.drawText(QRectF(x, box.top(), right - x, box.height()), Qt.AlignLeft | Qt.AlignVCenter, label)
        p.restore()


class NavList(QTreeWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.mono: QFont | None = None
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setUniformRowHeights(False)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setItemDelegate(_NavDelegate(self))

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.viewport().update()

    def add_section(self, title: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title])
        item.setData(0, ROLE, ("section", title))
        item.setFlags(Qt.ItemIsEnabled)
        self.addTopLevelItem(item)
        return item

    def add_entry(self, label: str, key, count: str = "", size: str = "", color: str = "",
                  tooltip: str = "") -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        item.setData(0, ROLE, key)
        item.setData(0, COUNT_ROLE, count)
        item.setData(0, SIZE_ROLE, size)
        item.setData(0, COLOR_ROLE, color)
        if tooltip:
            item.setToolTip(0, tooltip)
        self.addTopLevelItem(item)
        return item

    def content_height(self) -> int:
        h = 0
        for i in range(self.topLevelItemCount()):
            h += self.sizeHintForIndex(self.indexFromItem(self.topLevelItem(i))).height()
        return h + 4


class CategoryPanel(NavList):
    """All files + categories grouped as Yours / Chats / Received / Files."""

    selection_changed = Signal(object)  # None (all) or set[Category]

    def __init__(self, theme: Theme, parent=None):
        super().__init__(theme, parent)
        self._files: list[MediaFile] = []
        self.itemSelectionChanged.connect(self._emit)

    def _current_key(self):
        items = self.selectedItems()
        return items[0].data(0, ROLE) if items else ("all", None)

    def populate(self, files: list[MediaFile], keep_selection: bool = False) -> None:
        key = self._current_key() if keep_selection else ("all", None)
        self._files = files
        self.blockSignals(True)
        self.clear()
        if not files:
            self.blockSignals(False)
            return
        counts: dict[Category, int] = defaultdict(int)
        sizes: dict[Category, int] = defaultdict(int)
        for f in files:
            counts[f.category] += 1
            sizes[f.category] += f.size
        self.add_section("Library")
        restore = self.add_entry("All files", ("all", None), f"{len(files):,}", human_size(sum(sizes.values())))
        for group in GROUPS:
            cats = [c for c in CATEGORIES_IN_ORDER if CATEGORY_INFO[c].group == group and counts[c]]
            if not cats:
                continue
            self.add_section(group)
            for c in cats:
                info = CATEGORY_INFO[c]
                item = self.add_entry(info.label, ("cat", c), f"{counts[c]:,}", human_size(sizes[c]), info.color,
                                      f"{info.label}: {counts[c]:,} files, {human_size(sizes[c])}")
                if key == ("cat", c):
                    restore = item
        restore.setSelected(True)
        self.setCurrentItem(restore)
        self.blockSignals(False)
        self._emit()

    def select_category(self, cat: Category | None) -> None:
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            kind, value = item.data(0, ROLE)
            if (cat is None and kind == "all") or (kind == "cat" and value == cat):
                self.setCurrentItem(item)
                item.setSelected(True)
                return

    def _emit(self) -> None:
        kind, value = self._current_key()
        self.selection_changed.emit(None if kind != "cat" else {value})


class MatchPanel(NavList):
    """Filter by how certain the sorting is."""

    selection_changed = Signal(object)  # None or Confidence

    LABELS = {
        Confidence.SURE: "Folder or metadata is conclusive",
        Confidence.LIKELY: "Strong hint, worth a glance",
        Confidence.GUESS: "Review these",
    }

    def __init__(self, theme: Theme, parent=None):
        super().__init__(theme, parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.itemSelectionChanged.connect(self._emit)

    def populate(self, files: list[MediaFile]) -> None:
        current = self.selectedItems()[0].data(0, ROLE) if self.selectedItems() else ("any", None)
        counts = Counter(f.confidence for f in files)
        self.blockSignals(True)
        self.clear()
        if files:
            self.add_section("Match")
            restore = self.add_entry("Any", ("any", None), f"{len(files):,}")
            for conf in Confidence:
                color = self.theme.warning if conf == Confidence.GUESS else ""
                item = self.add_entry(conf.label, ("conf", conf), f"{counts[conf]:,}", "", color, self.LABELS[conf])
                if current == ("conf", conf):
                    restore = item
            restore.setSelected(True)
            self.setCurrentItem(restore)
        self.setFixedHeight(self.content_height() if files else 0)
        self.blockSignals(False)
        self._emit()

    def _emit(self) -> None:
        items = self.selectedItems()
        key = items[0].data(0, ROLE) if items else ("any", None)
        self.selection_changed.emit(key[1] if key[0] == "conf" else None)


class BackupPanel(NavList):
    """Filter by backup state."""

    selection_changed = Signal(object)  # None, True (backed up) or False (not yet)

    def __init__(self, theme: Theme, parent=None):
        super().__init__(theme, parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.itemSelectionChanged.connect(self._emit)

    def populate(self, files: list[MediaFile]) -> None:
        current = self.selectedItems()[0].data(0, ROLE) if self.selectedItems() else ("any", None)
        done = [f for f in files if f.backed_up]
        todo = [f for f in files if not f.backed_up]
        self.blockSignals(True)
        self.clear()
        if files:
            self.add_section("Backup")
            restore = self.add_entry("Any", ("any", None), f"{len(files):,}")
            new = self.add_entry("Not backed up", ("state", False), f"{len(todo):,}",
                                 human_size(sum(f.size for f in todo)))
            old = self.add_entry("Backed up", ("state", True), f"{len(done):,}",
                                 human_size(sum(f.size for f in done)), self.theme.accent)
            restore = {("state", False): new, ("state", True): old}.get(current, restore)
            restore.setSelected(True)
            self.setCurrentItem(restore)
        self.setFixedHeight(self.content_height() if files else 0)
        self.blockSignals(False)
        self._emit()

    def _emit(self) -> None:
        items = self.selectedItems()
        key = items[0].data(0, ROLE) if items else ("any", None)
        self.selection_changed.emit(key[1] if key[0] == "state" else None)

