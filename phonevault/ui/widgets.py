"""Small reusable widgets: segmented toggles and the device pill."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QMenu, QToolButton

from ..core.sources.discovery import SourceDescriptor
from .themes import Theme


class Segmented(QFrame):
    """Pill group of mutually exclusive toggles, e.g. [Grid | List]."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        for key, label in options:
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setCursor(Qt.PointingHandCursor)
            self._group.addButton(b)
            self._buttons[key] = b
            lay.addWidget(b)
            b.clicked.connect(lambda _c=False, k=key: self.changed.emit(k))
        self.set_value(current)

    def set_value(self, key: str) -> None:
        b = self._buttons.get(key)
        if b is not None:
            b.setChecked(True)

    def value(self) -> str:
        for key, b in self._buttons.items():
            if b.isChecked():
                return key
        return ""

    def set_icons(self, mapping: dict[str, QIcon]) -> None:
        for key, ic in mapping.items():
            b = self._buttons.get(key)
            if b is not None:
                b.setIcon(ic)
                b.setIconSize(QSize(14, 14))
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)


def _dot(color: str, size: int = 10) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


class DevicePill(QToolButton):
    """Shows the selected phone and its state; click for the device menu."""

    selected = Signal(object)  # SourceDescriptor
    choose_folder = Signal()
    refresh = Signal()
    check = Signal()

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.setObjectName("Pill")
        self.theme = theme
        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setCursor(Qt.PointingHandCursor)
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self._devices: list[SourceDescriptor] = []
        self._current: SourceDescriptor | None = None
        self._searching = True
        self._render()

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self._render()

    def set_searching(self) -> None:
        self._searching = True
        self._render()

    def set_devices(self, devices: list[SourceDescriptor], prefer_key: str = "") -> None:
        """Update the list. Keeps the current pick while it's usable; otherwise switches to a ready
        real phone (never auto-picks an emulator over a phone)."""
        self._searching = False
        self._devices = devices
        keys = {d.key: d for d in devices}
        previous = self._current
        current = keys.get(previous.key) if previous else None
        if current is None and previous is not None and previous.kind == "folder":
            current = previous  # a folder picked this session stays selectable
            self._devices = devices + [previous]
        if current is None or not current.ready or current.emulator:
            phone = next((d for d in devices if d.ready and not d.emulator), None)
            preferred = keys.get(prefer_key)
            if preferred is not None and preferred.ready and not preferred.emulator:
                phone = preferred
            current = phone or current or preferred or next((d for d in devices if d.ready), None) \
                or (devices[0] if devices else None)
        changed = (previous is None) != (current is None) or (
            previous is not None and current is not None
            and (previous.key, previous.ready, previous.note) != (current.key, current.ready, current.note)
        )
        self._current = current
        self._render()
        if changed and current is not None:
            self.selected.emit(current)

    def add_and_select(self, desc: SourceDescriptor) -> None:
        if not any(d.key == desc.key for d in self._devices):
            self._devices.append(desc)
        self._current = desc
        self._render()
        self.selected.emit(desc)

    @property
    def current(self) -> SourceDescriptor | None:
        return self._current

    def _render(self) -> None:
        t = self.theme
        d = self._current
        if self._searching:
            self.setText("Looking for phones…")
            self.setIcon(_dot(t.text_muted))
            self.setToolTip("")
        elif d is None:
            self.setText("No phone found")
            self.setIcon(_dot(t.text_muted))
            self.setToolTip("Connect a phone over USB. Open Connection check if it doesn't appear.")
        else:
            self.setText(d.label if d.ready else f"{d.label} · {d.note}")
            self.setIcon(_dot(t.accent if d.ready else t.warning))
            self.setToolTip(d.note or d.ident)
        self._menu.clear()
        group = QActionGroup(self._menu)
        group.setExclusive(True)
        for dev in self._devices:
            text = dev.label if dev.ready else f"{dev.label} — {dev.note}"
            act = QAction(_dot(t.accent if dev.ready else t.warning), text, self._menu)
            act.setCheckable(True)
            act.setChecked(dev is self._current)
            act.triggered.connect(lambda _c=False, x=dev: self._pick(x))
            group.addAction(act)
            self._menu.addAction(act)
        if not self._devices:
            empty = self._menu.addAction("No phones found")
            empty.setEnabled(False)
        self._menu.addSeparator()
        self._menu.addAction("Choose folder…", self.choose_folder.emit)
        self._menu.addAction("Refresh devices", self.refresh.emit)
        self._menu.addAction("Connection check…", self.check.emit)

    def _pick(self, desc: SourceDescriptor) -> None:
        self._current = desc
        self._render()
        self.selected.emit(desc)
