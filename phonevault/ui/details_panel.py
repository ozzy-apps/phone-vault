"""Right-hand inspector: preview, why a file was sorted where it is, and its metadata."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from ..core.metadata import ImageProbe
from ..core.models import CATEGORY_INFO, Confidence, Kind, MediaFile, human_size
from ..core.sources.base import Source
from . import icons
from .themes import Theme
from .workers import load_preview, run_task

_KIND_ICON = {Kind.IMAGE: "image", Kind.VIDEO: "video", Kind.AUDIO: "audio"}


def _tilde(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home + "/") else path
PREVIEW_BOX = QSize(640, 640)


class DetailsPanel(QFrame):
    open_requested = Signal(object)
    reveal_requested = Signal(object)
    reveal_backup_requested = Signal(object)

    FIELDS = ("Category", "Match", "Why", "Origin", "Date", "Camera", "Dimensions", "Size", "On phone", "Backup")

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.theme = theme
        self._source: Source | None = None
        self._file: MediaFile | None = None
        self._token = 0
        self._image = None
        self._info_open = True

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        title = QLabel("Details")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        self.name = QLineEdit()
        self.name.setReadOnly(True)
        self.name.setPlaceholderText("No file chosen")
        root.addWidget(self.name)
        self.caption = QLabel("")
        self.caption.setObjectName("Caption")
        self.caption.setWordWrap(True)
        root.addWidget(self.caption)

        self.preview = QLabel()
        self.preview.setObjectName("Preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        root.addWidget(self.preview)

        self.info_toggle = QToolButton()
        self.info_toggle.setObjectName("Flat")
        self.info_toggle.setText("Info")
        self.info_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.info_toggle.clicked.connect(self._toggle_info)
        header = QFrame()
        header.setObjectName("InfoHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(4, 2, 4, 2)
        hl.addWidget(self.info_toggle)
        hl.addStretch(1)
        root.addWidget(header)

        self.info = QWidget()
        grid = QGridLayout(self.info)
        grid.setContentsMargins(6, 2, 2, 2)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)
        self.values: dict[str, QLabel] = {}
        for row, key in enumerate(self.FIELDS):
            k = QLabel(key)
            k.setObjectName("KeyLabel")
            k.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            v = QLabel("")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            grid.addWidget(k, row, 0)
            grid.addWidget(v, row, 1)
            self.values[key] = v
        root.addWidget(self.info)
        root.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(lambda: self._file and self.open_requested.emit(self._file))
        self.reveal_btn = QPushButton("Show in folder")
        self.reveal_btn.clicked.connect(lambda: self._file and self.reveal_requested.emit(self._file))
        self.backup_btn = QPushButton("Show backup")
        self.backup_btn.clicked.connect(lambda: self._file and self.reveal_backup_requested.emit(self._file))
        buttons.addWidget(self.open_btn)
        buttons.addWidget(self.reveal_btn)
        buttons.addStretch(1)
        root.addLayout(buttons)
        second = QHBoxLayout()
        second.addWidget(self.backup_btn)
        second.addStretch(1)
        root.addLayout(second)
        self.set_theme(theme)
        self.clear()

    # --- public -----------------------------------------------------------
    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.info_toggle.setIcon(icons.icon("chevron-down" if self._info_open else "chevron-right", theme.text_muted))
        self.open_btn.setIcon(icons.icon("open", theme.text))
        self.reveal_btn.setIcon(icons.icon("folder", theme.text))
        self.backup_btn.setIcon(icons.icon("folder", theme.text))
        if self._file is not None and self._image is None:
            self._show_placeholder(self._file)
        self._refresh_match_color()

    def set_source(self, source: Source | None) -> None:
        self._source = source
        self.clear()

    def clear(self) -> None:
        self._file = None
        self._token += 1
        self._image = None
        self.name.clear()
        self.caption.setText("Select a file to see where it came from and why it was sorted there.")
        self.preview.clear()
        self.preview.setText("")
        self.preview.hide()
        for v in self.values.values():
            v.setText("")
        self.info.setVisible(False)
        self.info_toggle.parentWidget().setVisible(False)
        self.open_btn.setEnabled(False)
        self.reveal_btn.setEnabled(False)
        self.open_btn.hide()
        self.reveal_btn.hide()
        self.backup_btn.hide()

    def show_selection(self, files: list[MediaFile]) -> None:
        if not files:
            self.clear()
            return
        if len(files) == 1:
            self.show_file(files[0])
            return
        self.clear()
        self.name.setText(f"{len(files):,} files selected")
        self.caption.setText(f"{human_size(sum(f.size for f in files))} in total")

    def refresh(self) -> None:
        """Re-read the current file's fields (e.g. after a backup)."""
        if self._file is not None:
            self._fill(self._file)
            self.backup_btn.setVisible(self._file.backed_up)

    def show_file(self, f: MediaFile) -> None:
        self._file = f
        self._token += 1
        token = self._token
        self._image = None
        info = CATEGORY_INFO[f.category]
        self.name.setText(f.name)
        self.name.setCursorPosition(0)
        self.caption.setText(f"{info.label} · in {f.folder or 'storage root'}")
        self.info_toggle.parentWidget().setVisible(True)
        self.info.setVisible(self._info_open)
        self._fill(f)
        self.open_btn.show()
        self.reveal_btn.setVisible(self._source is not None and self._source.local_path(f.rel_path) is not None)
        self.backup_btn.setVisible(f.backed_up)
        self.open_btn.setEnabled(self._source is not None)
        self.reveal_btn.setEnabled(self._source is not None and self._source.local_path(f.rel_path) is not None)
        self.preview.show()
        self._show_placeholder(f)
        if self._source is not None and (f.kind == Kind.IMAGE):
            self.preview.setText("Loading preview…")
            run_task(load_preview, self._source, f, PREVIEW_BOX,
                     on_done=lambda res, tok=token: self._on_preview(tok, res))

    # --- internals --------------------------------------------------------
    def _fill(self, f: MediaFile, probe: ImageProbe | None = None) -> None:
        camera = f.camera
        width, height = f.width, f.height
        if probe is not None:
            width, height = probe.width, probe.height
            if probe.has_camera:
                model = probe.model
                make = probe.make.capitalize() if probe.make.islower() else probe.make
                camera = model if model.lower().startswith(make.lower()) else f"{make} {model}".strip()
        v = self.values
        v["Category"].setText(CATEGORY_INFO[f.category].label)
        v["Match"].setText(f.confidence.label)
        v["Why"].setText(f.reason)
        v["Origin"].setText(f.origin or "—")
        date = f.taken_at.strftime("%Y-%m-%d %H:%M") if f.taken_at else "—"
        v["Date"].setText(f"{date}  ·  from {f.date_source}" if f.taken_at else date)
        v["Camera"].setText(camera or ("none in file" if (f.probed or probe) else "not read"))
        v["Dimensions"].setText(f"{width} × {height}" if width and height else "—")
        v["Size"].setText(f"{human_size(f.size)}  ({f.size:,} bytes)")
        v["On phone"].setText(f.rel_path)
        if f.backed_up:
            v["Backup"].setText(f"Backed up {f.backed_up_at.replace('T', ' ')[:16]}\n{_tilde(f.backup_dest)}")
            v["Backup"].setStyleSheet(f"color: {self.theme.accent};")
        else:
            v["Backup"].setText("Not backed up")
            v["Backup"].setStyleSheet("")
        self._refresh_match_color()

    def _refresh_match_color(self) -> None:
        label = self.values.get("Match")
        if label is None:
            return
        guess = self._file is not None and self._file.confidence == Confidence.GUESS
        label.setStyleSheet(f"color: {self.theme.warning};" if guess else "")

    def _show_placeholder(self, f: MediaFile) -> None:
        if f.kind == Kind.IMAGE and self._image is not None:
            return
        pm = icons.pixmap(_KIND_ICON.get(f.kind, "file"), self.theme.text_muted, 56)
        self.preview.setPixmap(pm)

    def _on_preview(self, token: int, result) -> None:
        if token != self._token or self._file is None:
            return
        f, image, probe = result
        if probe is not None:
            self._fill(f, probe)
        if image is None:
            self._show_placeholder(f)
            return
        self._image = image
        self._render_image()

    def _render_image(self) -> None:
        if self._image is None:
            return
        box = self.preview.contentsRect().size()
        max_h = max(180, min(420, int(self.width() * 0.9)))
        target = QSize(max(10, box.width() - 8), max_h - 8)
        pm = QPixmap.fromImage(self._image).scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setMinimumHeight(min(max_h, pm.height() + 12))
        self.preview.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._render_image()

    def _toggle_info(self) -> None:
        self._info_open = not self._info_open
        self.info.setVisible(self._info_open and self._file is not None)
        self.info_toggle.setIcon(icons.icon("chevron-down" if self._info_open else "chevron-right",
                                            self.theme.text_muted))
