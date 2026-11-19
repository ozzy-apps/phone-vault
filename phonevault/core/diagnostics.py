"""Connection check: works out why a phone isn't showing up and what to do about it.

Looks at three layers, bottom up:
1. USB, read from /sys: is a phone attached at all, and does it offer an ADB or MTP interface?
2. adb: is it installed, which version, and what does ``adb devices`` say?
3. gvfs: is the phone mounted for File transfer?
"""

from __future__ import annotations

import grp
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .sources.adb import _run, adb_candidates, adb_version, find_adb, parse_adb_devices
from .sources.base import SourceError
from .sources.discovery import SourceDescriptor, discover_mounts

# USB vendor IDs of common Android phone makers.
ANDROID_VENDORS = {
    "18d1": "Google", "04e8": "Samsung", "2717": "Xiaomi", "22b8": "Motorola", "12d1": "Huawei",
    "2a70": "OnePlus", "0bb4": "HTC", "1004": "LG", "0fce": "Sony", "05c6": "Qualcomm", "2d95": "vivo",
    "22d9": "OPPO", "0e8d": "MediaTek", "19d2": "ZTE", "1949": "Amazon", "2ae5": "Fairphone", "17ef": "Lenovo",
    "0b05": "Asus", "1ebf": "Coolpad", "2916": "Yota", "29a9": "Nothing", "3651": "Nothing", "2b4c": "Realme",
    "1bbb": "TCL/Alcatel", "0489": "Foxconn/Nokia", "2e04": "HMD/Nokia", "109b": "Hisense", "1d45": "Teclast",
}

ADB_INTERFACE = ("ff", "42", "01")
MTP_INTERFACES = {("06", "01", "01")}


@dataclass
class UsbDevice:
    path: str
    vendor_id: str
    product_id: str
    manufacturer: str
    product: str
    serial: str
    has_adb: bool
    has_mtp: bool

    @property
    def name(self) -> str:
        maker = self.manufacturer or ANDROID_VENDORS.get(self.vendor_id, "")
        return " ".join(x for x in (maker, self.product) if x) or f"{self.vendor_id}:{self.product_id}"


@dataclass
class Finding:
    level: str  # ok | info | warn | error
    title: str
    detail: str = ""
    commands: list[str] = field(default_factory=list)


@dataclass
class ConnectionReport:
    adb_path: str | None
    adb_version: str
    adb_all: list[tuple[str, str]]
    adb_output: str
    adb_error: str
    devices: list[dict]
    usb: list[UsbDevice]
    mounts: list[SourceDescriptor]
    in_plugdev: bool
    udev_rules: bool
    findings: list[Finding]

    def as_text(self) -> str:
        lines = ["Phone Vault connection check", ""]
        lines.append(f"adb: {self.adb_path or 'not found'} {self.adb_version}".rstrip())
        for path, ver in self.adb_all:
            lines.append(f"  found adb: {path} {ver}".rstrip())
        lines.append(f"user in plugdev: {'yes' if self.in_plugdev else 'no'} · android udev rules: "
                     f"{'yes' if self.udev_rules else 'no'}")
        lines.append("")
        lines.append("USB phones:")
        for d in self.usb or []:
            lines.append(f"  {d.name} [{d.vendor_id}:{d.product_id}] adb={'yes' if d.has_adb else 'no'} "
                         f"mtp={'yes' if d.has_mtp else 'no'}")
        if not self.usb:
            lines.append("  none")
        lines.append("")
        lines.append("adb devices -l:")
        lines.extend("  " + l for l in (self.adb_output.strip() or "(no output)").splitlines())
        if self.adb_error.strip():
            lines.extend("  ! " + l for l in self.adb_error.strip().splitlines())
        lines.append("")
        lines.append("File transfer mounts:")
        lines.extend(f"  {m.label}" for m in self.mounts) if self.mounts else lines.append("  none")
        lines.append("")
        lines.append("Findings:")
        for f in self.findings:
            lines.append(f"  [{f.level}] {f.title}")
            if f.detail:
                lines.append(f"      {f.detail}")
            for c in f.commands:
                lines.append(f"      $ {c}")
        return "\n".join(lines)


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def scan_usb(sys_root: Path = Path("/sys/bus/usb/devices")) -> list[UsbDevice]:
    """USB devices that look like phones: a known Android vendor, or an ADB/MTP interface."""
    phones: list[UsbDevice] = []
    try:
        entries = sorted(sys_root.iterdir())
    except OSError:
        return phones
    for dev in entries:
        if ":" in dev.name or not (dev / "idVendor").exists():
            continue
        if _read(dev / "bDeviceClass").lower() == "09":  # hub
            continue
        vid, pid = _read(dev / "idVendor").lower(), _read(dev / "idProduct").lower()
        has_adb = has_mtp = False
        classes: set[str] = set()
        for iface in entries:
            if not iface.name.startswith(dev.name + ":"):
                continue
            triple = tuple(_read(iface / k).lower() for k in ("bInterfaceClass", "bInterfaceSubClass",
                                                               "bInterfaceProtocol"))
            classes.add(triple[0])
            if triple == ADB_INTERFACE:
                has_adb = True
            if triple in MTP_INTERFACES or "mtp" in _read(iface / "interface").lower():
                has_mtp = True
        # A known phone maker alone isn't enough: Asus, Lenovo or Foxconn also make hubs, keyboards and
        # Bluetooth adapters. Require a phone-like interface and no keyboard/Bluetooth ones.
        phone_like = bool(classes & {"06", "08", "ff"}) and not classes & {"03", "e0"}
        if has_adb or has_mtp or (vid in ANDROID_VENDORS and phone_like):
            phones.append(UsbDevice(dev.name, vid, pid, _read(dev / "manufacturer"), _read(dev / "product"),
                                    _read(dev / "serial"), has_adb, has_mtp))
    return phones


