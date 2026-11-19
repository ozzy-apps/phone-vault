"""Small stroke icons rendered from inline SVG in any theme colour."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "settings": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/>'
                '<circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "export": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
    "scan": '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/>'
            '<path d="M8 12h8"/>',
    "phone": '<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M11 18h2"/>',
    "open": '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/>'
            '<path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "chevron-right": '<path d="M9 6l6 6-6 6"/>',
    "grid": '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/>'
            '<rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="0.8"/><circle cx="4.5" cy="12" r="0.8"/>'
            '<circle cx="4.5" cy="18" r="0.8"/>',
    "panel": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/>'
             '<path d="M21 17l-5-5-8 8"/>',
    "video": '<rect x="3" y="5" width="13" height="14" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>',
    "audio": '<path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
    "file": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
}


def svg(name: str, color: str, width: float = 1.8) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">'
        f"{_PATHS[name]}</svg>"
    )


def _render(svg_text: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_text.encode()))
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return QPixmap.fromImage(img)


@lru_cache(maxsize=256)
def icon(name: str, color: str) -> QIcon:
    ic = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        ic.addPixmap(_render(svg(name, color), size))
    return ic


def pixmap(name: str, color: str, size: int) -> QPixmap:
    return _render(svg(name, color), size)


def write_svg(name: str, color: str, folder: Path, width: float = 2.4) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}-{color.lstrip('#')}-{width:g}.svg"
    if not path.exists():
        path.write_text(svg(name, color, width), "utf-8")
    return path
