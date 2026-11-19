"""Preferences. Every change applies immediately."""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSlider, QTabWidget,
    QVBoxLayout, QWidget,
)

from ..core.settings import Settings
from .branding import theme_preview
from .themes import all_themes, resolve_theme, themes_dir, write_theme_template

METADATA_LABELS = {
    "smart": "Smart — read photo metadata when folder and filename aren't conclusive",
    "all": "All images — most accurate, slower over USB",
    "off": "Off — sort by folder and filename only",
}


class SettingsDialog(QDialog):
    changed = Signal(object)  # Settings

    def __init__(self, settings: Settings, detected_cameras: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(560, 520)
        self.s = settings.copy()
        self._detected = detected_cameras

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._appearance_tab(), "Appearance")
        tabs.addTab(self._sorting_tab(), "Sorting")
        tabs.addTab(self._scanning_tab(), "Scanning")
        root.addWidget(tabs)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        box.accepted.connect(self.accept)
        root.addWidget(box)

    # --- tabs -----------------------------------------------------------------
    def _appearance_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(12, 14, 12, 12)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        outer.addLayout(form)
        outer.addStretch(1)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.theme_list = QListWidget()
        self.theme_list.setIconSize(QSize(40, 22))
        self.theme_list.setMaximumHeight(190)
        self._fill_themes()
        self.theme_list.currentItemChanged.connect(self._on_theme)
        theme_col = QVBoxLayout()
        theme_col.addWidget(self.theme_list)
        row = QHBoxLayout()
        row.setSpacing(6)
        new_btn = QPushButton("New theme from current")
        new_btn.clicked.connect(self._new_theme)
        folder_btn = QPushButton("Open themes folder")
        folder_btn.clicked.connect(self._open_themes_folder)
        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self._fill_themes)
        row.addWidget(new_btn)
        row.addWidget(folder_btn)
        row.addWidget(reload_btn)
        row.addStretch(1)
        theme_col.addLayout(row)
        form.addRow("Theme", theme_col)

        accent_row = QHBoxLayout()
        accent_row.setSpacing(6)
        self.accent_btn = QPushButton()
        self.accent_btn.setFixedWidth(120)
        self.accent_btn.clicked.connect(self._pick_accent)
        self.accent_reset = QPushButton("Use theme accent")
        self.accent_reset.clicked.connect(self._reset_accent)
        accent_row.addWidget(self.accent_btn)
        accent_row.addWidget(self.accent_reset)
        accent_row.addStretch(1)
        form.addRow("Accent", accent_row)
        self._sync_accent()

        scale_row = QHBoxLayout()
        self.scale = QSlider(Qt.Horizontal)
        self.scale.setRange(80, 150)
        self.scale.setSingleStep(5)
        self.scale.setPageStep(10)
        self.scale.setValue(int(round(self.s.font_scale * 100)))
        self.scale_label = QLabel(f"{self.scale.value()}%")
        self.scale_label.setObjectName("Mono")
        self.scale_label.setFixedWidth(44)
        self.scale.sliderReleased.connect(self._on_scale)
        self.scale.valueChanged.connect(lambda v: self.scale_label.setText(f"{v}%"))
        self.scale.valueChanged.connect(lambda _v: not self.scale.isSliderDown() and self._on_scale())
        scale_row.addWidget(self.scale, 1)
        scale_row.addWidget(self.scale_label)
        form.addRow("Interface size", scale_row)

        self.density = QComboBox()
        self.density.addItem("Comfortable", "comfortable")
        self.density.addItem("Compact", "compact")
        self.density.setCurrentIndex(max(0, self.density.findData(self.s.density)))
        self.density.currentIndexChanged.connect(lambda _i: self._set("density", self.density.currentData()))
        form.addRow("Density", self.density)

        self.details = QCheckBox("Show the details panel")
        self.details.setChecked(self.s.show_details)
        self.details.toggled.connect(lambda v: self._set("show_details", v))
        form.addRow("", self.details)
        return w

    def _sorting_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(12, 14, 12, 12)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        outer.addLayout(form)
        outer.addStretch(1)
        form.setVerticalSpacing(12)
        self.meta = QComboBox()
        for key, label in METADATA_LABELS.items():
            self.meta.addItem(label, key)
        self.meta.setCurrentIndex(max(0, self.meta.findData(self.s.metadata_mode)))
        self.meta.currentIndexChanged.connect(lambda _i: self._set("metadata_mode", self.meta.currentData()))
        form.addRow("Photo metadata", self.meta)

        self.cameras = QPlainTextEdit("\n".join(self.s.own_cameras))
        self.cameras.setPlaceholderText("One camera model per line, e.g. Pixel 8 or SM-S918B")
        self.cameras.setMaximumHeight(110)
        self.cameras.textChanged.connect(self._on_cameras)
        form.addRow("Your cameras", self.cameras)
        detected = ", ".join(self._detected) if self._detected else "none yet — scan your phone first"
        hint = QLabel(f"Detected from your camera folder: {detected}.\n"
                      "Photos with camera data from any other model are sorted as Received photos.")
        hint.setObjectName("Caption")
        hint.setWordWrap(True)
        form.addRow("", hint)
        return w

    def _scanning_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(12, 14, 12, 12)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        outer.addLayout(form)
        outer.addStretch(1)
        form.setVerticalSpacing(12)
        self.excludes = QPlainTextEdit("\n".join(self.s.exclude_patterns))
        self.excludes.setPlaceholderText("Android/data\n.thumbnails\n*.tmp")
        self.excludes.setMaximumHeight(130)
        self.excludes.textChanged.connect(
            lambda: self._set("exclude_patterns",
                              [l.strip() for l in self.excludes.toPlainText().splitlines() if l.strip()]))
        form.addRow("Skip", self.excludes)
        hint = QLabel("Folder paths (Android/data) skip everything inside them; names with * match "
                      "any file or folder name.")
        hint.setObjectName("Caption")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self.hidden = QCheckBox("Include hidden files and folders (names starting with a dot)")
        self.hidden.setChecked(self.s.include_hidden)
        self.hidden.toggled.connect(lambda v: self._set("include_hidden", v))
        form.addRow("", self.hidden)

        adb_row = QHBoxLayout()
        self.adb = QLineEdit(self.s.adb_path)
        self.adb.setPlaceholderText("Automatic (adb from PATH or Android SDK)")
        self.adb.editingFinished.connect(lambda: self._set("adb_path", self.adb.text().strip()))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_adb)
        adb_row.addWidget(self.adb, 1)
        adb_row.addWidget(browse)
        form.addRow("ADB", adb_row)
        return w

    # --- handlers -------------------------------------------------------------
    def _set(self, key: str, value) -> None:
        if getattr(self.s, key) == value:
            return
        setattr(self.s, key, value)
        self.changed.emit(self.s.copy())

    def _fill_themes(self) -> None:
        self.theme_list.blockSignals(True)
        self.theme_list.clear()
        for key, theme in all_themes().items():
            item = QListWidgetItem(QIcon(theme_preview(theme)), theme.name)
            item.setData(Qt.UserRole, key)
            if key.startswith("user:"):
                item.setToolTip(str(themes_dir() / f"{key[5:]}.json"))
            self.theme_list.addItem(item)
            if key == self.s.theme:
                self.theme_list.setCurrentItem(item)
        self.theme_list.blockSignals(False)

    def _on_theme(self, item, _prev) -> None:
        if item is not None:
            self._set("theme", item.data(Qt.UserRole))
            self._sync_accent()

    def _sync_accent(self) -> None:
        theme = resolve_theme(self.s.theme, self.s.accent_override)
        c = QColor(theme.accent)
        fg = "#10141a" if c.lightnessF() > 0.6 else "#ffffff"
        self.accent_btn.setText(theme.accent)
        self.accent_btn.setStyleSheet(f"background: {theme.accent}; color: {fg}; border: none;")
        self.accent_reset.setEnabled(bool(self.s.accent_override))

    def _pick_accent(self) -> None:
        current = QColor(resolve_theme(self.s.theme, self.s.accent_override).accent)
        color = QColorDialog.getColor(current, self, "Accent colour")
        if color.isValid():
            self._set("accent_override", color.name())
            self._sync_accent()

    def _reset_accent(self) -> None:
        self._set("accent_override", "")
        self._sync_accent()

    def _on_scale(self) -> None:
        self._set("font_scale", round(self.scale.value() / 100, 2))

    def _on_cameras(self) -> None:
        cams = [l.strip() for l in self.cameras.toPlainText().splitlines() if l.strip()]
        self._set("own_cameras", cams)

    def _new_theme(self) -> None:
        path = write_theme_template(resolve_theme(self.s.theme, self.s.accent_override))
        self._fill_themes()
        self._open_path(path)

    def _open_themes_folder(self) -> None:
        themes_dir().mkdir(parents=True, exist_ok=True)
        self._open_path(themes_dir())

    @staticmethod
    def _open_path(path) -> None:
        try:
            subprocess.Popen(["xdg-open", str(path)])
        except OSError:
            pass

    def _browse_adb(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose adb executable")
        if path:
            self.adb.setText(path)
            self._set("adb_path", path)