def _in_plugdev() -> bool:
    try:
        gid = grp.getgrnam("plugdev").gr_gid
    except KeyError:
        return True  # no such group on this system; access is handled by uaccess
    return gid in os.getgroups()


def _has_udev_rules() -> bool:
    for folder in ("/etc/udev/rules.d", "/lib/udev/rules.d", "/usr/lib/udev/rules.d"):
        try:
            for p in Path(folder).iterdir():
                if "android" in p.name.lower() or "adb" in p.name.lower():
                    return True
        except OSError:
            continue
    return False


def check_connection(adb_setting: str = "", sys_root: Path | None = None,
                     gvfs_root: Path | None = None) -> ConnectionReport:
    adb = find_adb(adb_setting)
    version = adb_version(adb) if adb else ""
    all_adb = [(p, adb_version(p)) for p in adb_candidates()]
    out = err = ""
    if adb:
        try:
            _code, out, err = _run([adb, "devices", "-l"], timeout=20)
        except SourceError as exc:
            err = str(exc)
    devices = parse_adb_devices(out)
    usb = scan_usb(sys_root) if sys_root else scan_usb()
    mounts = discover_mounts(gvfs_root)
    report = ConnectionReport(adb, version, all_adb, out, err, devices, usb, mounts, _in_plugdev(),
                              _has_udev_rules(), [])
    report.findings = diagnose(report)
    return report


def diagnose(r: ConnectionReport) -> list[Finding]:
    f: list[Finding] = []
    phones = [d for d in r.devices if not d["emulator"]]
    ready = [d for d in phones if d["state"] == "device"]

    for d in ready:
        f.append(Finding("ok", f"{d['model'] or d['serial']} is ready over ADB", "Press Scan."))
    for m in r.mounts:
        if m.ready:
            f.append(Finding("ok" if not ready else "info", f"Mounted for File transfer: {m.label}",
                             "Scanning works through this mount too, but ADB is much faster."))

    if not r.adb_path:
        f.append(Finding("error", "ADB isn't installed",
                         "Phone Vault needs adb to talk to a phone with USB debugging on.",
                         ["sudo apt install adb"]))

    versions = {v for _p, v in r.adb_all if v}
    if len(versions) > 1:
        f.append(Finding(
            "warn", "Two different adb versions are installed",
            "If Android Studio and the system both run adb, they keep restarting each other's server and "
            "the phone drops out. Phone Vault uses the Android SDK copy. Close Android Studio or set the "
            "same adb under Settings → Scanning.",
        ))
    if "doesn't match this client" in r.adb_error:
        f.append(Finding("warn", "adb server version clash", "Another program started a different adb version.",
                         [f"{r.adb_path} kill-server"]))

    usb_names = {u.serial: u.name for u in r.usb if u.serial}
    for d in phones:
        name = d["model"] or usb_names.get(d["serial"]) or d["serial"]
        if d["state"] in ("unauthorized", "authorizing"):
            f.append(Finding(
                "warn", f"{name}: allow USB debugging on the phone",
                "Unlock the phone and tap Allow on the \"Allow USB debugging?\" prompt (tick Always allow). "
                "No prompt? Developer options → Revoke USB debugging authorizations, unplug and plug back in.",
            ))
        elif d["state"] == "no permissions":
            f.append(Finding(
                "error", f"{name}: no permission to use the USB device",
                "Install the Android udev rules, make sure you're in the plugdev group, then log out and back "
                "in and reconnect the phone.",
                ["sudo apt install android-sdk-platform-tools-common", "sudo usermod -aG plugdev $USER"],
            ))
        elif d["state"] == "offline":
            f.append(Finding("warn", f"{name}: offline", "Unplug and reconnect the cable, then Restart ADB."))
        elif d["state"] in ("recovery", "sideload", "bootloader", "rescue"):
            f.append(Finding("warn", f"{name} is in {d['state']} mode", "Restart the phone normally."))

    adb_serials = {d["serial"] for d in r.devices}
    for u in r.usb:
        if u.serial and u.serial in adb_serials:
            continue
        if u.has_adb and r.adb_path and not phones:
            commands = []
            if not r.udev_rules:
                commands.append("sudo apt install android-sdk-platform-tools-common")
            f.append(Finding(
                "error", f"{u.name} offers USB debugging, but adb can't reach it",
                "Usually a USB permission problem. Install the udev rules, then Restart ADB and reconnect "
                "the phone.",
                commands,
            ))
        elif not u.has_adb:
            f.append(Finding(
                "warn", f"{u.name} is connected, but USB debugging isn't active on this connection",
                "Pull down the notification shade, tap the USB notification and choose File transfer. Then "
                "turn USB debugging off and on again in Developer options. On Xiaomi phones also enable "
                "\"USB debugging (Security settings)\".",
            ))

    if not r.usb and not phones and not any(m.ready for m in r.mounts):
        f.append(Finding(
            "error", "No phone detected on USB",
            "Use a data cable (many cables only charge), try another USB port directly on the computer, "
            "and unlock the phone.",
        ))

    emulators = [d for d in r.devices if d["emulator"]]
    if emulators and not ready:
        f.append(Finding("info", "Only an Android emulator is connected",
                         "That's Android Studio's virtual device, not your phone."))
    if not f:
        f.append(Finding("info", "Nothing to report"))
    order = {"error": 0, "warn": 1, "ok": 2, "info": 3}
    f.sort(key=lambda x: order[x.level])
    return f
