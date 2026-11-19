import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from phonevault.core.backup import (
    Archive, BackupOptions, archive_path, default_device_folder, plan_backup, run_backup, safe_component,
)
from phonevault.core.models import Category, MediaFile, RemoteEntry
from phonevault.core.scanner import run_scan
from phonevault.core.settings import Settings
from phonevault.core.sources import AdbSource, FolderSource
from phonevault.core.sources.base import DeviceInfo

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def phone(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("phone")
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_sample_phone.py"), str(target)], check=True,
                   capture_output=True)
    return target


def scan(phone_dir: Path):
    return run_scan(FolderSource(phone_dir, "Pixel 8"), Settings())


def test_archive_paths():
    f = MediaFile.from_entry(RemoteEntry("DCIM/Camera/PXL_20261118_101010123.jpg", 10, 0))
    f.category = Category.CAMERA_PHOTO
    f.taken_at = datetime(2026, 11, 18, 10, 10, 10)
    assert archive_path(f, "category") == "Yours/Camera photos/2026/11/PXL_20261118_101010123.jpg"
    assert archive_path(f, "date") == "2026/11/Camera photos/PXL_20261118_101010123.jpg"
    assert archive_path(f, "phone") == "DCIM/Camera/PXL_20261118_101010123.jpg"
    w = MediaFile.from_entry(RemoteEntry("x/IMG-1.jpg", 1, 0))
    w.category, w.origin, w.taken_at = Category.CHAT_IMAGE, "WhatsApp · sent", datetime(2026, 1, 2)
    assert archive_path(w, "category") == "Chats/Chat images/WhatsApp sent/2026/01/IMG-1.jpg"


def test_device_folder_names():
    assert default_device_folder("x", DeviceInfo("Google", "Pixel 8")) == "Google Pixel 8"
    assert default_device_folder("x", DeviceInfo("samsung", "SM-S918B")) == "Samsung SM-S918B"
    assert default_device_folder("Google Pixel 8 — Internal shared storage (MTP)") == "Google Pixel 8"
    assert default_device_folder("Pixel 8 (ADB · USB)") == "Pixel 8"
    assert safe_component("..") == "_" and safe_component("a/b") == "a_b"


def test_full_then_incremental_backup(phone, tmp_path):
    result = scan(phone)
    opts = BackupOptions(tmp_path / "vault", "Pixel 8")
    archive = Archive(opts.root, opts.device_folder)
    assert archive.mark(result.files) == 0
    plan = plan_backup(result.files, opts)
    assert len(plan.to_copy) == len(result.files) and plan.fits
    done = run_backup(FolderSource(phone), plan.to_copy, opts)
    assert done.copied == len(result.files) and not done.failed and not done.cancelled
    assert (archive.base / "Yours" / "Camera photos").is_dir()
    assert not archive.staging.exists()
    sample = next(f for f in result.files if f.category == Category.CAMERA_PHOTO)
    copy = Path(sample.backup_dest)
    assert copy.read_bytes() == (phone / sample.rel_path).read_bytes()
    assert abs(copy.stat().st_mtime - sample.mtime) < 1

    # A fresh scan sees everything as backed up.
    again = scan(phone)
    assert archive.mark(again.files) == len(again.files)
    assert plan_backup(again.files, opts).to_copy == []

    # A copy deleted from the archive is offered again.
    copy.unlink()
    third = scan(phone)
    archive.mark(third.files)
    assert [f.rel_path for f in plan_backup(third.files, opts).to_copy] == [sample.rel_path]


def test_lost_index_reuses_existing_copies(phone, tmp_path):
    result = scan(phone)
    opts = BackupOptions(tmp_path / "vault", "Pixel 8")
    run_backup(FolderSource(phone), result.files, opts)
    Archive(opts.root, opts.device_folder).db_path.unlink()
    fresh = scan(phone)
    second = run_backup(FolderSource(phone), fresh.files, opts)
    assert second.reused == len(fresh.files) and second.copied == 0


