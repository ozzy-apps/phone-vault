from __future__ import annotations

import posixpath
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Kind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    APP = "app"
    OTHER = "other"


_EXT_KIND: dict[str, Kind] = {}
for _kind, _exts in {
    Kind.IMAGE: "jpg jpeg png webp heic heif gif bmp dng raw tif tiff avif",
    Kind.VIDEO: "mp4 mov mkv webm 3gp avi m4v ts",
    Kind.AUDIO: "mp3 m4a aac opus ogg wav flac amr awb mid midi",
    Kind.DOCUMENT: "pdf doc docx odt xls xlsx ods ppt pptx odp txt rtf csv epub md vcf ics",
    Kind.ARCHIVE: "zip rar 7z tar gz tgz xz bz2",
    Kind.APP: "apk apks xapk",
}.items():
    for _ext in _exts.split():
        _EXT_KIND[_ext] = _kind


def kind_for(name: str) -> Kind:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _EXT_KIND.get(ext, Kind.OTHER)


class Category(str, Enum):
    CAMERA_PHOTO = "camera_photo"
    CAMERA_VIDEO = "camera_video"
    EDITED = "edited"
    SCREENSHOT = "screenshot"
    SCREEN_RECORDING = "screen_recording"
    CHAT_IMAGE = "chat_image"
    CHAT_VIDEO = "chat_video"
    VOICE_NOTE = "voice_note"
    STICKER = "sticker"
    RECEIVED_PHOTO = "received_photo"
    DOWNLOAD = "download"
    DOCUMENT = "document"
    AUDIO = "audio"
    OTHER_IMAGE = "other_image"
    OTHER_VIDEO = "other_video"
    OTHER = "other"


@dataclass(frozen=True)
class CategoryInfo:
    label: str
    group: str
    color: str
    order: int


GROUPS = ("Yours", "Chats", "Received", "Files")

CATEGORY_INFO: dict[Category, CategoryInfo] = {
    Category.CAMERA_PHOTO: CategoryInfo("Camera photos", "Yours", "#4a90e2", 0),
    Category.CAMERA_VIDEO: CategoryInfo("Camera videos", "Yours", "#83b3ee", 1),
    Category.EDITED: CategoryInfo("Edited photos", "Yours", "#6a7fc4", 2),
    Category.SCREENSHOT: CategoryInfo("Screenshots", "Yours", "#d9a441", 3),
    Category.SCREEN_RECORDING: CategoryInfo("Screen recordings", "Yours", "#e8c77e", 4),
    Category.CHAT_IMAGE: CategoryInfo("Chat images", "Chats", "#c4623f", 5),
    Category.CHAT_VIDEO: CategoryInfo("Chat videos", "Chats", "#de8a66", 6),
    Category.VOICE_NOTE: CategoryInfo("Voice notes", "Chats", "#a3442e", 7),
    Category.STICKER: CategoryInfo("Stickers & GIFs", "Chats", "#ebb59e", 8),
    Category.RECEIVED_PHOTO: CategoryInfo("Received photos", "Received", "#9b6bc9", 9),
    Category.DOWNLOAD: CategoryInfo("Downloads & saved", "Received", "#c39be0", 10),
    Category.DOCUMENT: CategoryInfo("Documents", "Files", "#8d939c", 11),
    Category.AUDIO: CategoryInfo("Audio", "Files", "#c75a7a", 12),
    Category.OTHER_IMAGE: CategoryInfo("Other images", "Files", "#b0a89c", 13),
    Category.OTHER_VIDEO: CategoryInfo("Other videos", "Files", "#857f76", 14),
    Category.OTHER: CategoryInfo("Other files", "Files", "#66625c", 15),
}

CATEGORIES_IN_ORDER = sorted(CATEGORY_INFO, key=lambda c: CATEGORY_INFO[c].order)


class Confidence(str, Enum):
    SURE = "sure"
    LIKELY = "likely"
    GUESS = "guess"

    @property
    def label(self) -> str:
        return self.value.capitalize()


@dataclass
class RemoteEntry:
    """A file as listed by a source. ``rel_path`` is POSIX, relative to the storage root."""

    rel_path: str
    size: int
    mtime: float


@dataclass
class MediaFile:
    rel_path: str
    size: int
    mtime: float
    kind: Kind = Kind.OTHER

    # Filled by metadata probing.
    probed: bool = False
    width: int | None = None
    height: int | None = None
    camera_make: str = ""
    camera_model: str = ""
    software: str = ""
    exif_taken: datetime | None = None

    # Filled by the classifier.
    category: Category = Category.OTHER
    origin: str = ""
    reason: str = ""
    confidence: Confidence = Confidence.GUESS
    sent: bool = False
    wants_probe: bool = False
    taken_at: datetime | None = None
    date_source: str = ""

    @classmethod
    def from_entry(cls, entry: RemoteEntry) -> "MediaFile":
        name = posixpath.basename(entry.rel_path)
        return cls(entry.rel_path, entry.size, entry.mtime, kind_for(name))

    @property
    def name(self) -> str:
        return posixpath.basename(self.rel_path)

    @property
    def folder(self) -> str:
        return posixpath.dirname(self.rel_path)

    @property
    def ext(self) -> str:
        n = self.name
        return n.rsplit(".", 1)[-1].lower() if "." in n else ""

    @property
    def camera(self) -> str:
        make, model = self.camera_make.strip(), self.camera_model.strip()
        if make.islower():
            make = make.capitalize()
        if not model:
            return make
        if make and not model.lower().startswith(make.lower()):
            return f"{make} {model}"
        return model

    @property
    def timestamp(self) -> float:
        return self.taken_at.timestamp() if self.taken_at else self.mtime

    @property
    def category_label(self) -> str:
        return CATEGORY_INFO[self.category].label


def human_size(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}" if n < 100 else f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
