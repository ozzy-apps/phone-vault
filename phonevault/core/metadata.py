"""Reads image size and camera EXIF from the first bytes of a file."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime

from PIL import Image

try:  # Optional HEIC/HEIF support.
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover - optional dependency
    pass

HEAD_BYTES = 128 * 1024
RETRY_BYTES = 1024 * 1024

_TAG_MAKE = 271
_TAG_MODEL = 272
_TAG_SOFTWARE = 305
_TAG_DATETIME = 306
_IFD_EXIF = 0x8769
_TAG_DATETIME_ORIGINAL = 36867


@dataclass
class ImageProbe:
    width: int
    height: int
    make: str = ""
    model: str = ""
    software: str = ""
    taken: datetime | None = None

    @property
    def has_camera(self) -> bool:
        return bool(self.make or self.model)


def _clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return str(value).replace("\x00", "").strip()


def _parse_exif_date(value) -> datetime | None:
    text = _clean(value)
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            dt = datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
        if 1990 <= dt.year <= 2100:
            return dt
    return None


def probe_image_bytes(data: bytes) -> ImageProbe | None:
    """Parse the header of an image. Works on truncated data for JPEG/PNG/WebP."""
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
            exif = im.getexif()
            make = _clean(exif.get(_TAG_MAKE))
            model = _clean(exif.get(_TAG_MODEL))
            software = _clean(exif.get(_TAG_SOFTWARE))
            taken = None
            try:
                taken = _parse_exif_date(exif.get_ifd(_IFD_EXIF).get(_TAG_DATETIME_ORIGINAL))
            except Exception:
                taken = None
            if taken is None and (make or model):
                taken = _parse_exif_date(exif.get(_TAG_DATETIME))
    except Exception:
        return None
    return ImageProbe(width, height, make, model, software, taken)


def probe_with_reader(read_head, rel_path: str) -> ImageProbe | None:
    """``read_head(rel_path, nbytes) -> bytes``. Retries once with a larger chunk."""
    data = read_head(rel_path, HEAD_BYTES)
    probe = probe_image_bytes(data)
    if probe is None and len(data) >= HEAD_BYTES:
        probe = probe_image_bytes(read_head(rel_path, RETRY_BYTES))
    return probe
