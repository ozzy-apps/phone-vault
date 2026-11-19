"""Lazy thumbnails for the grid view.

Only items that get painted are requested, newest request first, so fast
scrolling never builds a backlog. Over ADB the embedded EXIF thumbnail is used
when the photo has one, which avoids copying the whole file.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict, deque

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageReader

from ..core.models import Kind, MediaFile
from ..core.settings import cache_dir
from ..core.sources.base import Source
from .workers import local_copy

THUMB_EDGE = 320
MAX_PENDING = 160
MAX_MEMORY_ITEMS = 900
FETCH_LIMIT = 30 * 1024 * 1024


def exif_thumbnail(data: bytes) -> bytes | None:
    """Return the JPEG thumbnail embedded in the EXIF APP1 segment, if any."""
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
            seg = data[i + 4:i + 2 + length]
            start = seg.find(b"\xff\xd8", 8)
            if start < 0:
                return None
            end = seg.find(b"\xff\xd9", start)
            return seg[start:end + 2] if end > start else None
        if marker in (0xDA, 0xD9):
            return None
        i += 2 + length
    return None


def _scaled(reader: QImageReader, edge: int) -> QImage:
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > edge:
        reader.setScaledSize(size.scaled(QSize(edge, edge), Qt.KeepAspectRatioByExpanding))
    return reader.read()


class ThumbnailCache(QObject):
    ready = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source: Source | None = None
        self._generation = 0
        self._memory: OrderedDict[str, QImage] = OrderedDict()
        self._failed: set[str] = set()
        self._pending: deque[MediaFile] = deque()
        self._pending_keys: set[str] = set()
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._threads: list[threading.Thread] = []
        self._stop = False

    def set_source(self, source: Source | None) -> None:
        with self._lock:
            self._source = source
            self._generation += 1
            self._memory.clear()
            self._failed.clear()
            self._pending.clear()
            self._pending_keys.clear()
        workers = max(1, min(4, source.parallelism)) if source else 0
        while len(self._threads) < workers:
            t = threading.Thread(target=self._run, daemon=True)
            t.start()
            self._threads.append(t)

    def shutdown(self) -> None:
        with self._lock:
            self._stop = True
            self._wake.notify_all()

    def get(self, f: MediaFile) -> QImage | None:
        if f.kind != Kind.IMAGE:
            return None
        key = f.rel_path
        with self._lock:
            img = self._memory.get(key)
            if img is not None:
                self._memory.move_to_end(key)
                return img
            if key in self._failed or key in self._pending_keys or self._source is None:
                return None
            self._pending.append(f)
            self._pending_keys.add(key)
            while len(self._pending) > MAX_PENDING:
                old = self._pending.popleft()
                self._pending_keys.discard(old.rel_path)
            self._wake.notify()
        return None

    def _run(self) -> None:
        while True:
            with self._lock:
                while not self._pending and not self._stop:
                    self._wake.wait()
                if self._stop:
                    return
                f = self._pending.pop()  # newest first
                source, gen = self._source, self._generation
            try:
                img = self._make(source, f) if source else None
            except Exception:
                img = None
            with self._lock:
                if gen != self._generation:
                    continue
                self._pending_keys.discard(f.rel_path)
                if img is None or img.isNull():
                    self._failed.add(f.rel_path)
                    continue
                self._memory[f.rel_path] = img
                while len(self._memory) > MAX_MEMORY_ITEMS:
                    self._memory.popitem(last=False)
            self.ready.emit(f.rel_path)

    @staticmethod
    def _disk_path(source: Source, f: MediaFile):
        digest = hashlib.sha1(f"{source.label}:{f.rel_path}:{f.size}:{f.mtime}".encode()).hexdigest()
        return cache_dir() / "thumbs" / digest[:2] / f"{digest}.jpg"

    def _make(self, source: Source, f: MediaFile) -> QImage | None:
        disk = self._disk_path(source, f)
        if disk.exists():
            img = QImage(str(disk))
            if not img.isNull():
                return img
        img: QImage | None = None
        direct = source.local_path(f.rel_path)
        if direct is not None:
            img = _scaled(QImageReader(str(direct)), THUMB_EDGE)
        else:
            embedded = exif_thumbnail(source.read_head(f.rel_path, 128 * 1024)) if f.ext in ("jpg", "jpeg") else None
            if embedded:
                candidate = QImage.fromData(embedded)
                if not candidate.isNull() and max(candidate.width(), candidate.height()) >= 120:
                    img = candidate
            if img is None and f.size <= FETCH_LIMIT:
                img = _scaled(QImageReader(str(local_copy(source, f))), THUMB_EDGE)
        if img is None or img.isNull():
            return None
        disk.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(disk), "JPG", 85)
        return img