def test_name_collision_keeps_both(tmp_path):
    src = tmp_path / "phone"
    for folder, content in (("Download/a", b"first"), ("Download/b", b"second!")):
        (src / folder).mkdir(parents=True)
        (src / folder / "IMG.jpg").write_bytes(content)
        os.utime(src / folder / "IMG.jpg", (1763460000, 1763460000))
    result = scan(src)
    opts = BackupOptions(tmp_path / "vault", "P")
    done = run_backup(FolderSource(src), result.files, opts)
    assert done.copied == 2
    names = sorted(Path(f.backup_dest).name for f in result.files)
    assert names == ["IMG-1.jpg", "IMG.jpg"]


def test_skip_options(phone, tmp_path):
    result = scan(phone)
    opts = BackupOptions(tmp_path / "v", "P", skip_categories={Category.STICKER}, skip_sent=True)
    plan = plan_backup(result.files, opts)
    assert all(f.category != Category.STICKER and not f.sent for f in plan.to_copy)
    assert len(plan.skipped) == 12 + 10


def test_cancel_leaves_clean_archive(phone, tmp_path):
    result = scan(phone)
    opts = BackupOptions(tmp_path / "vault", "Pixel 8")
    calls = {"n": 0}

    def cancel_after_some():
        calls["n"] += 1
        return calls["n"] > 5

    done = run_backup(FolderSource(phone), result.files, opts, cancelled=cancel_after_some)
    assert done.cancelled and 0 < done.copied < len(result.files)
    archive = Archive(opts.root, opts.device_folder)
    assert not archive.staging.exists()
    assert len(archive.rows()) == done.copied


def test_checksum_mode(phone, tmp_path):
    result = scan(phone)
    files = [f for f in result.files if f.category == Category.SCREENSHOT][:5]
    done = run_backup(FolderSource(phone), files, BackupOptions(tmp_path / "v", "P", verify="checksum"))
    assert done.copied == 5 and not done.failed
    rows = sqlite3.connect(Archive(tmp_path / "v", "P").db_path).execute("SELECT verified FROM files").fetchall()
    assert {r[0] for r in rows} == {"checksum"}


FAKE_ADB = r"""#!/usr/bin/env bash
ROOT="@ROOT@"
if [ "$1" = "devices" ]; then printf 'List of devices attached\nSER1\tdevice usb:1-2 product:shiba model:Pixel_8 transport_id:3\n'; exit 0; fi
[ "$1" = "-s" ] && shift 2
cmd="$1"; shift
case "$cmd" in
  shell)
    script="${*//\/storage\/emulated\/0/$ROOT}"
    if [[ "$script" == getprop* ]]; then printf 'Google\nPixel 8\nPhysical size: 1080x2400\n'; exit 0; fi
    sh -c "$script" | sed "s|$ROOT|/storage/emulated/0|g" ;;
  exec-out) script="${*//\/storage\/emulated\/0/$ROOT}"; sh -c "$script" ;;
  pull)
    [ "$1" = "-a" ] && shift
    args=("$@"); dest="${args[-1]}"; unset 'args[-1]'
    echo "pull ${#args[@]}" >> "@LOG@"
    for src in "${args[@]}"; do cp -p "${src//\/storage\/emulated\/0/$ROOT}" "$dest"; done ;;
esac
"""


def test_backup_over_adb_uses_batches_and_checksums(phone, tmp_path):
    if not shutil.which("sha256sum"):
        pytest.skip("sha256sum not available")
    adb = tmp_path / "adb"
    log = tmp_path / "pulls.log"
    adb.write_text(FAKE_ADB.replace("@ROOT@", str(phone)).replace("@LOG@", str(log)))
    adb.chmod(0o755)
    source = AdbSource("SER1", str(adb), "Pixel 8")
    result = run_scan(source, Settings())
    opts = BackupOptions(tmp_path / "vault", default_device_folder("", result.device), verify="checksum")
    done = run_backup(source, result.files, opts)
    assert done.copied == len(result.files), done.failed[:3]
    pulls = log.read_text().split()
    assert pulls.count("pull") < len(result.files) / 4  # batched, not one adb call per file
    assert (Path(opts.root) / "Google Pixel 8" / "Yours").is_dir()
