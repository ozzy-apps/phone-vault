"""Phone storage over ADB (USB debugging). Faster and more reliable than MTP."""

from __future__ import annotations

import os
import posixpath
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator

from ..models import RemoteEntry
from .base import CancelFn, DeviceInfo, ProgressFn, Source, SourceError

STORAGE_ROOT = "/storage/emulated/0"


SDK_ADB_CANDIDATES = (
    "~/Android/Sdk/platform-tools/adb",
    "~/Android/sdk/platform-tools/adb",
    "/opt/android-sdk/platform-tools/adb",
    "/usr/lib/android-sdk/platform-tools/adb",
)

ADB_STATES = (
    "device", "unauthorized", "offline", "no permissions", "authorizing", "connecting",
    "recovery", "sideload", "bootloader", "rescue", "host",
)


def adb_candidates() -> list[str]:
    """Every adb on this machine, Android SDK copies first (they are newer than distro packages)."""
    found: list[str] = []
    for candidate in SDK_ADB_CANDIDATES:
        p = Path(candidate).expanduser()
        if p.is_file() and str(p) not in found:
            found.append(str(p))
    on_path = shutil.which("adb")
    if on_path:
        real = str(Path(on_path).resolve())
        if on_path not in found and real not in found:
            found.append(on_path)
    return found


def find_adb(configured: str = "") -> str | None:
    """The adb to use. An Android SDK adb wins over the distro one: running two different adb
    versions makes them kill each other's server, so the phone keeps disappearing."""
    if configured:
        p = Path(configured).expanduser()
        return str(p) if p.is_file() else None
    candidates = adb_candidates()
    return candidates[0] if candidates else None


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


def parse_adb_devices(out: str) -> list[dict]:
    """Parse ``adb devices -l`` output. Each dict: serial, state, model, product, transport, emulator."""
    devices = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("*") or line.lower().startswith("list of devices"):
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        serial, rest = parts
        state = next((st for st in ADB_STATES if rest.startswith(st)), "")
        if not state:
            continue
        props = dict(re.findall(r"(\w+):(\S+)", rest[len(state):]))
        emulator = serial.startswith("emulator-") or props.get("product", "").startswith(("sdk_", "sdk ")) \
            or props.get("model", "").lower().startswith("sdk_gphone")
        devices.append(
            {
                "serial": serial,
                "state": state,
                "model": props.get("model", "").replace("_", " "),
                "product": props.get("product", ""),
                "transport": "wifi" if ":" in serial and not emulator else "usb",
                "emulator": emulator,
            }
        )
    return devices


def list_adb_devices(adb: str) -> list[dict]:
    code, out, err = _run([adb, "devices", "-l"], timeout=15)
    return parse_adb_devices(out)


def adb_version(adb: str) -> str:
    try:
        _code, out, _err = _run([adb, "version"], timeout=10)
    except SourceError:
        return ""
    m = re.search(r"Version ([\w.\-]+)", out) or re.search(r"version ([\d.]+)", out)
    return m.group(1) if m else out.strip().splitlines()[0] if out.strip() else ""


def restart_adb_server(adb: str) -> str:
    """kill-server + start-server; returns combined output."""
    out = []
    for args in ([adb, "kill-server"], [adb, "start-server"]):
        try:
            _c, o, e = _run(args, timeout=20)
            out.append((o + e).strip())
        except SourceError as exc:
            out.append(str(exc))
    return "\n".join(x for x in out if x)


class AdbSource(Source):
    kind = "adb"
    parallelism = 4
    batches = True

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

    def fetch_many(self, items: list[tuple[str, Path]]) -> dict[str, str]:
        """One ``adb pull`` for many files (basenames must be unique within ``items``)."""
        if len(items) <= 1:
            return super().fetch_many(items)
        staging = Path(tempfile.mkdtemp(prefix="pull-", dir=items[0][1].parent))
        errors: dict[str, str] = {}
        try:
            try:
                _run(self._cmd("pull", "-a", *[self._remote(rel) for rel, _ in items], str(staging)), timeout=3600)
            except SourceError:
                pass  # files that did arrive are used; the rest is retried one by one below
            for rel, dest in items:
                got = staging / posixpath.basename(rel)
                if got.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(got, dest)
                    continue
                try:
                    self.fetch(rel, dest)
                except Exception as exc:
                    errors[rel] = str(exc) or type(exc).__name__
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return errors

    def remote_hashes(self, rel_paths: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        prefix = self.root + "/"
        for start in range(0, len(rel_paths), 40):
            chunk = rel_paths[start:start + 40]
            script = "sha256sum " + " ".join(shlex.quote(self._remote(r)) for r in chunk) + " 2>/dev/null"
            try:
                _code, text, _err = _run(self._cmd("shell", script), timeout=1800)
            except SourceError:
                continue
            for line in text.splitlines():
                digest, _sep, path = line.partition("  ")
                if len(digest) == 64 and path.startswith(prefix):
                    out[path[len(prefix):]] = digest.lower()
        return out
