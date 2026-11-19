"""Help → Connection check: shows what's wrong with the phone connection and how to fix it."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from ..core.diagnostics import ConnectionReport, Finding, check_connection
from ..core.sources.adb import restart_adb_server
from . import icons
from .themes import Theme
from .workers import run_task


def _dot(color: str, size: int = 10) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return pm


class ConnectionDialog(QDialog):
    devices_changed = Signal()

    def __init__(self, theme: Theme, adb_setting: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connection check")
        self.setMinimumSize(620, 480)
        self.theme = theme
        self.adb_setting = adb_setting
        self.report: ConnectionReport | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)
        title = QLabel("Connection check")
        title.setObjectName("PanelTitle")
        root.addWidget(title)
        self.summary = QLabel("Checking…")
        self.summary.setObjectName("Caption")
        root.addWidget(self.summary)

        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.list_host)
        root.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        self.restart_btn = QPushButton("Restart ADB")
        self.restart_btn.clicked.connect(self._restart)
        self.copy_btn = QPushButton("Copy report")
        self.copy_btn.clicked.connect(self._copy)
        self.again_btn = QPushButton("Check again")
        self.again_btn.setObjectName("Primary")
        self.again_btn.clicked.connect(self.run_check)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(self.restart_btn)
        buttons.addWidget(self.copy_btn)
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(self.again_btn)
        root.addLayout(buttons)
        self.run_check()

    def run_check(self) -> None:
        self._busy("Checking…")
        run_task(check_connection, self.adb_setting, on_done=self._show, on_fail=lambda e: self._busy(e, False))

    def _busy(self, text: str, busy: bool = True) -> None:
        self.summary.setText(text)
        for b in (self.restart_btn, self.again_btn, self.copy_btn):
            b.setEnabled(not busy)

    def _show(self, report: ConnectionReport) -> None:
        self.report = report
        self._busy("", False)
        self.restart_btn.setEnabled(bool(report.adb_path))
        adb = f"adb {report.adb_version}" if report.adb_path else "adb not installed"
        phones = len([u for u in report.usb])
        self.summary.setText(f"{adb} · {phones} phone{'s' if phones != 1 else ''} on USB · "
                             f"{len(report.mounts)} File transfer mount{'s' if len(report.mounts) != 1 else ''}")
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, finding in enumerate(report.findings):
            self.list_layout.insertWidget(i, self._card(finding))
        self.devices_changed.emit()

    def _card(self, f: Finding) -> QWidget:
        t = self.theme
        color = {"ok": t.accent, "info": t.text_muted, "warn": t.warning, "error": t.danger}[f.level]
        card = QFrame()
        card.setObjectName("Panel")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        head = QHBoxLayout()
        dot = QLabel()
        dot.setPixmap(_dot(color))
        head.addWidget(dot, 0, Qt.AlignTop)
        title = QLabel(f.title)
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 600;")
        head.addWidget(title, 1)
        lay.addLayout(head)
        if f.detail:
            detail = QLabel(f.detail)
            detail.setObjectName("Caption")
            detail.setWordWrap(True)
            detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(detail)
        for cmd in f.commands:
            row = QHBoxLayout()
            code = QLabel(cmd)
            code.setObjectName("Mono")
            code.setTextInteractionFlags(Qt.TextSelectableByMouse)
            copy = QToolButton()
            copy.setObjectName("Flat")
            copy.setText("Copy")
            copy.clicked.connect(lambda _c=False, c=cmd: QGuiApplication.clipboard().setText(c))
            row.addWidget(code, 1)
            row.addWidget(copy)
            box = QFrame()
            box.setObjectName("InfoHeader")
            box.setLayout(row)
            row.setContentsMargins(8, 2, 4, 2)
            lay.addWidget(box)
        return card

    def _restart(self) -> None:
        if not self.report or not self.report.adb_path:
            return
        self._busy("Restarting ADB…")
        run_task(restart_adb_server, self.report.adb_path, on_done=lambda _o: self.run_check(),
                 on_fail=lambda e: self._busy(e, False))

    def _copy(self) -> None:
        if self.report:
            QGuiApplication.clipboard().setText(self.report.as_text())
            self.summary.setText("Report copied to the clipboard")
