from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, QItemSelectionModel, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenuBar, QMessageBox,
    QProgressBar, QPushButton, QSplitter, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from ..core.classifier import classify_all
from ..core.models import MediaFile, human_size
from ..core.scanner import ScanResult
from ..core.settings import Settings
from ..core.sources import SourceDescriptor, SourceError, discover_sources, find_adb, open_source
from . import icons
from .branding import AppMark, app_icon
from .category_panel import CategoryPanel, MatchPanel
from .details_panel import DetailsPanel
from .file_view import COL_DATE, COL_NAME, COL_SIZE, FILE_ROLE, FileFilterProxy, FileTable, FileTableModel
from .grid_view import FileGrid
from .settings_dialog import SettingsDialog
from .storage_band import StorageBand
from .style import apply_theme, mono_font
from .themes import all_themes, resolve_theme
from .thumbnails import ThumbnailCache
from .widgets import DevicePill, Segmented
from .workers import ScanThread, local_copy, run_task

SORT_COLUMNS = {"date": (COL_DATE, Qt.DescendingOrder), "name": (COL_NAME, Qt.AscendingOrder),
                "size": (COL_SIZE, Qt.DescendingOrder)}
PHASE_LABELS = {"Listing files": "Listing files", "Reading photo metadata": "Reading photo metadata",
                "Sorting": "Sorting", "Connecting": "Connecting"}


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.theme = resolve_theme(settings.theme, settings.accent_override)
        self.result: ScanResult | None = None
        self.source = None
        self.scan_thread: ScanThread | None = None
        self.adb_path: str | None = find_adb(settings.adb_path)
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.setMinimumSize(980, 600)

        self.thumbs = ThumbnailCache(self)
        self._build_ui()
        self._build_menus()
        self.apply_settings(settings, initial=True)
        self._restore_window()
        QTimer.singleShot(0, self.refresh_devices)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        t = self.theme
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar: mark, name, menus | device pill, scan
        top = QFrame()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(10, 4, 8, 4)
        tl.setSpacing(6)
        self.mark = AppMark(t, 20)
        tl.addWidget(self.mark)
        name = QLabel(APP_NAME)
        name.setObjectName("AppName")
        tl.addWidget(name)
        tl.addSpacing(8)
        self.menubar = QMenuBar()
        self.menubar.setNativeMenuBar(False)
        tl.addWidget(self.menubar)
        tl.addStretch(1)
        self.device = DevicePill(t)
        self.device.selected.connect(self._on_device_selected)
        self.device.choose_folder.connect(self.choose_folder)
        self.device.refresh.connect(self.refresh_devices)
        tl.addWidget(self.device)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_scan)
        self.stop_btn.hide()
        tl.addWidget(self.stop_btn)
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("Primary")
        self.scan_btn.clicked.connect(self.start_scan)
        tl.addWidget(self.scan_btn)
        self.settings_btn = QToolButton()
        self.settings_btn.setObjectName("Flat")
        self.settings_btn.setToolTip("Settings (Ctrl+,)")
        self.settings_btn.clicked.connect(self.open_settings)
        tl.addWidget(self.settings_btn)
        root.addWidget(top)

        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(6, 2, 6, 4)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        bl.addWidget(self.splitter)
        root.addWidget(body, 1)

        # Sidebar
        side = QFrame()
        side.setObjectName("Sidebar")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(6, 8, 6, 6)
        self.categories = CategoryPanel(t)
        self.categories.selection_changed.connect(self._on_categories)
        sl.addWidget(self.categories, 1)
        self.matches = MatchPanel(t)
        self.matches.selection_changed.connect(self._on_match)
        self.matches.setFixedHeight(0)
        sl.addWidget(self.matches)
        side.setMinimumWidth(250)
        self.splitter.addWidget(side)

        # Centre: library
        center = QFrame()
        center.setObjectName("Panel")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(12, 10, 12, 8)
        cl.setSpacing(8)
        head = QHBoxLayout()
        self.title = QLabel("Library")
        self.title.setObjectName("PanelTitle")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Mono")
        head.addWidget(self.title)
        head.addSpacing(6)
        head.addWidget(self.subtitle)
        head.addStretch(1)
        cl.addLayout(head)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search files")
        self.search.setToolTip("Matches names, folders, apps, cameras and reasons")
        self.search.setMinimumWidth(200)
        self.search.setClearButtonEnabled(True)
        self._search_action = self.search.addAction(icons.icon("search", t.text_muted), QLineEdit.LeadingPosition)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(160)
        self._search_timer.timeout.connect(lambda: self.proxy.set_text(self.search.text()))
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        bar.addWidget(self.search, 1)
        self.sort_seg = Segmented([("date", "Date"), ("name", "Name"), ("size", "Size")], self.settings.sort_key)
        self.sort_seg.changed.connect(self._on_sort)
        bar.addWidget(self.sort_seg)
        self.size_seg = Segmented([("S", "S"), ("M", "M"), ("L", "L")], self.settings.grid_size)
        self.size_seg.changed.connect(self._on_grid_size)
        bar.addWidget(self.size_seg)
        self.view_seg = Segmented([("grid", "Grid"), ("list", "List")], self.settings.view_mode)
        self.view_seg.changed.connect(self._on_view)
        bar.addWidget(self.view_seg)
        self.export_btn = QToolButton()
        self.export_btn.setObjectName("Flat")
        self.export_btn.setToolTip("Export the shown files as CSV (Ctrl+E)")
        self.export_btn.clicked.connect(self.export_csv)
        bar.addWidget(self.export_btn)
        cl.addLayout(bar)

        self.band = StorageBand(t)
        self.band.category_clicked.connect(self.categories.select_category)
        cl.addWidget(self.band)

        self.model = FileTableModel(t, self)
        self.proxy = FileFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.stack = QStackedWidget()
        self.empty = self._build_empty_state()
        self.grid = FileGrid(self.thumbs, t)
        self.grid.setModel(self.proxy)
        self.table = FileTable()
        self.table.setModel(self.proxy)
        self.table.setSelectionModel(self.grid.selectionModel())
        self.grid.selectionModel().selectionChanged.connect(self._on_selection)
        self.grid.doubleClicked.connect(self._open_index)
        self.table.doubleClicked.connect(self._open_index)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._on_header_sort)
        for w in (self.empty, self.grid, self.table):
            self.stack.addWidget(w)
        cl.addWidget(self.stack, 1)

        foot = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setObjectName("Caption")
        hint = QLabel("Double-click opens a file · Ctrl+F search")
        hint.setObjectName("Caption")
        foot.addWidget(self.count_label)
        foot.addStretch(1)
        foot.addWidget(hint)
        cl.addLayout(foot)
        self.splitter.addWidget(center)

        # Details
        self.details = DetailsPanel(t)
        self.details.open_requested.connect(self.open_file)
        self.details.reveal_requested.connect(self.reveal_file)
        self.details.setMinimumWidth(270)
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([285, 760, 320])
        self.setCentralWidget(central)

        # Status bar
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.status_label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.hide()
        self.totals_label = QLabel("")
        self.totals_label.setObjectName("Mono")
        sb.addWidget(self.status_label)
        sb.addWidget(self.progress)
        sb.addPermanentWidget(self.totals_label)
        self._set_library_visible(False)

    def _build_empty_state(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.addStretch(1)
        box = QVBoxLayout()
        box.setSpacing(8)
        title = QLabel("No phone scanned")
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        box.addWidget(title)
        self.empty_body = QLabel()
        self.empty_body.setObjectName("EmptyBody")
        self.empty_body.setAlignment(Qt.AlignCenter)
        self.empty_body.setWordWrap(True)
        self.empty_body.setMaximumWidth(520)
        box.addWidget(self.empty_body, 0, Qt.AlignHCenter)
        self.empty_note = QLabel()
        self.empty_note.setObjectName("Warning")
        self.empty_note.setAlignment(Qt.AlignCenter)
        self.empty_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.empty_note, 0, Qt.AlignHCenter)
        row = QHBoxLayout()
        row.addStretch(1)
        folder = QPushButton("Choose folder…")
        folder.clicked.connect(self.choose_folder)
        self.empty_scan = QPushButton("Scan")
        self.empty_scan.setObjectName("Primary")
        self.empty_scan.clicked.connect(self.start_scan)
        row.addWidget(folder)
        row.addWidget(self.empty_scan)
        row.addStretch(1)
        box.addSpacing(6)
        box.addLayout(row)
        outer.addLayout(box)
        outer.addStretch(2)
        self._update_empty_text()
        return w

    def _update_empty_text(self) -> None:
        self.empty_body.setText(
            "Connect your phone with a USB cable, pick it at the top right and press Scan.\n\n"
            "USB debugging (ADB) is fastest: on the phone open Settings → About phone, tap Build number "
            "7 times, then turn on Developer options → USB debugging.\n"
            "Or set the phone's USB mode to File transfer to scan it as a mounted folder."
        )
        self.empty_note.setText("" if self.adb_path else "ADB isn't installed. Install it with: sudo apt install adb")
        self.empty_note.setVisible(not self.adb_path)

    def _build_menus(self) -> None:
        mb = self.menubar
        file_menu = mb.addMenu("File")
        self.act_scan = file_menu.addAction("Scan", self.start_scan)
        self.act_scan.setShortcut(QKeySequence("F5"))
        self.act_stop = file_menu.addAction("Stop scan", self.stop_scan)
        self.act_stop.setShortcut(QKeySequence("Esc"))
        self.act_stop.setEnabled(False)
        refresh = file_menu.addAction("Refresh devices", self.refresh_devices)
        refresh.setShortcut(QKeySequence("Ctrl+R"))
        folder = file_menu.addAction("Choose folder…", self.choose_folder)
        folder.setShortcut(QKeySequence("Ctrl+O"))
        file_menu.addSeparator()
        export = file_menu.addAction("Export shown files as CSV…", self.export_csv)
        export.setShortcut(QKeySequence("Ctrl+E"))
        file_menu.addSeparator()
        prefs = file_menu.addAction("Settings…", self.open_settings)
        prefs.setShortcut(QKeySequence("Ctrl+,"))
        quit_ = file_menu.addAction("Quit", self.close)
        quit_.setShortcut(QKeySequence("Ctrl+Q"))

        view = mb.addMenu("View")
        self.act_grid = view.addAction("Grid", lambda: self._on_view("grid"))
        self.act_grid.setShortcut(QKeySequence("Ctrl+1"))
        self.act_list = view.addAction("List", lambda: self._on_view("list"))
        self.act_list.setShortcut(QKeySequence("Ctrl+2"))
        view.addSeparator()
        self.act_details = view.addAction("Details panel", self._toggle_details)
        self.act_details.setCheckable(True)
        self.act_details.setShortcut(QKeySequence("Ctrl+I"))
        find = view.addAction("Search", lambda: (self.search.setFocus(), self.search.selectAll()))
        find.setShortcut(QKeySequence.Find)
        self.theme_menu = view.addMenu("Theme")
        self.theme_menu.aboutToShow.connect(self._fill_theme_menu)

        help_menu = mb.addMenu("Help")
        help_menu.addAction("Connecting your phone", self._show_connect_help)
        help_menu.addAction(f"About {APP_NAME}", self._show_about)
        for act in (self.act_scan, self.act_stop, refresh, folder, export, prefs, quit_, self.act_grid,
                    self.act_list, self.act_details, find):
            self.addAction(act)

    # ------------------------------------------------------------- settings
    def apply_settings(self, s: Settings, initial: bool = False) -> None:
        old = self.settings
        self.settings = s
        if not initial:
            s.save()
        self.theme = t = resolve_theme(s.theme, s.accent_override)
        apply_theme(QApplication.instance(), t, s.font_scale, s.density)
        self.setWindowIcon(app_icon(t))
        mono = mono_font(s.font_scale)
        self.model.mono = mono
        self.categories.mono = mono
        self.matches.mono = mono
        for widget in (self.model, self.categories, self.matches, self.grid, self.band, self.details, self.mark,
                       self.device):
            widget.set_theme(t)
        self.sort_seg.set_value(s.sort_key)
        self.size_seg.set_value(s.grid_size)
        self.view_seg.set_value(s.view_mode)
        self.band.set_scale(s.font_scale)
        self.mark.set_mark_size(round(20 * s.font_scale))
        self.table.apply_row_height(round((26 if s.density == "comfortable" else 22) * s.font_scale))
        if initial:
            self.table.default_widths(s.font_scale)
        self.grid.set_cell(s.grid_size, s.font_scale)
        self.details.setVisible(s.show_details)
        self.act_details.setChecked(s.show_details)
        self.settings_btn.setIcon(icons.icon("settings", t.text))
        self.export_btn.setIcon(icons.icon("export", t.text))
        self._search_action.setIcon(icons.icon("search", t.text_muted))
        self.view_seg.set_icons({"grid": icons.icon("grid", t.text_muted), "list": icons.icon("list", t.text_muted)})
        if not initial and (old.adb_path != s.adb_path):
            self.adb_path = find_adb(s.adb_path)
            self._update_empty_text()
            self.refresh_devices()
        if not initial and old.own_cameras != s.own_cameras and self.result is not None:
            self.result.context.user_cameras = {c for c in s.own_cameras if c}
            classify_all(self.result.files, self.result.context)
            self._show_result(self.result, keep_selection=True)

    def open_settings(self) -> None:
        detected = sorted(self.result.context.learned_cameras | self.result.context.device_cameras) if self.result else []
        dlg = SettingsDialog(self.settings, detected, self)
        dlg.changed.connect(self.apply_settings)
        dlg.exec()

    def _fill_theme_menu(self) -> None:
        self.theme_menu.clear()
        group = QActionGroup(self.theme_menu)
        for key, theme in all_themes().items():
            act = QAction(theme.name, self.theme_menu)
            act.setCheckable(True)
            act.setChecked(key == self.settings.theme)
            act.triggered.connect(lambda _c=False, k=key: self._set_theme(k))
            group.addAction(act)
            self.theme_menu.addAction(act)

    def _set_theme(self, key: str) -> None:
        s = self.settings.copy()
        s.theme = key
        self.apply_settings(s)

    def _toggle_details(self) -> None:
        s = self.settings.copy()
        s.show_details = not s.show_details
        self.apply_settings(s)

    # -------------------------------------------------------------- devices
    def refresh_devices(self) -> None:
        self.device.set_searching()
        run_task(discover_sources, self.settings.adb_path, list(self.settings.recent_folders),
                 on_done=self._on_devices, on_fail=lambda _e: self._on_devices(([], self.adb_path)))

    def _on_devices(self, result) -> None:
        devices, adb = result
        self.adb_path = adb
        self._update_empty_text()
        self.device.set_devices(devices, self.settings.last_source)
        self._update_scan_enabled()

    def _on_device_selected(self, desc: SourceDescriptor) -> None:
        if desc.ready and self.settings.last_source != desc.key:
            self.settings.last_source = desc.key
            self.settings.save()
        self._update_scan_enabled()

    def choose_folder(self) -> None:
        start = self.settings.recent_folders[0] if self.settings.recent_folders else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose the phone's storage folder", start)
        if not folder:
            return
        self.settings.remember_folder(folder)
        self.settings.save()
        desc = SourceDescriptor("folder", folder, f"{Path(folder).name or folder} (folder)")
        self.device.add_and_select(desc)

    def _update_scan_enabled(self) -> None:
        d = self.device.current
        ok = d is not None and d.ready and self.scan_thread is None
        self.scan_btn.setEnabled(ok)
        self.empty_scan.setEnabled(ok)
        self.act_scan.setEnabled(ok)

    # ----------------------------------------------------------------- scan
    def start_scan(self) -> None:
        desc = self.device.current
        if desc is None or not desc.ready or self.scan_thread is not None:
            return
        try:
            source = open_source(desc, self.settings.adb_path)
        except SourceError as exc:
            self._status(str(exc))
            return
        self.scan_thread = ScanThread(source, self.settings, self)
        self.scan_thread.progress.connect(self._on_progress)
        self.scan_thread.succeeded.connect(lambda r, src=source: self._on_scan_done(src, r))
        self.scan_thread.failed.connect(self._on_scan_failed)
        self.scan_thread.finished.connect(self._on_thread_finished)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.stop_btn.show()
        self.act_stop.setEnabled(True)
        self._status(f"Connecting to {desc.label}")
        self._update_scan_enabled()
        self.scan_thread.start()

    def stop_scan(self) -> None:
        if self.scan_thread is not None:
            self.scan_thread.cancel()
            self._status("Stopping…")

    def _on_progress(self, phase: str, done: int, total: int) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self._status(f"{PHASE_LABELS.get(phase, phase)} · {done:,} / {total:,}")
        else:
            self.progress.setRange(0, 0)
            self._status(f"{PHASE_LABELS.get(phase, phase)}" + (f" · {done:,}" if done else ""))

    def _on_scan_done(self, source, result: ScanResult) -> None:
        self.source = source
        self.result = result
        self.thumbs.set_source(source)
        self.details.set_source(source)
        self._show_result(result)
        self._status(f"Scanned {result.source_label} in {result.duration:.1f} s · "
                     f"{result.probed:,} files read for metadata · {result.skipped:,} skipped")

    def _on_scan_failed(self, message: str) -> None:
        self._status(message)
        if message != "Scan stopped":
            QMessageBox.warning(self, "Scan failed", message)

    def _on_thread_finished(self) -> None:
        self.scan_thread = None
        self.progress.hide()
        self.stop_btn.hide()
        self.act_stop.setEnabled(False)
        self._update_scan_enabled()

    def _show_result(self, result: ScanResult, keep_selection: bool = False) -> None:
        self.model.set_files(result.files)
        self.categories.populate(result.files, keep_selection=keep_selection)
        self.matches.populate(result.files)
        self.band.set_files(result.files)
        self._apply_sort(self.settings.sort_key)
        self.title.setText(result.source_label)
        total = human_size(result.total_size)
        self.subtitle.setText(f"scanned {datetime.now():%H:%M}")
        self.totals_label.setText(f"{len(result.files):,} files · {total}")
        self._set_library_visible(True)
        self._update_count()
        self.details.clear()

    def _set_library_visible(self, visible: bool) -> None:
        for w in (self.sort_seg, self.size_seg, self.view_seg, self.export_btn, self.search, self.band):
            w.setVisible(visible)
        if visible:
            self.stack.setCurrentWidget(self.grid if self.settings.view_mode == "grid" else self.table)
            self.size_seg.setVisible(self.settings.view_mode == "grid")
        else:
            self.stack.setCurrentWidget(self.empty)

    # ------------------------------------------------------------ filtering
    def _on_categories(self, cats) -> None:
        self.proxy.set_categories(cats)
        self.band.set_highlight(cats)
        self._update_count()

    def _on_match(self, conf) -> None:
        self.proxy.set_confidence(conf)
        self._update_count()

    def _on_sort(self, key: str) -> None:
        self._apply_sort(key)
        s = self.settings.copy()
        s.sort_key = key
        self.settings = s
        s.save()

    def _apply_sort(self, key: str) -> None:
        col, order = SORT_COLUMNS[key]
        header = self.table.horizontalHeader()
        header.blockSignals(True)
        header.setSortIndicator(col, order)
        header.blockSignals(False)
        self.proxy.sort(col, order)

    def _on_header_sort(self, col: int, order) -> None:
        self.proxy.sort(col, order)
        for key, (c, _o) in SORT_COLUMNS.items():
            if c == col:
                self.sort_seg.set_value(key)

    def _on_grid_size(self, key: str) -> None:
        s = self.settings.copy()
        s.grid_size = key
        self.apply_settings(s)

    def _on_view(self, mode: str) -> None:
        self.view_seg.set_value(mode)
        s = self.settings.copy()
        s.view_mode = mode
        self.settings = s
        s.save()
        if self.result is not None:
            self.stack.setCurrentWidget(self.grid if mode == "grid" else self.table)
        self.size_seg.setVisible(mode == "grid" and self.result is not None)

    def _update_count(self) -> None:
        shown = self.proxy.rowCount()
        size = sum(f.size for f in self.proxy.visible_files()) if shown else 0
        self.count_label.setText(f"{shown:,} files shown · {human_size(size)}")

    # ----------------------------------------------------------- selection
    def _selected_files(self) -> list[MediaFile]:
        rows = self.grid.selectionModel().selectedRows(0) or self.grid.selectionModel().selectedIndexes()
        seen, files = set(), []
        for idx in rows:
            f = idx.data(FILE_ROLE)
            if f is not None and id(f) not in seen:
                seen.add(id(f))
                files.append(f)
        return files

    def _on_selection(self, *_):
        self.details.show_selection(self._selected_files())

    def _open_index(self, index) -> None:
        f = index.data(FILE_ROLE)
        if f is not None:
            self.open_file(f)

    def open_file(self, f: MediaFile) -> None:
        if self.source is None:
            return
        self._status(f"Opening {f.name}…")
        run_task(local_copy, self.source, f,
                 on_done=lambda path: (QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))), self._status("Ready")),
                 on_fail=lambda err: self._status(f"Could not open {f.name}: {err}"))

    def reveal_file(self, f: MediaFile) -> None:
        if self.source is None:
            return
        path = self.source.local_path(f.rel_path)
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    # --------------------------------------------------------------- export
    def export_csv(self) -> None:
        if self.result is None:
            return
        default = str(Path.home() / f"phone-vault-{self.result.source_label.split(' (')[0].replace(' ', '-')}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export shown files", default, "CSV files (*.csv)")
        if not path:
            return
        files = self.proxy.visible_files()
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["path", "name", "category", "origin", "match", "reason", "date", "date_source",
                        "size_bytes", "camera", "width", "height"])
            for f in files:
                w.writerow([f.rel_path, f.name, f.category_label, f.origin, f.confidence.value, f.reason,
                            f.taken_at.isoformat(sep=" ") if f.taken_at else "", f.date_source, f.size,
                            f.camera, f.width or "", f.height or ""])
        self._status(f"Exported {len(files):,} files to {path}")

    # ---------------------------------------------------------------- misc
    def _status(self, text: str) -> None:
        self.status_label.setText(text)

    def _show_connect_help(self) -> None:
        QMessageBox.information(
            self, "Connecting your phone",
            "ADB (recommended)\n"
            "1. On the phone: Settings → About phone → tap Build number 7 times.\n"
            "2. Settings → System → Developer options → turn on USB debugging.\n"
            "3. Connect the cable and accept the prompt on the phone.\n"
            "4. On this computer: sudo apt install adb\n\n"
            "File transfer (MTP)\n"
            "Set the phone's USB mode to File transfer. The phone appears in the device list once "
            "Zorin has mounted it.\n\n"
            "Any folder\n"
            "Use File → Choose folder… for a copy of the phone's storage or an MTP mount.",
        )

    def _show_about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}", f"{APP_NAME} {__version__}\nBack up and sort the files on your phone.")

    def _restore_window(self) -> None:
        if self.settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.settings.window_geometry.encode()))
        if self.settings.splitter_state:
            self.splitter.restoreState(QByteArray.fromBase64(self.settings.splitter_state.encode()))

    def closeEvent(self, e):
        if self.scan_thread is not None:
            self.scan_thread.cancel()
            self.scan_thread.wait(3000)
        self.thumbs.shutdown()
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
        self.settings.splitter_state = bytes(self.splitter.saveState().toBase64()).decode()
        self.settings.save()
        super().closeEvent(e)
