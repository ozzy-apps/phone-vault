"""Colour themes.

The default theme follows the look of Inca (near-black neutral panels, amber
accent). Extra themes can be dropped into ``~/.config/phone-vault/themes/*.json``.
Any field left out falls back to the default theme, so a file with just
``{"name": "Mine", "accent": "#3d8bfd"}`` is a valid theme.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from PySide6.QtGui import QColor

from ..core.settings import config_dir


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    dark: bool
    bg: str  # window, menu bar, status bar
    surface: str  # panels
    sidebar: str  # navigation column
    field: str  # inputs, cards, segmented-control track
    surface_alt: str  # section headers, alternate rows
    raised: str  # hover, active tab
    border: str
    text: str
    text_muted: str
    accent: str
    accent_text: str  # text on a solid accent fill
    sel_strong: str  # selected navigation item / active segment
    sel_soft: str  # selected table row
    warning: str
    danger: str

    def q(self, attr: str, alpha: float | None = None) -> QColor:
        c = QColor(getattr(self, attr))
        if alpha is not None:
            c.setAlphaF(alpha)
        return c


BUILTIN_THEMES: dict[str, Theme] = {
    t.key: t
    for t in (
        Theme(
            key="inca", name="Inca", dark=True,
            bg="#111214", surface="#1b1c20", sidebar="#18191c", field="#141518", surface_alt="#1f2126",
            raised="#2e3036", border="#26282d", text="#e4e4e6", text_muted="#8b8d94",
            accent="#e4ab41", accent_text="#16120a", sel_strong="#594d39", sel_soft="#393125",
            warning="#d98b55", danger="#e0604f",
        ),
        Theme(
            key="inca-blue", name="Inca Blue", dark=True,
            bg="#111214", surface="#1b1c20", sidebar="#18191c", field="#141518", surface_alt="#1f2126",
            raised="#2e3036", border="#26282d", text="#e4e4e6", text_muted="#8b8d94",
            accent="#4a90e2", accent_text="#ffffff", sel_strong="#344a63", sel_soft="#24303f",
            warning="#e4ab41", danger="#e0604f",
        ),
        Theme(
            key="graphite", name="Graphite", dark=True,
            bg="#1a1b1e", surface="#232428", sidebar="#202125", field="#1c1d20", surface_alt="#28292e",
            raised="#34363c", border="#313338", text="#e8e8ea", text_muted="#979aa1",
            accent="#5a9be6", accent_text="#0f141a", sel_strong="#3a4c62", sel_soft="#2b3543",
            warning="#e4ab41", danger="#e66a5a",
        ),
        Theme(
            key="light", name="Light", dark=False,
            bg="#e6e7ea", surface="#f4f4f6", sidebar="#eeeff1", field="#ffffff", surface_alt="#ebecef",
            raised="#dfe1e5", border="#d3d5da", text="#1d1f23", text_muted="#626670",
            accent="#b97a12", accent_text="#ffffff", sel_strong="#ead7b2", sel_soft="#f2e7d1",
            warning="#b4541f", danger="#b8382b",
        ),
    )
}

DEFAULT_THEME = "inca"
_COLOR_FIELDS = [f.name for f in fields(Theme) if f.name not in ("key", "name", "dark")]


def mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    ).name()


def themes_dir() -> Path:
    return config_dir() / "themes"


def load_user_themes(folder: Path | None = None) -> dict[str, Theme]:
    folder = folder or themes_dir()
    base = asdict(BUILTIN_THEMES[DEFAULT_THEME])
    found: dict[str, Theme] = {}
    try:
        files = sorted(folder.glob("*.json"))
    except OSError:
        return found
    for path in files:
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        merged = dict(base)
        merged.update({k: v for k, v in data.items() if k in base and k != "key"})
        merged["key"] = f"user:{path.stem}"
        merged["name"] = str(data.get("name") or path.stem)
        if "dark" not in data:
            merged["dark"] = QColor(merged["bg"]).lightnessF() < 0.5
        # Derive selection colours from the accent when a theme only sets the accent.
        if "accent" in data and "sel_strong" not in data:
            merged["sel_strong"] = mix(merged["surface"], mix(merged["accent"], "#808080", 0.35), 0.42)
        if "accent" in data and "sel_soft" not in data:
            merged["sel_soft"] = mix(merged["surface"], merged["accent"], 0.18)
        if not all(QColor(str(merged[name])).isValid() for name in _COLOR_FIELDS):
            continue
        found[merged["key"]] = Theme(**merged)
    return found


def all_themes() -> dict[str, Theme]:
    return {**BUILTIN_THEMES, **load_user_themes()}


def resolve_theme(key: str, accent_override: str = "") -> Theme:
    theme = all_themes().get(key, BUILTIN_THEMES[DEFAULT_THEME])
    if accent_override and QColor(accent_override).isValid():
        acc = QColor(accent_override).name()
        text = "#10141a" if QColor(acc).lightnessF() > 0.6 else "#ffffff"
        theme = replace(
            theme,
            accent=acc,
            accent_text=text,
            sel_strong=mix(theme.surface, mix(acc, "#808080", 0.35), 0.42),
            sel_soft=mix(theme.surface, acc, 0.18),
        )
    return theme


def write_theme_template(theme: Theme, folder: Path | None = None) -> Path:
    """Save ``theme`` as an editable JSON file and return its path."""
    folder = folder or themes_dir()
    folder.mkdir(parents=True, exist_ok=True)
    data = asdict(theme)
    data.pop("key")
    data["name"] = f"{theme.name} (custom)"
    stem, n = "custom", 1
    while (folder / f"{stem}.json").exists():
        n += 1
        stem = f"custom-{n}"
    path = folder / f"{stem}.json"
    path.write_text(json.dumps(data, indent=2), "utf-8")
    return path
