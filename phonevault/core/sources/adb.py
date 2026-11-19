"""Phone storage over ADB (USB debugging). Faster and more reliable than MTP."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from ..models import RemoteEntry
from .base import CancelFn, DeviceInfo, ProgressFn, Source, SourceError

STORAGE_ROOT = "/storage/emulated/0"


def find_adb(configured: str = "") -> str | None:
    if configured:
        p = Path(configured).expanduser()
        return str(p) if p.is_file() else None
    found = shutil.which("adb")
    if found:
        return found
    for candidate in ("~/Android/Sdk/platform-tools/adb", "/usr/lib/android-sdk/platform-tools/adb"):
        p = Path(candidate).expanduser()
        if p.is_file():
            return str(p)
    return None


def _run(args: list[str], timeout: float = 20, binary: bool = False):
    try:
        proc = subprocess.run(args, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise SourceError("adb not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise SourceError("adb timed out") from exc
    if binary:
        return proc.returncode, proc.stdout, proc.stderr.decode("utf-8", "replace")
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", "surrogateescape"),
        proc.stderr.decode("utf-8", "replace"),
    )


def list_adb_devices(adb: str) -> list[dict]:
    """Parse ``adb devices -l``. Each dict: serial, state, model, product, transport."""
    code, out, err = _run([adb, "devices", "-l"], timeout=15)
    devices = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        m = re.match(r"(\S+)\s+(device|unauthorized|offline|no permissions|recovery|sideload|bootloader)\b(.*)", line)
        if not m:
            continue
        serial, state, rest = m.groups()
        props = dict(re.findall(r"(\w+):(\S+)", rest))
        devices.append(
            {
                "serial": serial,
                "state": state,
                "model": props.get("model", "").replace("_", " "),
                "product": props.get("product", ""),
                "transport": "wifi" if ":" in serial else "usb",
            }
        )
    return devices


class AdbSource(Source):
    kind = "adb"
    parallelism = 4

    def __init__(self, serial: str, adb: str, label: str | None = None, root: str = STORAGE_ROOT):
        self.serial = serial
        self.adb = adb
        self.root = root.rstrip("/")
        self._label = label or serial

    @property
    def label(self) -> str:
        return self._label

    def _cmd(self, *args: str) -> list[str]:
        return [self.adb, "-s", self.serial, *args]

    def _remote(self, rel_path: str) -> str:
        return f"{self.root}/{rel_path}"

    def device_info(self) -> DeviceInfo:
        script = "getprop ro.product.manufacturer; getprop ro.product.model; wm size"
        code, out, _ = _run(self._cmd("shell", script), timeout=15)
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        info = DeviceInfo()
        if lines:
            info.manufacturer = lines[0] if not lines[0].lower().startswith(("physical", "override")) else ""
        if len(lines) > 1:
            info.model = lines[1] if not lines[1].lower().startswith(("physical", "override")) else ""
        for l in lines:
            m = re.search(r"(?:physical|override) size:\s*(\d+)x(\d+)", l, re.IGNORECASE)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                if (w, h) not in info.screen_sizes:
                    info.screen_sizes.append((w, h))
        return info

    def list_files(self, progress: ProgressFn | None = None, cancelled: CancelFn | None = None) -> Iterator[RemoteEntry]:
        r = self.root
        script = (
            f"find {shlex.quote(r)} \\( -path {shlex.quote(r + '/Android/data')} "
            f"-o -path {shlex.quote(r + '/Android/obb')} -o -name .thumbnails \\) -prune "
            f"-o -type f -exec stat -c '%s|%Y|%n' {{}} + 2>/dev/null"
        )
        try:
            proc = subprocess.Popen(self._cmd("shell", script), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as exc:
            raise SourceError("adb not found") from exc
        prefix = r + "/"
        count = 0
        assert proc.stdout is not None
        try:
            for raw in proc.stdout:
                if cancelled and cancelled():
                    proc.kill()
                    return
                line = raw.decode("utf-8", "surrogateescape").rstrip("\r\n")
                parts = line.split("|", 2)
                if len(parts) != 3 or not parts[2].startswith(prefix):
                    continue
                try:
                    size, mtime = int(parts[0]), float(parts[1])
                except ValueError:
                    continue
                count += 1
                if progress and count % 200 == 0:
                    progress(count)
                yield RemoteEntry(parts[2][len(prefix):], size, mtime)
        finally:
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if proc.returncode not in (0, 1) and count == 0:
            err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
            raise SourceError(err.strip() or "Listing files over adb failed")
        if progress:
            progress(count)

    def read_head(self, rel_path: str, nbytes: int) -> bytes:
        remote = shlex.quote(self._remote(rel_path))
        code, out, _ = _run(self._cmd("exec-out", f"head -c {int(nbytes)} {remote}"), timeout=30, binary=True)
        return out if code == 0 else b""

    def fetch(self, rel_path: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        code, _out, err = _run(self._cmd("pull", "-a", self._remote(rel_path), str(dest)), timeout=600)
        if code != 0 or not dest.exists():
            raise SourceError(err.strip() or f"Could not copy {rel_path}")
        return dest
