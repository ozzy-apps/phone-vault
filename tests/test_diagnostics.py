from pathlib import Path

from phonevault.core.diagnostics import ConnectionReport, UsbDevice, diagnose, scan_usb
from phonevault.core.sources.adb import parse_adb_devices

ADB_OUT = """* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached
38XYZ12345             device usb:1-2 product:shiba model:Pixel_8 device:shiba transport_id:3
R5CT1234               unauthorized usb:1-3 transport_id:4
0123ABCD               no permissions (missing udev rules? user is in the plugdev group); see [http://developer.android.com/tools/device.html] usb:1-4 transport_id:5
emulator-5554          device product:sdk_gphone64_x86_64 model:sdk_gphone64_x86_64 device:emu64xa transport_id:6
"""


def test_parse_all_states():
    devs = parse_adb_devices(ADB_OUT)
    assert [(d["serial"], d["state"]) for d in devs] == [
        ("38XYZ12345", "device"), ("R5CT1234", "unauthorized"), ("0123ABCD", "no permissions"),
        ("emulator-5554", "device"),
    ]
    assert devs[0]["model"] == "Pixel 8" and not devs[0]["emulator"]
    assert devs[3]["emulator"]


def report(**kw) -> ConnectionReport:
    base = dict(adb_path="/usr/bin/adb", adb_version="35.0.2", adb_all=[("/usr/bin/adb", "35.0.2")], adb_output="",
                adb_error="", devices=[], usb=[], mounts=[], in_plugdev=True, udev_rules=True, findings=[])
    base.update(kw)
    return ConnectionReport(**base)


def titles(r):
    return [(f.level, f.title) for f in diagnose(r)]


def usb(has_adb=True, serial="38XYZ12345"):
    return UsbDevice("1-2", "18d1", "4ee7", "Google", "Pixel 8", serial, has_adb, True)


def test_ready_phone():
    r = report(devices=parse_adb_devices(ADB_OUT)[:1], usb=[usb()])
    assert titles(r) == [("ok", "Pixel 8 is ready over ADB")]


def test_adb_missing():
    r = report(adb_path=None, adb_version="", adb_all=[])
    levels = titles(r)
    assert ("error", "ADB isn't installed") in levels
    assert ("error", "No phone detected on USB") in levels


def test_unauthorized_and_no_permissions():
    devs = parse_adb_devices(ADB_OUT)[1:3]
    found = diagnose(report(devices=devs))
    assert found[0].level == "error" and "no permission" in found[0].title
    assert "sudo apt install android-sdk-platform-tools-common" in found[0].commands
    assert any("allow USB debugging" in f.title for f in found)


def test_usb_debugging_not_active_on_connection():
    found = titles(report(usb=[usb(has_adb=False)]))
    assert found[0][0] == "warn" and "USB debugging isn't active" in found[0][1]


def test_adb_interface_but_adb_sees_nothing():
    found = titles(report(usb=[usb()], udev_rules=False))
    assert found[0][0] == "error" and "adb can't reach it" in found[0][1]


def test_only_emulator_and_version_clash():
    emu = parse_adb_devices(ADB_OUT)[3:]
    found = titles(report(devices=emu, adb_all=[("/a", "35.0.2"), ("/b", "1.0.41")]))
    assert ("info", "Only an Android emulator is connected") in found
    assert ("warn", "Two different adb versions are installed") in found


def test_scan_usb_reads_sysfs(tmp_path):
    def dev(name, files):
        d = tmp_path / name
        d.mkdir()
        for k, v in files.items():
            (d / k).write_text(v + "\n")

    dev("1-2", {"idVendor": "18d1", "idProduct": "4ee7", "manufacturer": "Google", "product": "Pixel 8",
                "serial": "38XYZ12345", "bDeviceClass": "00"})
    dev("1-2:1.0", {"bInterfaceClass": "06", "bInterfaceSubClass": "01", "bInterfaceProtocol": "01"})
    dev("1-2:1.1", {"bInterfaceClass": "ff", "bInterfaceSubClass": "42", "bInterfaceProtocol": "01"})
    # An Asus keyboard: known vendor, but HID only -> not a phone
    dev("1-5", {"idVendor": "0b05", "idProduct": "1234", "bDeviceClass": "00"})
    dev("1-5:1.0", {"bInterfaceClass": "03", "bInterfaceSubClass": "01", "bInterfaceProtocol": "01"})
    # a hub
    dev("usb1", {"idVendor": "1d6b", "idProduct": "0002", "bDeviceClass": "09"})
    phones = scan_usb(Path(tmp_path))
    assert [(p.name, p.has_adb, p.has_mtp) for p in phones] == [("Google Pixel 8", True, True)]
