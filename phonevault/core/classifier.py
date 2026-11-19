"""Rule-based sorting of phone files.

Each file gets a category, an origin (app or source), a confidence level and a
human readable reason. Rules look at, in order: the folder the file lives in,
the filename, and (when probed) the camera EXIF data and pixel size.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from .models import Category, Confidence, Kind, MediaFile


def normalize_camera(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip().lower()


@dataclass
class ClassifyContext:
    user_cameras: set[str] = field(default_factory=set)
    device_cameras: set[str] = field(default_factory=set)
    learned_cameras: set[str] = field(default_factory=set)
    screen_sizes: set[tuple[int, int]] = field(default_factory=set)

    @property
    def own_cameras(self) -> set[str]:
        return {normalize_camera(c) for c in self.user_cameras | self.device_cameras | self.learned_cameras if c}

    def is_own(self, camera: str) -> bool | None:
        """True/False when we know the phone's camera, None when we don't."""
        own = self.own_cameras
        if not own:
            return None
        cam = normalize_camera(camera)
        if not cam:
            return None
        for o in own:
            if cam == o or cam.endswith(" " + o) or o.endswith(" " + cam):
                return True
        return False

    def add_screen_size(self, w: int, h: int) -> None:
        self.screen_sizes.add((w, h))
        self.screen_sizes.add((h, w))


# --- Folder and filename patterns -------------------------------------------

_WA_RE = re.compile(r"(?:^|/)(?P<app>whatsapp(?: business)?)/media/(?P<sub>[^/]+)(?P<rest>/.*)?$")
_TELEGRAM_SUB_RE = re.compile(r"(?:^|/)telegram/telegram (?P<sub>images|video|audio|documents|files)(?P<rest>/.*)?$")
_CHAT_DIRS: list[tuple[str, re.Pattern]] = [
    ("Telegram", re.compile(r"(?:^|/)(?:pictures|movies|music|download|documents)/telegram(?:/|$)")),
    ("Signal", re.compile(r"(?:^|/)(?:pictures|movies|music|download|documents|dcim)/signal(?:/|$)")),
    ("Messenger", re.compile(r"(?:^|/)(?:pictures|movies|dcim)/messenger(?:/|$)")),
    ("Viber", re.compile(r"(?:^|/)viber/media/|(?:^|/)pictures/viber(?:/|$)")),
    ("Discord", re.compile(r"(?:^|/)(?:pictures|movies|download)/discord(?:/|$)")),
]

_SHOT_DIR = re.compile(r"(?:^|/)screenshots?(?:/|$)")
_SHOT_NAME = re.compile(r"^(?:screenshot|screen_shot|screencap|scrnshot)[ _\-]")
_SHOT_APP = re.compile(r"^screenshot_\d{8}[-_]\d{6}(?:\d{0,3})?_(?P<app>[^.]+)\.\w+$", re.IGNORECASE)
_REC_DIR = re.compile(r"(?:^|/)(?:screen ?recordings?|screenrecord(?:er|s|ings?)?|screen_recordings?)(?:/|$)")
_REC_NAME = re.compile(r"^(?:screen[_ \-]?record(?:ing)?|screenrecord|record_screen|screen-\d{8})")

_CAMERA_DIR = re.compile(r"^dcim/(?:camera|opencamera|\d{3}[a-z_]*)/")
_CAMERA_NAME = re.compile(r"^(?:img|vid|pxl|mvimg|dsc|photo|video)?[_-]?\d{8}[_-]\d{6}")

_EDITOR_APPS = {
    "snapseed": "Snapseed",
    "lightroom": "Lightroom",
    "picsart": "PicsArt",
    "vsco": "VSCO",
    "capcut": "CapCut",
    "photo editor": "Photo editor",
    "photoshop express": "Photoshop Express",
}
_SAVED_APPS = {
    "instagram": "Instagram",
    "snapchat": "Snapchat",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "twitter": "X",
    "reddit": "Reddit",
    "pinterest": "Pinterest",
    "threads": "Threads",
    "canva": "Canva",
}
_APP_DIR = re.compile(r"^(?:pictures|movies|dcim)/(?P<app>[^/]+)/")
_EDITOR_SOFTWARE = re.compile(r"snapseed|lightroom|photoshop|picsart|vsco|gimp|darktable", re.IGNORECASE)

_QUICKSHARE_DIR = re.compile(r"^(?:downloads?/)?(?:quick share|nearby share)/")
_BLUETOOTH_DIR = re.compile(r"^(?:downloads?/)?bluetooth/")
_DOWNLOAD_DIR = re.compile(r"^downloads?/")
_RECORDER_DIR = re.compile(r"^(?:recordings|music/recordings|call|callrecordings|call recordings|sounds|voice recorder|recorder)/")
_MUSIC_DIR = re.compile(r"^music/")
_SYSTEM_SOUND_DIR = re.compile(r"^(?:ringtones|notifications|alarms)/")
_DOCUMENTS_DIR = re.compile(r"^documents/")
_MOVIES_DIR = re.compile(r"^movies/")

_DATE_TIME_RE = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})[_\-]?(\d{2})(\d{2})(\d{2})")
_DATE_TIME_DASHED_RE = re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})[-_ ](?:at )?(\d{2})[-.:](\d{2})[-.:](\d{2})")
_DATE_ONLY_RE = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?=-WA|_WA|-)", re.IGNORECASE)


def date_from_name(name: str) -> tuple[datetime | None, bool]:
    """Returns (datetime, has_time)."""
    for rx in (_DATE_TIME_RE, _DATE_TIME_DASHED_RE):
        m = rx.search(name)
        if m:
            try:
                return datetime(*map(int, m.groups())), True
            except ValueError:
                pass
    m = _DATE_ONLY_RE.search(name)
    if m:
        try:
            return datetime(*map(int, m.groups())), False
        except ValueError:
            pass
    return None, False


def _wa_sub(sub: str) -> str:
    s = sub.lower().lstrip(".")
    if "voice note" in s:
        return "voice"
    if "video note" in s:
        return "video"
    if "animated gif" in s or "sticker" in s:
        return "sticker"
    if "status" in s:
        return "status"
    if "profile photo" in s:
        return "profile"
    if "document" in s:
        return "documents"
    if "image" in s:
        return "images"
    if "video" in s:
        return "video"
    if "audio" in s:
        return "audio"
    return "other"


def _set(f: MediaFile, category: Category, confidence: Confidence, reason: str, origin: str = "",
         wants_probe: bool = False) -> None:
    f.category = category
    f.confidence = confidence
    f.reason = reason
    f.origin = origin
    f.wants_probe = wants_probe


def _by_kind(f: MediaFile, origin: str, reason: str, confidence: Confidence = Confidence.LIKELY) -> None:
    mapping = {
        Kind.IMAGE: Category.OTHER_IMAGE,
        Kind.VIDEO: Category.OTHER_VIDEO,
        Kind.AUDIO: Category.AUDIO,
        Kind.DOCUMENT: Category.DOCUMENT,
    }
    _set(f, mapping.get(f.kind, Category.OTHER), confidence, reason, origin, f.kind == Kind.IMAGE)


# --- Rules -------------------------------------------------------------------

def _rule_chat(f: MediaFile, p: str) -> bool:
    m = _WA_RE.search(p)
    if m:
        app = "WhatsApp Business" if "business" in m.group("app") else "WhatsApp"
        sub = _wa_sub(m.group("sub"))
        rest = m.group("rest") or ""
        sent = rest.startswith("/sent/")
        return _apply_chat(f, app, sub, sent)
    m = _TELEGRAM_SUB_RE.search(p)
    if m:
        sub = {"images": "images", "video": "video", "audio": "audio"}.get(m.group("sub"), "documents")
        return _apply_chat(f, "Telegram", sub, False)
    for app, rx in _CHAT_DIRS:
        if rx.search(p):
            sub = {Kind.IMAGE: "images", Kind.VIDEO: "video", Kind.AUDIO: "audio"}.get(f.kind, "documents")
            return _apply_chat(f, app, sub, False)
    return False


def _apply_chat(f: MediaFile, app: str, sub: str, sent: bool) -> bool:
    f.sent = sent
    origin = f"{app} · sent" if sent else app
    sure = Confidence.SURE
    if sub == "sticker":
        _set(f, Category.STICKER, sure, f"{app} stickers/GIFs folder", origin)
    elif sub == "voice":
        _set(f, Category.VOICE_NOTE, sure, f"{app} voice notes folder", origin)
    elif sub == "status":
        cat = Category.CHAT_VIDEO if f.kind == Kind.VIDEO else Category.CHAT_IMAGE
        _set(f, cat, sure, f"Saved {app} status", origin)
    elif sub == "profile":
        _set(f, Category.CHAT_IMAGE, sure, f"{app} profile photo", origin)
    elif sub == "documents":
        if f.kind == Kind.IMAGE:
            _set(f, Category.CHAT_IMAGE, Confidence.LIKELY,
                 f"Image sent as a {app} document (original quality, metadata kept)", origin, True)
        elif f.kind == Kind.VIDEO:
            _set(f, Category.CHAT_VIDEO, sure, f"Video sent as a {app} document", origin)
        else:
            _by_kind(f, origin, f"{app} documents folder", sure)
    elif sub == "images" and f.kind == Kind.IMAGE:
        reason = f"Sent by you via {app} (compressed copy)" if sent else f"{app} images folder"
        _set(f, Category.CHAT_IMAGE, sure, reason, origin)
    elif sub == "video" or (sub == "images" and f.kind == Kind.VIDEO):
        reason = f"Sent by you via {app} (compressed copy)" if sent else f"{app} video folder"
        _set(f, Category.CHAT_VIDEO, sure, reason, origin)
    elif sub == "audio":
        _set(f, Category.AUDIO, sure, f"{app} audio folder", origin)
    else:
        if f.kind == Kind.IMAGE:
            _set(f, Category.CHAT_IMAGE, Confidence.LIKELY, f"{app} media folder", origin)
        elif f.kind == Kind.VIDEO:
            _set(f, Category.CHAT_VIDEO, Confidence.LIKELY, f"{app} media folder", origin)
        else:
            _by_kind(f, origin, f"{app} media folder")
    return True


def _rule_screen(f: MediaFile, p: str, name: str) -> bool:
    if f.kind == Kind.IMAGE and (_SHOT_DIR.search(p) or _SHOT_NAME.match(name)):
        m = _SHOT_APP.match(f.name)
        origin = m.group("app").replace("_", " ") if m else "Screenshot"
        where = "Screenshots folder" if _SHOT_DIR.search(p) else "Screenshot filename"
        _set(f, Category.SCREENSHOT, Confidence.SURE, where, origin)
        return True
    if f.kind == Kind.VIDEO and (_REC_DIR.search(p) or _REC_NAME.match(name)):
        where = "Screen recordings folder" if _REC_DIR.search(p) else "Screen recording filename"
        _set(f, Category.SCREEN_RECORDING, Confidence.SURE, where, "Screen recorder")
        return True
    return False


def _rule_app_folders(f: MediaFile, p: str) -> bool:
    m = _APP_DIR.match(p)
    if not m or f.kind not in (Kind.IMAGE, Kind.VIDEO):
        return False
    folder = m.group("app")
    for key, label in _EDITOR_APPS.items():
        if key in folder:
            if f.kind == Kind.IMAGE:
                _set(f, Category.EDITED, Confidence.LIKELY, f"Exported from {label}", label)
            else:
                _set(f, Category.OTHER_VIDEO, Confidence.LIKELY, f"Exported from {label}", label)
            return True
    for key, label in _SAVED_APPS.items():
        if key == folder or folder.startswith(key):
            _set(f, Category.DOWNLOAD, Confidence.LIKELY, f"Saved from {label}", label, f.kind == Kind.IMAGE)
            return True
    return False


def _rule_camera(f: MediaFile, p: str, name: str) -> bool:
    if f.kind not in (Kind.IMAGE, Kind.VIDEO):
        return False
    in_camera_dir = bool(_CAMERA_DIR.match(p))
    in_dcim = p.startswith("dcim/")
    if not (in_camera_dir or in_dcim):
        return False
    conf = Confidence.SURE if in_camera_dir else Confidence.LIKELY
    where = "Camera folder" if in_camera_dir else "DCIM folder"
    cat = Category.CAMERA_PHOTO if f.kind == Kind.IMAGE else Category.CAMERA_VIDEO
    _set(f, cat, conf, where, "Camera")
    return True


def _rule_transfers(f: MediaFile, p: str) -> bool:
    for rx, origin in ((_QUICKSHARE_DIR, "Quick Share"), (_BLUETOOTH_DIR, "Bluetooth")):
        if rx.match(p):
            if f.kind == Kind.IMAGE:
                _set(f, Category.RECEIVED_PHOTO, Confidence.LIKELY, f"Received via {origin}", origin, True)
            elif f.kind == Kind.VIDEO:
                _set(f, Category.DOWNLOAD, Confidence.LIKELY, f"Received via {origin}", origin)
            else:
                _by_kind(f, origin, f"Received via {origin}")
            return True
    if _DOWNLOAD_DIR.match(p):
        if f.kind in (Kind.IMAGE, Kind.VIDEO):
            _set(f, Category.DOWNLOAD, Confidence.LIKELY, "Download folder", "Downloads", f.kind == Kind.IMAGE)
        else:
            _by_kind(f, "Downloads", "Download folder", Confidence.SURE)
        return True
    return False


def _rule_files(f: MediaFile, p: str) -> bool:
    if f.kind == Kind.AUDIO:
        if _RECORDER_DIR.match(p):
            _set(f, Category.AUDIO, Confidence.SURE, "Recordings folder", "Recorder")
            return True
        if _SYSTEM_SOUND_DIR.match(p):
            _set(f, Category.AUDIO, Confidence.SURE, "System sounds folder", "System sounds")
            return True
        if _MUSIC_DIR.match(p):
            _set(f, Category.AUDIO, Confidence.SURE, "Music folder", "Music")
            return True
    if _DOCUMENTS_DIR.match(p):
        _by_kind(f, "Documents", "Documents folder", Confidence.SURE)
        return True
    if f.kind == Kind.VIDEO and _MOVIES_DIR.match(p):
        _set(f, Category.OTHER_VIDEO, Confidence.LIKELY, "Movies folder", "Movies")
        return True
    return False


def _refine_with_metadata(f: MediaFile, ctx: ClassifyContext) -> None:
    if f.kind != Kind.IMAGE or not f.probed:
        return
    cam = f.camera
    own = ctx.is_own(cam) if cam else None

    # Files already placed in a camera folder: only annotate.
    if f.category == Category.CAMERA_PHOTO and f.confidence == Confidence.SURE:
        if cam and own is False:
            f.reason = f"Camera folder, but camera data says {cam}"
            f.confidence = Confidence.LIKELY
        elif cam and own and f.software and _EDITOR_SOFTWARE.search(f.software):
            _set(f, Category.EDITED, Confidence.LIKELY, f"Your camera ({cam}), edited in {f.software}", f.origin)
        return

    # Received chat images usually have their EXIF stripped; when it survives, use it.
    if not (f.wants_probe or (f.category == Category.CHAT_IMAGE and not f.sent)):
        return

    in_chat = f.category in (Category.CHAT_IMAGE, Category.CHAT_VIDEO)
    origin = f.origin
    if cam:
        if own is True:
            if f.software and _EDITOR_SOFTWARE.search(f.software):
                _set(f, Category.EDITED, Confidence.LIKELY, f"Your camera ({cam}), edited in {f.software}", origin)
            else:
                where = f" — copy in {origin}" if origin else ""
                _set(f, Category.CAMERA_PHOTO, Confidence.LIKELY, f"Your camera ({cam}){where}", origin or "Camera")
        elif own is False:
            _set(f, Category.RECEIVED_PHOTO, Confidence.SURE, f"Camera data from {cam} — not your phone", origin)
        else:
            _set(f, Category.RECEIVED_PHOTO, Confidence.GUESS,
                 f"Camera data from {cam}; your phone's camera is not known yet", origin)
        return

    if not in_chat and f.width and f.height and (f.width, f.height) in ctx.screen_sizes:
        _set(f, Category.SCREENSHOT, Confidence.LIKELY,
             f"No camera data, {f.width}×{f.height} matches your screen", origin or "Screenshot")


def assign_date(f: MediaFile) -> None:
    if f.exif_taken:
        f.taken_at, f.date_source = f.exif_taken, "photo metadata"
        return
    dt, has_time = date_from_name(f.name)
    if dt:
        if not has_time:
            mt = datetime.fromtimestamp(f.mtime) if f.mtime else None
            if mt and mt.date() == dt.date():
                dt = mt
        f.taken_at, f.date_source = dt, "filename"
        return
    f.taken_at = datetime.fromtimestamp(f.mtime) if f.mtime else None
    f.date_source = "file date"


def classify(f: MediaFile, ctx: ClassifyContext) -> None:
    p = f.rel_path.lower()
    name = f.name.lower()
    f.sent = False
    (
        _rule_chat(f, p)
        or _rule_screen(f, p, name)
        or _rule_app_folders(f, p)
        or _rule_camera(f, p, name)
        or _rule_transfers(f, p)
        or _rule_files(f, p)
        or _fallback(f, name)
    )
    _refine_with_metadata(f, ctx)
    assign_date(f)


def _fallback(f: MediaFile, name: str) -> bool:
    if f.kind == Kind.IMAGE and _CAMERA_NAME.match(name):
        _set(f, Category.OTHER_IMAGE, Confidence.GUESS, "Camera-style filename outside the camera folder",
             "", True)
        return True
    _by_kind(f, "", "No folder rule matched", Confidence.GUESS)
    return True


def classify_all(files: list[MediaFile], ctx: ClassifyContext) -> None:
    for f in files:
        classify(f, ctx)


def learn_from_samples(files: list[MediaFile], ctx: ClassifyContext) -> None:
    """Learn the phone's own camera model(s) and screen size(s) from probed files."""
    cams = Counter(
        f.camera
        for f in files
        if f.probed and f.camera and f.category == Category.CAMERA_PHOTO and _CAMERA_DIR.match(f.rel_path.lower())
    )
    total = sum(cams.values())
    ctx.learned_cameras = {c for c, n in cams.items() if n >= 2 or (total and n / total >= 0.2)} if total else set()
    sizes = Counter(
        (f.width, f.height)
        for f in files
        if f.probed and f.width and f.category == Category.SCREENSHOT and f.confidence == Confidence.SURE
    )
    for (w, h), _n in sizes.most_common(4):
        ctx.add_screen_size(w, h)
