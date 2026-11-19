"""Background work: the scan thread and small one-off tasks."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThread, QThreadPool, Signal
from PySide6.QtGui import QImage, QImageReader

from ..core.backup import BackupCancelled, BackupOptions, run_backup
from ..core.metadata import ImageProbe, probe_with_reader
from ..core.models import Kind, MediaFile
from ..core.scanner import ScanCancelled, run_scan
from ..core.settings import Settings, cache_dir
from ..core.sources.base import Source, SourceError

PREVIEW_FETCH_LIMIT = 60 * 1024 * 1024


class ScanThread(QThread):
    progress = Signal(str, int, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, source: Source, settings: Settings, parent=None):
        super().__init__(parent)
        self.source = source
        self.settings = settings.copy()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            result = run_scan(self.source, self.settings, self.progress.emit, self._cancel.is_set)
        except ScanCancelled:
            self.failed.emit("Scan stopped")
        except SourceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - surfaced in the UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.succeeded.emit(result)


class BackupThread(QThread):
    progress = Signal(int, int, int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, source: Source, files: list[MediaFile], opts: BackupOptions, parent=None):
        super().__init__(parent)
        self.source, self.files, self.opts = source, files, opts
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            result = run_backup(self.source, self.files, self.opts, self.progress.emit, self._cancel.is_set)
        except BackupCancelled:
            self.failed.emit("Backup stopped")
        except Exception as exc:  # pragma: no cover - surfaced in the UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.succeeded.emit(result)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn, args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn(*self.args)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)


_live: set[_Task] = set()


def run_task(fn, *args, on_done=None, on_fail=None) -> None:
    task = _Task(fn, args)
    task.setAutoDelete(False)
    _live.add(task)

    def finish(*_):
        _live.discard(task)

    if on_done:
        task.signals.done.connect(on_done)
    if on_fail:
        task.signals.failed.connect(on_fail)
    task.signals.done.connect(finish)
    task.signals.failed.connect(finish)
    QThreadPool.globalInstance().start(task)


def local_copy(source: Source, f: MediaFile) -> Path:
    """A path on this computer for ``f``: direct for folders, cached copy for ADB."""
    direct = source.local_path(f.rel_path)
    if direct is not None:
        return direct
    digest = hashlib.sha1(f"{source.label}:{f.rel_path}:{f.size}:{f.mtime}".encode()).hexdigest()[:20]
    dest = cache_dir() / "files" / f"{digest}.{f.ext or 'bin'}"
    if not dest.exists():
        source.fetch(f.rel_path, dest)
    return dest


def load_preview(source: Source, f: MediaFile, box: QSize) -> tuple[MediaFile, QImage | None, ImageProbe | None]:
    probe = None
    if f.kind == Kind.IMAGE and not f.probed:
        try:
            probe = probe_with_reader(source.read_head, f.rel_path)
        except Exception:
            probe = None
    if f.kind != Kind.IMAGE or f.size > PREVIEW_FETCH_LIMIT:
        return f, None, probe
    path = local_copy(source, f)
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    edge = max(box.width(), box.height())
    if size.isValid() and max(size.width(), size.height()) > edge:
        # Fit the longest side so EXIF rotation can't push it out of the box.
        reader.setScaledSize(size.scaled(QSize(edge, edge), Qt.KeepAspectRatio))
    image = reader.read()
    return f, (image if not image.isNull() else None), probe

