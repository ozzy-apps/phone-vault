from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .. import APP_ID


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_ID


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / APP_ID


METADATA_MODES = ("smart", "all", "off")
DENSITIES = ("comfortable", "compact")


@dataclass
class Settings:
    # Appearance
    theme: str = "inca"
    accent_override: str = ""
    font_scale: float = 1.0
    density: str = "comfortable"
    show_details: bool = True
    view_mode: str = "grid"  # grid | list
    grid_size: str = "M"  # S | M | L
    sort_key: str = "date"  # date | name | size

    # Sorting
    metadata_mode: str = "smart"
    own_cameras: list[str] = field(default_factory=list)

    # Scanning
    exclude_patterns: list[str] = field(
        default_factory=lambda: ["Android/data", "Android/obb", ".thumbnails", ".trashed-*", ".nomedia"]
    )
    include_hidden: bool = False
    adb_path: str = ""

    # State
    recent_folders: list[str] = field(default_factory=list)
    last_source: str = ""
    window_geometry: str = ""
    splitter_state: str = ""

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.path().read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        s = cls(**{k: v for k, v in data.items() if k in known})
        if s.metadata_mode not in METADATA_MODES:
            s.metadata_mode = "smart"
        if s.density not in DENSITIES:
            s.density = "comfortable"
        s.font_scale = min(1.5, max(0.8, float(s.font_scale)))
        if s.view_mode not in ("grid", "list"):
            s.view_mode = "grid"
        if s.grid_size not in ("S", "M", "L"):
            s.grid_size = "M"
        if s.sort_key not in ("date", "name", "size"):
            s.sort_key = "date"
        return s

    def save(self) -> None:
        p = self.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), "utf-8")
        tmp.replace(p)

    def copy(self) -> "Settings":
        return Settings(**json.loads(json.dumps(asdict(self))))

    def remember_folder(self, folder: str) -> None:
        if folder in self.recent_folders:
            self.recent_folders.remove(folder)
        self.recent_folders.insert(0, folder)
        del self.recent_folders[6:]
