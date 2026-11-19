from datetime import datetime

import pytest

from phonevault.core.classifier import ClassifyContext, classify, date_from_name
from phonevault.core.models import Category, Confidence, MediaFile, RemoteEntry
from phonevault.core.scanner import is_excluded


def mf(path: str, **probe) -> MediaFile:
    f = MediaFile.from_entry(RemoteEntry(path, 1000, datetime(2026, 11, 1, 12).timestamp()))
    if probe:
        f.probed = True
        for k, v in probe.items():
            setattr(f, k, v)
    return f


OWN = ClassifyContext(learned_cameras={"Google Pixel 8"}, screen_sizes={(1080, 2400), (2400, 1080)})


@pytest.mark.parametrize(
    "path, category, origin",
    [
        ("DCIM/Camera/PXL_20261101_101010123.jpg", Category.CAMERA_PHOTO, "Camera"),
        ("DCIM/Camera/20261101_101010.mp4", Category.CAMERA_VIDEO, "Camera"),
        ("DCIM/Screenshots/Screenshot_20261101-101010_WhatsApp.jpg", Category.SCREENSHOT, "WhatsApp"),
        ("Pictures/Screenshots/Screenshot_20261101-101010.png", Category.SCREENSHOT, "Screenshot"),
        ("Movies/Screen recordings/Screen_Recording_20261101_101010.mp4", Category.SCREEN_RECORDING, "Screen recorder"),
        ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/IMG-20261101-WA0001.jpg", Category.CHAT_IMAGE, "WhatsApp"),
        ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/Sent/IMG-20261101-WA0002.jpg", Category.CHAT_IMAGE, "WhatsApp · sent"),
        ("WhatsApp/Media/WhatsApp Video/VID-20261101-WA0001.mp4", Category.CHAT_VIDEO, "WhatsApp"),
        ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Voice Notes/202644/PTT-20261101-WA0001.opus", Category.VOICE_NOTE, "WhatsApp"),
        ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Stickers/STK-20261101-WA0001.webp", Category.STICKER, "WhatsApp"),
        ("Android/media/com.whatsapp.w4b/WhatsApp Business/Media/WhatsApp Business Images/IMG-20261101-WA0001.jpg", Category.CHAT_IMAGE, "WhatsApp Business"),
        ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents/contract.pdf", Category.DOCUMENT, "WhatsApp"),
        ("Pictures/Telegram/IMG_20261101_101010_1.jpg", Category.CHAT_IMAGE, "Telegram"),
        ("Pictures/Snapseed/IMG_20261101_101010.jpg", Category.EDITED, "Snapseed"),
        ("Pictures/Instagram/IMG_20261101_101010.jpg", Category.DOWNLOAD, "Instagram"),
        ("Download/meme.jpg", Category.DOWNLOAD, "Downloads"),
        ("Download/ticket.pdf", Category.DOCUMENT, "Downloads"),
        ("Recordings/Voice Recorder/Recording 1.m4a", Category.AUDIO, "Recorder"),
        ("Music/song.mp3", Category.AUDIO, "Music"),
        ("Documents/notes.pdf", Category.DOCUMENT, "Documents"),
        ("Download/app.apk", Category.OTHER, "Downloads"),
    ],
)
def test_folder_rules(path, category, origin):
    f = mf(path)
    classify(f, OWN)
    assert f.category == category, f.reason
    assert f.origin == origin
    assert f.reason


def test_whatsapp_document_with_foreign_camera_is_received():
    f = mf("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents/IMG_4410.JPG",
           camera_make="Apple", camera_model="iPhone 15 Pro", width=4032, height=3024)
    classify(f, OWN)
    assert f.category == Category.RECEIVED_PHOTO
    assert f.confidence == Confidence.SURE
    assert "iPhone 15 Pro" in f.reason


def test_download_with_own_camera_is_camera_photo():
    f = mf("Download/IMG_20261101_101010.jpg", camera_make="Google", camera_model="Pixel 8")
    classify(f, OWN)
    assert f.category == Category.CAMERA_PHOTO


def test_screen_sized_download_without_exif_is_screenshot():
    f = mf("Download/image.png", width=1080, height=2400)
    classify(f, OWN)
    assert f.category == Category.SCREENSHOT
    assert f.confidence == Confidence.LIKELY


def test_unknown_own_camera_gives_guess():
    f = mf("Download/DSC_0192.jpg", camera_make="Canon", camera_model="Canon EOS R6")
    classify(f, ClassifyContext())
    assert f.category == Category.RECEIVED_PHOTO
    assert f.confidence == Confidence.GUESS


def test_camera_folder_with_foreign_exif_is_flagged():
    f = mf("DCIM/Camera/IMG_1.jpg", camera_make="Apple", camera_model="iPhone 15")
    classify(f, OWN)
    assert f.category == Category.CAMERA_PHOTO
    assert f.confidence == Confidence.LIKELY


def test_received_whatsapp_image_with_surviving_exif():
    f = mf("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/IMG-20261101-WA0001.jpg",
           camera_make="samsung", camera_model="SM-S918B")
    classify(f, OWN)
    assert f.category == Category.RECEIVED_PHOTO


def test_user_camera_setting_matches_model_only():
    ctx = ClassifyContext(user_cameras={"Pixel 8"})
    assert ctx.is_own("Google Pixel 8") is True
    assert ctx.is_own("Pixel 8 Pro") is False


@pytest.mark.parametrize(
    "name, expected, has_time",
    [
        ("PXL_20261101_101010123.jpg", datetime(2026, 11, 1, 10, 10, 10), True),
        ("IMG_20261101_101010.jpg", datetime(2026, 11, 1, 10, 10, 10), True),
        ("20261101_101010.jpg", datetime(2026, 11, 1, 10, 10, 10), True),
        ("Screenshot_20261101-101010_Chrome.jpg", datetime(2026, 11, 1, 10, 10, 10), True),
        ("Screenshot 2026-11-01 at 10.10.10.png", datetime(2026, 11, 1, 10, 10, 10), True),
        ("IMG-20261101-WA0001.jpg", datetime(2026, 11, 1), False),
    ],
)
def test_dates_from_filenames(name, expected, has_time):
    assert date_from_name(name) == (expected, has_time)


def test_date_from_name_rejects_invalid():
    assert date_from_name("IMG_20261399_999999.jpg") == (None, False)


def test_exclusions():
    pats = ["Android/data", ".thumbnails", ".trashed-*"]
    assert is_excluded("Android/data/com.x/file", pats, True)
    assert is_excluded("DCIM/.thumbnails/1.jpg", pats, True)
    assert is_excluded("DCIM/Camera/.trashed-1-IMG.jpg", pats, True)
    assert is_excluded("Android/media/com.whatsapp/WhatsApp/Media/.Statuses/a.jpg", [], False)
    assert not is_excluded("DCIM/Camera/IMG.jpg", pats, False)
