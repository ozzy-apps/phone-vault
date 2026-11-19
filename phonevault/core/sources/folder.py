"""A phone storage reachable as a folder: an MTP/PTP mount (gvfs) or any directory."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Iterator

from ..models import RemoteEntry
from .base import CancelFn, ProgressFn, Source, SourceError

_PRUNE_DIRS = {"android/data", "android/obb"}


class FolderSource(Source):
    kind = "folder"
    parallelism = 8

    def __init__(self, root: str | os.PathLike, label: str | None = None):
        self.root = Path(root)
        self._label = label or self.root.name or str(self.root)
        if not self.root.is_dir():
            raise SourceError(f"Folder not found: {self.root}")
        if "gvfs" in self.root.parts or str(self.root).startswith("/run/user/"):
            self.parallelism = 2  # MTP mounts serialise access anyway.

    @property
    def label(self) -> str:
        return self._label

    def list_files(self, progress: ProgressFn | None = None, cancelled: CancelFn | None = None) -> Iterator[RemoteEntry]:
        count = 0
        root = str(self.root)
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            if cancelled and cancelled():
                return
            rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
            rel_dir = "" if rel_dir == "." else rel_dir
            dirnames[:] = [
                d for d in dirnames
                if f"{rel_dir}/{d}".lstrip("/").lower() not in _PRUNE_DIRS and d != ".thumbnails"
            ]
            for name in filenames:
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full, follow_symlinks=False)
                except OSError:
                    continue
                rel = f"{rel_dir}/{name}" if rel_dir else name
                count += 1
                if progress and count % 200 == 0:
                    progress(count)
                yield RemoteEntry(rel, st.st_size, st.st_mtime)
        if progress:
            progress(count)

    def local_path(self, rel_path: str) -> Path:
        return self.root.joinpath(*rel_path.split("/"))

    def read_head(self, rel_path: str, nbytes: int) -> bytes:
        try:
            with open(self.local_path(rel_path), "rb") as fh:
                return fh.read(nbytes)
        except OSError:
            return b""

    def fetch(self, rel_path: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.local_path(rel_path), dest)
        return dest

    def remote_hashes(self, rel_paths: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for rel in rel_paths:
            h = hashlib.sha256()
            try:
                with open(self.local_path(rel), "rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
            except OSError:
                continue
            out[rel] = h.hexdigest()
        return out
