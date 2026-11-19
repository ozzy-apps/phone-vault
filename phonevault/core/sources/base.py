from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from ..models import RemoteEntry

ProgressFn = Callable[[int], None]
CancelFn = Callable[[], bool]


class SourceError(RuntimeError):
    pass


@dataclass
class DeviceInfo:
    manufacturer: str = ""
    model: str = ""
    screen_sizes: list[tuple[int, int]] = field(default_factory=list)

    @property
    def cameras(self) -> set[str]:
        names = set()
        if self.model:
            names.add(self.model)
            if self.manufacturer and not self.model.lower().startswith(self.manufacturer.lower()):
                names.add(f"{self.manufacturer} {self.model}")
        return names


class Source(ABC):
    """A phone storage that can be listed and read."""

    kind: str = "source"
    #: Number of threads that may read file heads at once.
    parallelism: int = 4

    @property
    @abstractmethod
    def label(self) -> str: ...

    @abstractmethod
    def list_files(self, progress: ProgressFn | None = None, cancelled: CancelFn | None = None) -> Iterator[RemoteEntry]:
        ...

    @abstractmethod
    def read_head(self, rel_path: str, nbytes: int) -> bytes: ...

    @abstractmethod
    def fetch(self, rel_path: str, dest: Path) -> Path:
        """Copy a file to ``dest`` (a file path) and return it."""

    def fetch_many(self, items: list[tuple[str, Path]]) -> dict[str, str]:
        """Copy several files. Returns {rel_path: error} for the ones that failed."""
        errors: dict[str, str] = {}
        for rel_path, dest in items:
            try:
                self.fetch(rel_path, dest)
            except Exception as exc:  # keep going; the caller reports per file
                errors[rel_path] = str(exc) or type(exc).__name__
        return errors

    def remote_hashes(self, rel_paths: list[str]) -> dict[str, str]:
        """SHA-256 of files as stored on the phone. Missing entries mean "couldn't hash"."""
        return {}

    #: True when fetch_many is faster than single fetches (one adb call for many files).
    batches: bool = False

    def local_path(self, rel_path: str) -> Path | None:
        """Direct path on this computer, if the source is a mounted folder."""
        return None

    def device_info(self) -> DeviceInfo:
        return DeviceInfo()
