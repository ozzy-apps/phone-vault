import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from phonevault.ui.thumbnails import exif_thumbnail  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_user_theme_with_only_accent(app, tmp_path):
    from phonevault.ui.themes import BUILTIN_THEMES, load_user_themes

    (tmp_path / "mine.json").write_text(json.dumps({"name": "Mine", "accent": "#3d8bfd"}))
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "bad-color.json").write_text(json.dumps({"accent": "not-a-colour"}))
    themes = load_user_themes(tmp_path)
    assert list(themes) == ["user:mine"]
    t = themes["user:mine"]
    assert t.name == "Mine" and t.accent == "#3d8bfd"
    assert t.bg == BUILTIN_THEMES["inca"].bg
    assert t.sel_strong != BUILTIN_THEMES["inca"].sel_strong  # derived from the new accent


def test_accent_override(app):
    from phonevault.ui.themes import resolve_theme

    t = resolve_theme("inca", "#ffffff")
    assert t.accent == "#ffffff" and t.accent_text != "#ffffff"


def test_no_green_in_builtin_themes(app):
    from PySide6.QtGui import QColor

    from phonevault.ui.themes import BUILTIN_THEMES

    for theme in BUILTIN_THEMES.values():
        hue = QColor(theme.accent).hslHue()
        assert not (75 <= hue <= 165), theme.key


def test_stylesheet_builds_for_every_theme(app, tmp_path):
    from phonevault.ui.style import build_stylesheet
    from phonevault.ui.themes import BUILTIN_THEMES

    for theme in BUILTIN_THEMES.values():
        css = build_stylesheet(theme, 1.0, "compact", tmp_path)
        assert theme.accent in css


def test_exif_thumbnail_extracted(tmp_path):
    from PIL import Image

    thumb_path = tmp_path / "t.jpg"
    Image.new("RGB", (160, 120), (10, 20, 30)).save(thumb_path, "JPEG")
    thumb = thumb_path.read_bytes()
    photo_path = tmp_path / "photo.jpg"
    Image.new("RGB", (800, 600), (200, 120, 40)).save(photo_path, "JPEG")
    raw = photo_path.read_bytes()

    # APP1 segment: "Exif" header, a minimal TIFF header, then the embedded thumbnail JPEG.
    payload = b"Exif\x00\x00" + b"II*\x00\x08\x00\x00\x00" + thumb
    app1 = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    with_thumb = raw[:2] + app1 + raw[2:]

    assert exif_thumbnail(with_thumb) == thumb
    assert exif_thumbnail(raw) is None
    assert exif_thumbnail(b"PNG") is None
