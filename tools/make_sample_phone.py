#!/usr/bin/env python3
"""Generate a fake Android storage tree for demos, tests and screenshots.

Usage: python3 tools/make_sample_phone.py /tmp/sample-phone
"""

from __future__ import annotations

import math
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SCREEN = (1080, 2400)
RNG = random.Random(7)

SKIES = [
    ((28, 44, 92), (233, 150, 92)),
    ((18, 30, 60), (120, 160, 220)),
    ((70, 40, 70), (240, 180, 120)),
    ((40, 70, 130), (200, 220, 240)),
    ((90, 50, 40), (250, 200, 140)),
    ((20, 24, 40), (90, 110, 170)),
]
GROUND = [(60, 44, 40), (48, 40, 52), (70, 52, 38), (36, 36, 48)]


def landscape(w: int, h: int, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    top, bottom = rnd.choice(SKIES)
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        px.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    if rnd.random() < 0.7:
        r = rnd.randint(h // 14, h // 8)
        cx, cy = rnd.randint(r, w - r), rnd.randint(h // 6, h // 2)
        px.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(250, 220, 170))
    for layer in range(3):
        base = h * (0.55 + 0.12 * layer)
        amp = h * (0.18 - 0.04 * layer)
        g = GROUND[(seed + layer) % len(GROUND)]
        shade = tuple(min(255, int(c * (1.4 - 0.25 * layer))) for c in g)
        pts = [(0, h)]
        phase = rnd.random() * 6
        for x in range(0, w + 20, 20):
            y = base - amp * abs(math.sin(x / w * (2.5 + layer) + phase)) - rnd.random() * amp * 0.15
            pts.append((x, y))
        pts.append((w, h))
        px.polygon(pts, fill=shade)
    return img.filter(ImageFilter.GaussianBlur(1.2))


def card(w: int, h: int, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    bg = rnd.choice([(196, 98, 63), (74, 144, 226), (217, 164, 65), (155, 107, 201), (60, 60, 70)])
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    for _ in range(6):
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        r = rnd.randint(w // 12, w // 4)
        c = tuple(min(255, v + rnd.randint(20, 70)) for v in bg)
        d.ellipse([x - r, y - r, x + r, y + r], fill=c)
    d.rectangle([w * 0.1, h * 0.75, w * 0.9, h * 0.85], fill=(250, 245, 235))
    return img


def screenshot(seed: int) -> Image.Image:
    rnd = random.Random(seed)
    w, h = SCREEN
    dark = rnd.random() < 0.5
    bg = (24, 25, 28) if dark else (246, 244, 240)
    fg = (52, 54, 60) if dark else (222, 218, 210)
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 90], fill=(14, 15, 18) if dark else (230, 228, 222))
    d.rectangle([0, 90, w, 260], fill=rnd.choice([(74, 144, 226), (196, 98, 63), (155, 107, 201)]))
    y = 320
    while y < h - 200:
        hh = rnd.randint(110, 300)
        d.rounded_rectangle([48, y, w - 48, y + hh], 28, fill=fg)
        y += hh + 36
    return img


def save_jpeg(img: Image.Image, path: Path, when: datetime, make: str = "", model: str = "",
              software: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    if make or model:
        exif[271] = make
        exif[272] = model
        exif[306] = when.strftime("%Y:%m:%d %H:%M:%S")
        exif.get_ifd(0x8769)[36867] = when.strftime("%Y:%m:%d %H:%M:%S")
    if software:
        exif[305] = software
    img.save(path, "JPEG", quality=82, exif=exif.tobytes() if len(exif) else b"")
    touch(path, when)


def save_png(img: Image.Image, path: Path, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    touch(path, when)


def blob(path: Path, when: datetime, size: int, header: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(os.urandom(max(0, size - len(header))))
    touch(path, when)


def touch(path: Path, when: datetime) -> None:
    ts = when.timestamp()
    os.utime(path, (ts, ts))


MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def build(root: Path) -> None:
    start = datetime(2026, 8, 2, 9, 30)
    wa = root / "Android/media/com.whatsapp/WhatsApp/Media"

    # Own camera: Google Pixel 8
    for i in range(46):
        when = start + timedelta(days=i * 2.3, hours=RNG.randint(0, 9), minutes=RNG.randint(0, 59))
        name = f"PXL_{when:%Y%m%d_%H%M%S}{RNG.randint(100, 999)}.jpg"
        save_jpeg(landscape(1600, 1200, i), root / "DCIM/Camera" / name, when, "Google", "Pixel 8")
    for i in range(9):
        when = start + timedelta(days=i * 9 + 1, hours=5)
        blob(root / "DCIM/Camera" / f"PXL_{when:%Y%m%d_%H%M%S}412.mp4", when, RNG.randint(4, 30) * 1_000_000, MP4)

    # Edited in Snapseed
    for i in range(3):
        when = start + timedelta(days=20 + i * 11)
        save_jpeg(landscape(1600, 1200, 100 + i), root / f"Pictures/Snapseed/IMG_{when:%Y%m%d_%H%M%S}.jpg", when,
                  "Google", "Pixel 8", "Snapseed 2.21")

    # Screenshots (Pixel naming)
    for i in range(18):
        when = start + timedelta(days=i * 5.1, hours=14, minutes=i)
        save_png(screenshot(i), root / "Pictures/Screenshots" / f"Screenshot_{when:%Y%m%d-%H%M%S}.png", when)
    # Screen recordings
    for i in range(2):
        when = start + timedelta(days=30 + i * 20)
        blob(root / "Movies/Screen recordings" / f"Screen_Recording_{when:%Y%m%d_%H%M%S}.mp4", when,
             12_000_000, MP4)

    # WhatsApp received images (EXIF stripped, compressed)
    for i in range(34):
        when = start + timedelta(days=i * 2.7, hours=19)
        img = landscape(1280, 960, 300 + i) if i % 3 else card(1080, 1080, 300 + i)
        save_jpeg(img, wa / "WhatsApp Images" / f"IMG-{when:%Y%m%d}-WA{i:04d}.jpg", when)
    # WhatsApp sent copies
    for i in range(10):
        when = start + timedelta(days=i * 6, hours=20)
        save_jpeg(landscape(1280, 960, i * 4), wa / "WhatsApp Images/Sent" / f"IMG-{when:%Y%m%d}-WA{100 + i:04d}.jpg",
                  when)
    # A photo someone sent as a document — keeps their iPhone EXIF
    for i, when in enumerate([datetime(2026, 9, 14, 16, 2), datetime(2026, 10, 3, 11, 40)]):
        save_jpeg(landscape(1600, 1200, 500 + i), wa / "WhatsApp Documents" / f"IMG_{4410 + i}.JPG", when,
                  "Apple", "iPhone 15 Pro")
    blob(wa / "WhatsApp Documents" / "Huurcontract 2026.pdf", datetime(2026, 9, 1, 10), 380_000, PDF)
    for i in range(7):
        when = start + timedelta(days=i * 11, hours=12)
        blob(wa / "WhatsApp Video" / f"VID-{when:%Y%m%d}-WA{i:04d}.mp4", when, RNG.randint(2, 18) * 1_000_000, MP4)
    for i in range(14):
        when = start + timedelta(days=i * 5, hours=8)
        week = f"{when:%Y}{int(when.strftime('%W')):02d}"
        blob(wa / "WhatsApp Voice Notes" / week / f"PTT-{when:%Y%m%d}-WA{i:04d}.opus", when,
             RNG.randint(20, 400) * 1000)
    (wa / "WhatsApp Stickers").mkdir(parents=True, exist_ok=True)
    for i in range(12):
        when = start + timedelta(days=i * 7)
        sticker = wa / "WhatsApp Stickers" / f"STK-{when:%Y%m%d}-WA{i:04d}.webp"
        card(512, 512, 700 + i).save(sticker, "WEBP")
        touch(sticker, when)
    # Hidden statuses (skipped by default)
    save_jpeg(card(720, 1280, 900), wa / ".Statuses" / "a1b2c3.jpg", datetime(2026, 11, 2))

    # Telegram
    for i in range(6):
        when = start + timedelta(days=i * 13)
        save_jpeg(card(1280, 1280, 800 + i), root / "Pictures/Telegram" / f"IMG_{when:%Y%m%d_%H%M%S}_{i}.jpg", when)

    # Downloads
    save_jpeg(card(1200, 1200, 1001), root / "Download/meme-of-the-day.jpg", datetime(2026, 9, 3, 22))
    save_jpeg(landscape(1440, 3200, 1002), root / "Download/wallpaper-andes.jpg", datetime(2026, 8, 21, 9))
    save_jpeg(landscape(2000, 1333, 1003), root / "Download/DSC_0192.jpg", datetime(2026, 10, 9, 15),
              "Canon", "Canon EOS R6")
    save_png(screenshot(1004), root / "Download/image.png", datetime(2026, 10, 22, 13))
    blob(root / "Download/Boarding pass AMS-LIM.pdf", datetime(2026, 10, 1, 7), 210_000, PDF)
    blob(root / "Download/Invoice-0917.pdf", datetime(2026, 9, 17, 9), 95_000, PDF)
    blob(root / "Download/some-app-v2.4.apk", datetime(2026, 8, 30, 18), 48_000_000, b"PK\x03\x04")
    save_jpeg(landscape(1600, 1200, 1005), root / "Download/Quick Share/IMG_20261012_174401.jpg",
              datetime(2026, 10, 12, 17, 44), "samsung", "SM-S918B")
    save_jpeg(card(1080, 1350, 1006), root / "Pictures/Instagram/IMG_20261101_120000.jpg", datetime(2026, 11, 1, 12))

    # Audio and documents
    for i in range(4):
        when = start + timedelta(days=i * 17)
        blob(root / "Recordings/Voice Recorder" / f"Recording {i + 1}.m4a", when, RNG.randint(1, 9) * 1_000_000)
    for name in ("Andes Sunrise.mp3", "Quena Session.mp3"):
        blob(root / "Music" / name, datetime(2026, 8, 5), 7_400_000)
    blob(root / "Documents/Notes Peru trip.pdf", datetime(2026, 9, 9), 140_000, PDF)

    # Excluded or hidden by default
    blob(root / "Android/data/com.example/cache/blob.bin", datetime(2026, 11, 1), 1000)
    blob(root / "DCIM/.thumbnails/1234.jpg", datetime(2026, 11, 1), 1000)
    blob(root / "DCIM/Camera/.trashed-1765000000-PXL_20261020_101010123.jpg", datetime(2026, 10, 20), 1000)


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/sample-phone")
    target.mkdir(parents=True, exist_ok=True)
    build(target)
    count = sum(1 for _ in target.rglob("*") if _.is_file())
    print(f"Sample phone written to {target} ({count} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
