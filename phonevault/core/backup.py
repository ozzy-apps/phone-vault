"""Backups: copy phone files into a sorted archive on this computer.

Archive on disk::

    <root>/<device folder>/
        Yours/Camera photos/2026/11/PXL_20261118_101010123.jpg      (layout "category")
        Chats/Chat images/WhatsApp/2026/11/IMG-20261118-WA0001.jpg
        .phonevault/index.sqlite                                     what was copied, from where, verified how

Every file is copied to ``.phonevault/staging`` first, checked, then moved into place,
so a cancelled or failed run never leaves half-written files in the archive. Runs are
incremental: a phone file whose path and size are already in the index, and whose copy
still exists, is skipped.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import CATEGORY_INFO, Category, MediaFile
from .sources.base import DeviceInfo, Source

LAYOUTS = {
    "category": "By category",
    "date": "By date",
    "phone": "Same folders as the phone",
}
VERIFY_MODES = {
    "size": "Size check",
    "checksum": "Checksum on the phone (slower)",
}
BATCH_MAX_FILES = 64
BATCH_MAX_BYTES = 96 * 1024 * 1024
BATCH_FILE_LIMIT = 16 * 1024 * 1024  # bigger files are pulled one at a time
COMMIT_EVERY = 40

# done_files, total_files, done_bytes, total_bytes, current file name
BackupProgress = Callable[[int, int, int, int, str], None]


class BackupCancelled(Exception):
    pass


def safe_component(name: str) -> str:
    name = name.replace("/", "_").replace("\x00", "").strip()
    if name in ("", ".", ".."):
        return "_"
    return name[:200]


def default_device_folder(label: str, device: DeviceInfo | None = None) -> str:
    """'Google Pixel 8' from device info, or the source label without '(ADB · USB)' / '— storage' parts."""
    if device is not None and device.model:
        make = device.manufacturer.strip()
        if make.islower():
            make = make.capitalize()
        model = device.model.strip()
        name = model if not make or model.lower().startswith(make.lower()) else f"{make} {model}"
        return safe_component(name)
    name = re.sub(r"\s*\([^)]*\)\s*$", "", label)
    name = name.split(" — ")[0]
    return safe_component(name or "Phone")


def archive_path(f: MediaFile, layout: str) -> str:
    """Path of ``f`` inside the device folder, POSIX style."""
    name = safe_component(f.name)
    if layout == "phone":
        return "/".join(safe_component(p) for p in f.rel_path.split("/"))
    info = CATEGORY_INFO[f.category]
    when = f.taken_at or datetime.fromtimestamp(f.mtime or 0)
    year, month = f"{when:%Y}", f"{when:%m}"
    if layout == "date":
        return f"{year}/{month}/{info.label}/{name}"
    parts = [info.group, info.label]
    if info.group == "Chats" and f.origin:
        parts.append(safe_component(f.origin.replace(" · ", " ")))
    return "/".join([*parts, year, month, name])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    n = 1
    while True:
        candidate = path.with_name(f"{stem}-{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1


@dataclass
class IndexRow:
    rel_path: str
    size: int
    mtime: float
    sha256: str
    dest: str
    category: str
    backed_up_at: str
    verified: str


class Archive:
    """One phone's backup folder and its index."""

    def __init__(self, root: Path, device_folder: str):
        self.root = Path(root)
        self.base = self.root / safe_component(device_folder)
        self.meta = self.base / ".phonevault"
        self.db_path = self.meta / "index.sqlite"
        self.staging = self.meta / "staging"

    def exists(self) -> bool:
        return self.db_path.exists()

    def connect(self) -> sqlite3.Connection:
        self.meta.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS files (rel_path TEXT PRIMARY KEY, size INTEGER, mtime REAL, sha256 TEXT,"
            " dest TEXT, category TEXT, backed_up_at TEXT, verified TEXT)"
        )
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        return conn

    def rows(self) -> dict[str, IndexRow]:
        if not self.exists():
            return {}
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute("SELECT rel_path, size, mtime, sha256, dest, category, backed_up_at, verified FROM files")
            return {r[0]: IndexRow(*r) for r in cur}
        finally:
            conn.close()

    def mark(self, files: list[MediaFile]) -> int:
        """Set ``backup_dest`` on files whose verified copy is in this archive. Returns how many."""
        rows = self.rows()
        count = 0
        for f in files:
            f.backup_dest, f.backed_up_at = "", ""
            row = rows.get(f.rel_path)
            if row is None or row.size != f.size:
                continue
            dest = self.base / row.dest
            try:
                if dest.stat().st_size != f.size:
                    continue
            except OSError:
                continue
            f.backup_dest, f.backed_up_at = str(dest), row.backed_up_at
            count += 1
        return count


@dataclass
class BackupOptions:
    root: Path
    device_folder: str
    layout: str = "category"
    verify: str = "size"
    skip_categories: set[Category] = field(default_factory=set)
    skip_sent: bool = False


