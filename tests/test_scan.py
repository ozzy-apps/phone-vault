import subprocess
import sys
from pathlib import Path

import pytest

from phonevault.core.metadata import probe_image_bytes
from phonevault.core.models import Category
from phonevault.core.scanner import run_scan
from phonevault.core.settings import Settings
from phonevault.core.sources import FolderSource
from phonevault.core.sources.adb import list_adb_devices
from phonevault.core.sources.discovery import _mtp_label

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def sample_phone(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("phone")
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_sample_phone.py"), str(target)], check=True,
                   capture_output=True)
    return target


def test_full_scan_of_sample_phone(sample_phone):
    result = run_scan(FolderSource(sample_phone, "Sample"), Settings())
    by_cat = {}
    for f in result.files:
        by_cat.setdefault(f.category, []).append(f)
    assert len(by_cat[Category.CAMERA_PHOTO]) == 46
    assert len(by_cat[Category.SCREENSHOT]) == 19  # 18 + screen-sized download
    assert len(by_cat[Category.RECEIVED_PHOTO]) == 4
    assert "Google Pixel 8" in result.context.learned_cameras
    assert (1080, 2400) in result.context.screen_sizes
    assert not any("Android/data" in f.rel_path for f in result.files)
    assert not any(".Statuses" in f.rel_path for f in result.files)


def test_metadata_off_skips_probing(sample_phone):
    s = Settings(metadata_mode="off")
    result = run_scan(FolderSource(sample_phone), s)
    assert result.probed == 0


def test_probe_reads_truncated_jpeg(sample_phone):
    photo = next((sample_phone / "DCIM" / "Camera").glob("*.jpg"))
    probe = probe_image_bytes(photo.read_bytes()[:128 * 1024])
    assert probe and probe.model == "Pixel 8" and probe.width == 1600


def test_parse_adb_devices(monkeypatch):
    out = (
        "List of devices attached\n"
        "38XYZ12345\tdevice usb:1-2 product:shiba model:Pixel_8 device:shiba transport_id:3\n"
        "R5CT1234\tunauthorized usb:1-3 transport_id:4\n"
        "192.168.1.20:5555\tdevice product:a54 model:SM_A546B device:a54x transport_id:5\n"
    )

    def fake_run(args, timeout=0, binary=False):
        return 0, out, ""

    monkeypatch.setattr("phonevault.core.sources.adb._run", fake_run)
    devices = list_adb_devices("adb")
    assert [d["state"] for d in devices] == ["device", "unauthorized", "device"]
    assert devices[0]["model"] == "Pixel 8"
    assert devices[2]["transport"] == "wifi"


def test_mtp_label():
    assert _mtp_label("mtp:host=Google_Pixel_8_38XYZ12345") == "Google Pixel 8"
    assert _mtp_label("mtp:host=SAMSUNG_SAMSUNG_Android_R5CT1234ABC") == "SAMSUNG SAMSUNG Android"
