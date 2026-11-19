#!/usr/bin/env python3
"""Render README screenshots headlessly against a generated sample phone.

Usage: QT_QPA_PLATFORM=offscreen python3 tools/capture_screenshots.py docs/screenshots
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="pv-shots-"))
os.environ["XDG_CONFIG_HOME"] = str(TMP / "config")
os.environ["XDG_CACHE_HOME"] = str(TMP / "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from phonevault.core.models import Category  # noqa: E402
from phonevault.core.scanner import run_scan  # noqa: E402
from phonevault.core.settings import Settings  # noqa: E402
from phonevault.core.sources import FolderSource, SourceDescriptor  # noqa: E402


def pump(seconds: float = 0.3) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "screenshots")
    out.mkdir(parents=True, exist_ok=True)
    phone = TMP / "Pixel 8"
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_sample_phone.py"), str(phone)], check=True,
                   capture_output=True)

    app = QApplication(sys.argv)
    app.setApplicationName("Phone Vault")
    from phonevault.ui.main_window import MainWindow
    from phonevault.ui.settings_dialog import SettingsDialog

    settings = Settings()
    win = MainWindow(settings)
    win.resize(1480, 900)
    win.show()
    pump(1.0)
    win.grab().save(str(out / "empty-state.png"))

    desc = SourceDescriptor("adb", "38XYZ12345", "Pixel 8 (ADB · USB)")
    win.device.add_and_select(desc)
    source = FolderSource(phone, "Pixel 8")
    result = run_scan(source, win.settings)
    result.source_label = "Pixel 8"
    win._on_scan_done(source, result)
    pump(0.5)

    def wait_thumbs():
        for _ in range(40):
            win.grid.viewport().update()
            pump(0.15)

    def select_row(pred):
        for r in range(win.proxy.rowCount()):
            idx = win.proxy.index(r, 0)
            f = win.proxy.data(idx, 258)  # FILE_ROLE
            if pred(f):
                win.grid.selectionModel().select(idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
                win.grid.scrollTo(idx)
                return

    # 1. Grid, all files, a camera photo selected
    wait_thumbs()
    select_row(lambda f: f.category == Category.CAMERA_PHOTO)
    wait_thumbs()
    pump(1.0)
    win.grab().save(str(out / "library-grid.png"))

    # 2. Received photos in the list view
    win._on_view("list")
    win.categories.select_category(Category.RECEIVED_PHOTO)
    pump(0.3)
    select_row(lambda f: "iPhone" in f.reason)
    pump(1.2)
    win.grab().save(str(out / "received-list.png"))

    # 3. Screenshots, grid size L
    win._on_view("grid")
    win._on_grid_size("L")
    win.categories.select_category(Category.SCREENSHOT)
    pump(0.3)
    select_row(lambda f: f.folder == "Download")
    wait_thumbs()
    pump(1.0)
    win.grab().save(str(out / "screenshots-grid.png"))

    # 4. Light theme
    s = win.settings.copy()
    s.theme = "light"
    s.grid_size = "M"
    win.apply_settings(s)
    win.categories.select_category(None)
    pump(0.3)
    select_row(lambda f: f.category == Category.CAMERA_PHOTO)
    wait_thumbs()
    pump(0.8)
    win.grab().save(str(out / "theme-light.png"))

    # 5. Settings dialog (back to the default theme)
    s = win.settings.copy()
    s.theme = "inca"
    win.apply_settings(s)
    dlg = SettingsDialog(win.settings, sorted(result.context.learned_cameras), win)
    dlg.resize(620, 560)
    dlg.show()
    pump(0.6)
    dlg.grab().save(str(out / "settings.png"))
    dlg.close()

    print("Screenshots written to", out)
    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
