"""Back up: choose where and how, see what will be copied, then start."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)

from ..core.backup import BackupOptions, BackupPlan, archive_path, plan_backup
from ..core.models import CATEGORIES_IN_ORDER, CATEGORY_INFO, Category, MediaFile, human_size
from ..core.settings import Settings
from .branding import swatch
from .themes import Theme
from .widgets import Segmented


def _tilde(path: Path) -> str:
    home = str(Path.home())
    s = str(path)
    return "~" + s[len(home):] if s.startswith(home) else s


class BackupDialog(QDialog):
    def __init__(self, files: list[MediaFile], settings: Settings, device_folder: str, title: str,
                 theme: Theme, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Back up")
        self.setMinimumWidth(640)
        self.files = files
        self.settings = settings.copy()
        self.theme = theme
        self.plan: BackupPlan | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)
        head = QLabel(f"Back up {title}")
        head.setObjectName("PanelTitle")
        root.addWidget(head)
        self.summary = QLabel()
        self.summary.setObjectName("Mono")
        root.addWidget(self.summary)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        dest_row = QHBoxLayout()
        self.dest = QLineEdit(str(self.settings.backup_root_path()))
        self.dest.textChanged.connect(self._update)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        dest_row.addWidget(self.dest, 1)
        dest_row.addWidget(browse)
        form.addRow("Destination", dest_row)

        self.folder = QLineEdit(device_folder)
        self.folder.setToolTip("Folder for this phone inside the destination. Keep it the same between backups.")
        self.folder.textChanged.connect(self._update)
        form.addRow("Phone folder", self.folder)

        self.layout_seg = Segmented([("category", "By category"), ("date", "By date"), ("phone", "Same as phone")],
                                    self.settings.backup_layout)
        self.layout_seg.changed.connect(lambda _k: self._update())
        lay_row = QHBoxLayout()
        lay_row.addWidget(self.layout_seg)
        lay_row.addStretch(1)
        form.addRow("Layout", lay_row)
        self.example = QLabel()
        self.example.setObjectName("Mono")
        self.example.setWordWrap(False)
        self.example.setMinimumWidth(10)
        self.example.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("", self.example)

        self.verify_seg = Segmented([("size", "Size check"), ("checksum", "Checksum on the phone")],
                                    self.settings.backup_verify)
        self.verify_seg.setToolTip("Every copy gets a SHA-256 fingerprint. Checksum mode also has the phone compute "
                                   "one and compares them, which reads every file twice.")
        self.verify_seg.changed.connect(lambda _k: self._update())
        ver_row = QHBoxLayout()
        ver_row.addWidget(self.verify_seg)
        ver_row.addStretch(1)
        form.addRow("Verify", ver_row)

        self.skip_list = QListWidget()
        self.skip_list.setMaximumHeight(168)
        self.skip_list.itemChanged.connect(lambda _i: self._update())
        form.addRow("Include", self.skip_list)
        self.skip_sent = QCheckBox()
        self.skip_sent.setChecked(self.settings.backup_skip_sent)
        self.skip_sent.toggled.connect(lambda _v: self._update())
        form.addRow("", self.skip_sent)
        self.space = QLabel()
        form.addRow("Space", self.space)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.start = QPushButton("Start backup")
        self.start.setObjectName("Primary")
        self.start.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.start)
        root.addLayout(buttons)
        self._fill_categories()
        self._update()

    # ------------------------------------------------------------------
    def _fill_categories(self) -> None:
        pending = [f for f in self.files if not f.backed_up]
        counts = Counter(f.category for f in pending)
        sizes: Counter = Counter()
        for f in pending:
            sizes[f.category] += f.size
        skip = set(self.settings.backup_skip_categories)
        self.skip_list.blockSignals(True)
        for cat in CATEGORIES_IN_ORDER:
            if not counts[cat]:
                continue
            info = CATEGORY_INFO[cat]
            item = QListWidgetItem(QIcon(swatch(info.color)), f"{info.label}  ·  {counts[cat]:,} · {human_size(sizes[cat])}")
            item.setData(Qt.UserRole, cat.value)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if cat.value in skip else Qt.Checked)
            self.skip_list.addItem(item)
        self.skip_list.blockSignals(False)
        sent = sum(1 for f in pending if f.sent)
        self.skip_sent.setText(f"Skip copies you sent in chats ({sent:,}) — compressed duplicates of your photos")
        self.skip_sent.setVisible(sent > 0)

    def options(self) -> BackupOptions:
        skip = {Category(self.skip_list.item(i).data(Qt.UserRole)) for i in range(self.skip_list.count())
                if self.skip_list.item(i).checkState() != Qt.Checked}
        return BackupOptions(
            root=Path(self.dest.text().strip() or str(self.settings.backup_root_path())).expanduser(),
            device_folder=self.folder.text().strip() or "Phone",
            layout=self.layout_seg.value() or "category",
            verify=self.verify_seg.value() or "size",
            skip_categories=skip,
            skip_sent=self.skip_sent.isChecked() and self.skip_sent.isVisible(),
        )

    def _update(self) -> None:
        opts = self.options()
        self.plan = plan = plan_backup(self.files, opts)
        n, size = len(plan.to_copy), plan.bytes_to_copy
        parts = [f"{n:,} files to copy · {human_size(size)}"]
        if plan.already:
            parts.append(f"{len(plan.already):,} already backed up")
        if plan.skipped:
            parts.append(f"{len(plan.skipped):,} skipped")
        self.summary.setText("  ·  ".join(parts))
        sample = next((f for f in plan.to_copy), None) or (self.files[0] if self.files else None)
        if sample is not None:
            path = opts.root / opts.device_folder / archive_path(sample, opts.layout)
            text = _tilde(path)
            self.example.setToolTip(text)
            self.example.setText(self.example.fontMetrics().elidedText(text, Qt.ElideMiddle, 470))
        fits = plan.fits
        self.space.setText(f"{human_size(size)} needed · {human_size(plan.free_bytes)} free on that drive")
        self.space.setObjectName("" if fits else "Warning")
        self.space.setStyleSheet("" if fits else f"color: {self.theme.warning};")
        self.start.setEnabled(n > 0 and fits)
        self.start.setText("Start backup" if n else "Nothing new to back up")

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Backup destination", self.dest.text())
        if folder:
            self.dest.setText(folder)

    def updated_settings(self) -> Settings:
        """Settings with this dialog's choices remembered."""
        opts = self.options()
        s = self.settings
        default = Path.home() / "Phone Vault"
        s.backup_root = "" if opts.root == default else str(opts.root)
        s.backup_layout = opts.layout
        s.backup_verify = opts.verify
        s.backup_skip_categories = sorted(c.value for c in opts.skip_categories)
        s.backup_skip_sent = opts.skip_sent
        return s