@dataclass
class BackupPlan:
    to_copy: list[MediaFile]
    already: list[MediaFile]
    skipped: list[MediaFile]
    free_bytes: int

    @property
    def bytes_to_copy(self) -> int:
        return sum(f.size for f in self.to_copy)

    @property
    def fits(self) -> bool:
        return self.bytes_to_copy < self.free_bytes


def free_space(path: Path) -> int:
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 0


def plan_backup(files: list[MediaFile], opts: BackupOptions) -> BackupPlan:
    to_copy, already, skipped = [], [], []
    for f in files:
        if f.backed_up:
            already.append(f)
        elif f.category in opts.skip_categories or (opts.skip_sent and f.sent):
            skipped.append(f)
        else:
            to_copy.append(f)
    return BackupPlan(to_copy, already, skipped, free_space(opts.root))


@dataclass
class BackupResult:
    base: Path
    copied: int = 0
    copied_bytes: int = 0
    reused: int = 0
    failed: list[tuple[MediaFile, str]] = field(default_factory=list)
    cancelled: bool = False
    duration: float = 0.0


def _batches(files: list[MediaFile], source: Source) -> list[list[MediaFile]]:
    if not source.batches:
        return [[f] for f in files]
    out: list[list[MediaFile]] = []
    batch: list[MediaFile] = []
    names: set[str] = set()
    size = 0
    for f in files:
        if f.size > BATCH_FILE_LIMIT:
            out.append([f])
            continue
        if batch and (len(batch) >= BATCH_MAX_FILES or size + f.size > BATCH_MAX_BYTES or f.name in names):
            out.append(batch)
            batch, names, size = [], set(), 0
        batch.append(f)
        names.add(f.name)
        size += f.size
    if batch:
        out.append(batch)
    return out


def run_backup(source: Source, files: list[MediaFile], opts: BackupOptions,
               progress: BackupProgress | None = None, cancelled: Callable[[], bool] | None = None) -> BackupResult:
    """Copy ``files`` (normally ``plan.to_copy``) into the archive. Safe to cancel at any time."""
    archive = Archive(opts.root, opts.device_folder)
    result = BackupResult(archive.base)
    start = time.monotonic()
    report = progress or (lambda *_: None)
    total = len(files)
    total_bytes = sum(f.size for f in files)
    done = done_bytes = 0
    conn = archive.connect()
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('device_folder', ?)", (opts.device_folder,))
    archive.staging.mkdir(parents=True, exist_ok=True)
    pending_commit = 0
    try:
        for batch in _batches(files, source):
            if cancelled and cancelled():
                result.cancelled = True
                break
            report(done, total, done_bytes, total_bytes, batch[0].name)
            staged = {f.rel_path: archive.staging / f"{i:03d}-{safe_component(f.name)}" for i, f in enumerate(batch)}
            errors = source.fetch_many([(f.rel_path, staged[f.rel_path]) for f in batch])
            remote = source.remote_hashes([f.rel_path for f in batch if f.rel_path not in errors]) \
                if opts.verify == "checksum" else {}
            for f in batch:
                part = staged[f.rel_path]
                try:
                    if f.rel_path in errors:
                        raise OSError(errors[f.rel_path])
                    reused = _finalize(f, part, archive, opts, remote, conn)
                except Exception as exc:
                    result.failed.append((f, str(exc) or type(exc).__name__))
                    part.unlink(missing_ok=True)
                else:
                    if reused:
                        result.reused += 1
                    else:
                        result.copied += 1
                        result.copied_bytes += f.size
                    pending_commit += 1
                done += 1
                done_bytes += f.size
            if pending_commit >= COMMIT_EVERY:
                conn.commit()
                pending_commit = 0
            report(done, total, done_bytes, total_bytes, "")
    finally:
        conn.commit()
        conn.close()
        shutil.rmtree(archive.staging, ignore_errors=True)
    result.duration = time.monotonic() - start
    return result


def _finalize(f: MediaFile, part: Path, archive: Archive, opts: BackupOptions, remote: dict[str, str],
              conn: sqlite3.Connection) -> bool:
    """Verify a staged copy and move it into place. Returns True when an identical file was already there."""
    size = part.stat().st_size
    if size != f.size:
        raise OSError(f"size mismatch: phone {f.size:,} bytes, copy {size:,} bytes")
    digest = sha256_file(part)
    if opts.verify == "checksum":
        expected = remote.get(f.rel_path)
        if not expected:
            raise OSError("couldn't read the checksum on the phone")
        if expected != digest:
            raise OSError("checksum mismatch")
    rel_dest = archive_path(f, opts.layout)
    dest = archive.base / rel_dest
    reused = False
    if dest.exists():
        if dest.stat().st_size == size and sha256_file(dest) == digest:
            reused = True
            part.unlink()
        else:
            dest = _unique(dest)
    if not reused:
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(part, dest)
        if f.mtime:
            os.utime(dest, (f.mtime, f.mtime))
    stamp = datetime.now().isoformat(timespec="seconds")
    rel = posixpath.join(*dest.relative_to(archive.base).parts)
    conn.execute(
        "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f.rel_path, f.size, f.mtime, digest, rel, f.category.value, stamp, opts.verify),
    )
    f.backup_dest, f.backed_up_at = str(dest), stamp
    return reused
