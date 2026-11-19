from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from ..core.models import CATEGORY_INFO, Category, Confidence, Kind, MediaFile, human_size
from . import icons
from .themes import Theme

COLUMNS = ("Name", "Category", "Origin", "Date", "Size", "Match", "Backup", "Folder")
COL_NAME, COL_CATEGORY, COL_ORIGIN, COL_DATE, COL_SIZE, COL_MATCH, COL_BACKUP, COL_FOLDER = range(len(COLUMNS))
SORT_ROLE = Qt.UserRole + 1
FILE_ROLE = Qt.UserRole + 2

_KIND_ICON = {Kind.IMAGE: "image", Kind.VIDEO: "video", Kind.AUDIO: "audio"}


class FileTableModel(QAbstractTableModel):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.files: list[MediaFile] = []
        self.theme = theme
        self.mono = None  # QFont for numeric columns, set by the window

    def set_files(self, files: list[MediaFile]) -> None:
        self.beginResetModel()
        self.files = files
        self.endResetModel()

    def refresh(self) -> None:
        if self.files:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.files) - 1, len(COLUMNS) - 1))

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.refresh()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.files)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section].upper()
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole and section == COL_SIZE:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        f = self.files[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == COL_NAME:
                return f.name
            if col == COL_CATEGORY:
                return f.category_label
            if col == COL_ORIGIN:
                return f.origin
            if col == COL_DATE:
                return f.taken_at.strftime("%Y-%m-%d %H:%M") if f.taken_at else ""
            if col == COL_SIZE:
                return human_size(f.size)
            if col == COL_MATCH:
                return f.confidence.label
            if col == COL_BACKUP:
                return "Backed up" if f.backed_up else ""
            if col == COL_FOLDER:
                return f.folder
        elif role == SORT_ROLE:
            if col == COL_DATE:
                return f.timestamp
            if col == COL_SIZE:
                return f.size
            if col == COL_CATEGORY:
                return CATEGORY_INFO[f.category].order
            if col == COL_MATCH:
                return list(Confidence).index(f.confidence)
            if col == COL_BACKUP:
                return 1 if f.backed_up else 0
            return (self.data(index, Qt.DisplayRole) or "").lower()
        elif role == FILE_ROLE:
            return f
        elif role == Qt.DecorationRole and col == COL_NAME:
            return icons.icon(_KIND_ICON.get(f.kind, "file"), CATEGORY_INFO[f.category].color)
        elif role == Qt.ToolTipRole:
            if col == COL_MATCH or col == COL_CATEGORY:
                return f.reason
            if col == COL_NAME or col == COL_FOLDER:
                return f.rel_path
            if col == COL_DATE:
                return f"From {f.date_source}" if f.date_source else None
            if col == COL_BACKUP and f.backed_up:
                return f"{f.backup_dest}\nBacked up {f.backed_up_at.replace('T', ' ')}"
        elif role == Qt.ForegroundRole:
            if col == COL_MATCH and f.confidence == Confidence.GUESS:
                return QColor(self.theme.warning)
            if col == COL_BACKUP:
                return QColor(self.theme.accent)
            if col in (COL_FOLDER, COL_MATCH, COL_DATE, COL_SIZE):
                return QColor(self.theme.text_muted)
        elif role == Qt.FontRole and col in (COL_DATE, COL_SIZE) and self.mono is not None:
            return self.mono
        elif role == Qt.TextAlignmentRole and col == COL_SIZE:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None


class FileFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._categories: set[Category] | None = None
        self._confidence: Confidence | None = None
        self._backed_up: bool | None = None
        self._needle = ""
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(False)

    def set_categories(self, cats: set[Category] | None) -> None:
        self._categories = cats
        self.invalidateFilter()

    def set_confidence(self, conf: Confidence | None) -> None:
        self._confidence = conf
        self.invalidateFilter()

    def set_backup_state(self, backed_up: bool | None) -> None:
        self._backed_up = backed_up
        self.invalidateFilter()

    def set_text(self, text: str) -> None:
        self._needle = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        model: FileTableModel = self.sourceModel()
        f = model.files[row]
        if self._categories is not None and f.category not in self._categories:
            return False
        if self._confidence is not None and f.confidence != self._confidence:
            return False
        if self._backed_up is not None and f.backed_up != self._backed_up:
            return False
        if self._needle:
            hay = f"{f.rel_path} {f.origin} {f.camera} {f.reason} {f.category_label}".lower()
            return all(part in hay for part in self._needle.split())
        return True

    def visible_files(self) -> list[MediaFile]:
        return [self.data(self.index(r, 0), FILE_ROLE) for r in range(self.rowCount())]


class FileTable(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.verticalHeader().hide()
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        h = self.horizontalHeader()
        h.setHighlightSections(False)
        h.setSectionsMovable(True)
        h.setStretchLastSection(False)
        h.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        h.setSectionResizeMode(QHeaderView.Interactive)

    def apply_row_height(self, px: int) -> None:
        self.verticalHeader().setDefaultSectionSize(px)

    def default_widths(self, scale: float) -> None:
        h = self.horizontalHeader()
        h.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for col, w in ((COL_CATEGORY, 130), (COL_ORIGIN, 110), (COL_DATE, 125), (COL_SIZE, 70),
                       (COL_MATCH, 60), (COL_BACKUP, 82), (COL_FOLDER, 170)):
            self.setColumnWidth(col, int(w * scale))
        h.setMinimumSectionSize(int(48 * scale))
