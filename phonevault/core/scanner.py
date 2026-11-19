"""Scan pipeline: list → first-pass sort → read metadata → learn → final sort."""

from __future__ import annotations

import fnmatch
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from .classifier import ClassifyContext, classify_all, learn_from_samples
from .metadata import probe_with_reader
from .models import Category, Confidence, Kind, MediaFile
from .settings import Settings
from .sources.base import DeviceInfo, Source

# phase, done, total (total 0 = unknown)
ScanProgress = Callable[[str, int, int], None]

LEARN_CAMERA_SAMPLES = 24
LEARN_SCREEN_SAMPLES = 12


class ScanCancelled(Exception):
    pass


@dataclass
class ScanResult:
    source_label: str
    files: list[MediaFile]
    context: ClassifyContext
    device: DeviceInfo
    duration: float = 0.0
    probed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)


def is_excluded(rel_path: str, patterns: list[str], include_hidden: bool) -> bool:
    low = rel_path.lower()
    parts = low.split("/")
    if not include_hidden and any(p.startswith(".") for p in parts):
        return True
    for pat in patterns:
        pat = pat.strip().lower().strip("/")
        if not pat:
            continue
        if "/" in pat:
            if low == pat or low.startswith(pat + "/") or fnmatch.fnmatch(low, pat):
                return True
        elif any(fnmatch.fnmatch(part, pat) for part in parts):
            return True
    return False


def _spread(items: list[MediaFile], n: int) -> list[MediaFile]:
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def build_context(settings: Settings, device: DeviceInfo) -> ClassifyContext:
    ctx = ClassifyContext(user_cameras={c.strip() for c in settings.own_cameras if c.strip()},
                          device_cameras=device.cameras)
    for w, h in device.screen_sizes:
        ctx.add_screen_size(w, h)
    return ctx


def select_probe_targets(files: list[MediaFile], mode: str) -> list[MediaFile]:
    if mode == "off":
        return []
    images = [f for f in files if f.kind == Kind.IMAGE]
    if mode == "all":
        return images
    targets = {id(f): f for f in images if f.wants_probe}
    by_date = sorted(images, key=lambda f: f.mtime, reverse=True)
    cams = [f for f in by_date if f.category == Category.CAMERA_PHOTO and f.confidence == Confidence.SURE]
    shots = [f for f in by_date if f.category == Category.SCREENSHOT and f.confidence == Confidence.SURE]
    for f in _spread(cams, LEARN_CAMERA_SAMPLES) + _spread(shots, LEARN_SCREEN_SAMPLES):
        targets[id(f)] = f
    return list(targets.values())


def probe_files(source: Source, targets: list[MediaFile], progress: ScanProgress | None,
                cancelled: Callable[[], bool] | None) -> int:
    done = 0
    total = len(targets)
    if not total:
        return 0

    def work(f: MediaFile):
        if cancelled and cancelled():
            return f, None
        return f, probe_with_reader(source.read_head, f.rel_path)

    last = 0.0
    with ThreadPoolExecutor(max_workers=max(1, source.parallelism)) as pool:
        futures = [pool.submit(work, f) for f in targets]
        for fut in as_completed(futures):
            f, probe = fut.result()
            f.probed = True
            if probe:
                f.width, f.height = probe.width, probe.height
                f.camera_make, f.camera_model = probe.make, probe.model
                f.software, f.exif_taken = probe.software, probe.taken
            done += 1
            now = time.monotonic()
            if progress and (now - last > 0.08 or done == total):
                progress("Reading photo metadata", done, total)
                last = now
            if cancelled and cancelled():
                for other in futures:
                    other.cancel()
                raise ScanCancelled()
    return done


def run_scan(source: Source, settings: Settings, progress: ScanProgress | None = None,
             cancelled: Callable[[], bool] | None = None) -> ScanResult:
    start = time.monotonic()
    report = progress or (lambda *_: None)
    report("Connecting", 0, 0)
    errors: list[str] = []
    try:
        device = source.device_info()
    except Exception as exc:  # device info is optional
        device = DeviceInfo()
        errors.append(f"Device info: {exc}")

    report("Listing files", 0, 0)
    files: list[MediaFile] = []
    skipped = 0
    for entry in source.list_files(lambda n: report("Listing files", n, 0), cancelled):
        if is_excluded(entry.rel_path, settings.exclude_patterns, settings.include_hidden):
            skipped += 1
            continue
        files.append(MediaFile.from_entry(entry))
    if cancelled and cancelled():
        raise ScanCancelled()

    ctx = build_context(settings, device)
    report("Sorting", 0, len(files))
    classify_all(files, ctx)

    targets = select_probe_targets(files, settings.metadata_mode)
    probed = probe_files(source, targets, report, cancelled)

    learn_from_samples(files, ctx)
    report("Sorting", len(files), len(files))
    classify_all(files, ctx)

    return ScanResult(source.label, files, ctx, device, time.monotonic() - start, probed, skipped, errors)
