"""Finds phones: ADB devices and MTP/PTP mounts created by GNOME (gvfs)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .adb import AdbSource, find_adb, list_adb_devices
from .base import Source, SourceError
from .folder import FolderSource

_STATE_NOTES = {
    "unauthorized": "Unlock the phone and allow USB debugging",
    "authorizing": "Waiting for you to allow USB debugging on the phone",
    "connecting": "Connecting…",
    "offline": "Offline: reconnect the cable",
    "no permissions": "No USB permission: open Help → Connection check",
    "recovery": "Phone is in recovery mode",
    "sideload": "Phone is in sideload mode",
    "bootloader": "Phone is in bootloader mode",
    "rescue": "Phone is in rescue mode",
}


@dataclass
class SourceDescriptor:
    kind: str  # "adb" | "mtp" | "folder"
    ident: str  # serial or path
    label: str
    ready: bool = True
    note: str = ""
    emulator: bool = False

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.ident}"


def _mtp_label(mount_name: str) -> str:
    m = re.search(r"host=([^,]+)", mount_name)
    host = m.group(1) if m else mount_name
    parts = host.split("_")
    if len(parts) > 1 and re.fullmatch(r"[0-9A-Fa-f]{8,}|[0-9A-Za-z]{10,}", parts[-1]):
        parts = parts[:-1]
    return " ".join(parts) or "Phone"


def discover_mounts(gvfs_root: Path | None = None) -> list[SourceDescriptor]:
    root = gvfs_root or Path(f"/run/user/{os.getuid()}/gvfs")
    found: list[SourceDescriptor] = []
    try:
        mounts = sorted(p for p in root.iterdir() if p.name.startswith(("mtp:", "gphoto2:")))
    except OSError:
        return found
    for mount in mounts:
        device = _mtp_label(mount.name)
        kind = "PTP" if mount.name.startswith("gphoto2:") else "MTP"
        try:
            storages = sorted(p for p in mount.iterdir() if p.is_dir())
        except OSError:
            storages = []
        if not storages:
            found.append(SourceDescriptor("mtp", str(mount), f"{device} ({kind})", False,
                                          "Unlock the phone and choose File transfer"))
        for storage in storages:
            found.append(SourceDescriptor("mtp", str(storage), f"{device} — {storage.name} ({kind})"))
    return found


def discover_sources(adb_path: str = "", extra_folders: list[str] | None = None) -> tuple[list[SourceDescriptor], str | None]:
    """Returns (descriptors, adb_executable_or_None)."""
    found: list[SourceDescriptor] = []
    adb = find_adb(adb_path)
    if adb:
        try:
            devices = list_adb_devices(adb)
            # Real phones first; an Android Studio emulator is never the default pick.
            devices.sort(key=lambda d: d["emulator"])
            for dev in devices:
                ready = dev["state"] == "device"
                name = dev["model"] or dev["serial"]
                via = "Emulator" if dev["emulator"] else ("ADB · Wi-Fi" if dev["transport"] == "wifi" else "ADB · USB")
                found.append(
                    SourceDescriptor("adb", dev["serial"], f"{name} ({via})", ready,
                                     "" if ready else _STATE_NOTES.get(dev["state"], dev["state"]),
                                     dev["emulator"])
                )
        except SourceError:
            pass
    found.extend(discover_mounts())
    for folder in extra_folders or []:
        if Path(folder).is_dir():
            found.append(SourceDescriptor("folder", folder, f"{Path(folder).name or folder} (folder)"))
    return found, adb


def open_source(desc: SourceDescriptor, adb_path: str = "") -> Source:
    if desc.kind == "adb":
        adb = find_adb(adb_path)
        if not adb:
            raise SourceError("adb not found")
        return AdbSource(desc.ident, adb, desc.label)
    return FolderSource(desc.ident, desc.label)
