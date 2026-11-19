"""Qt stylesheet + palette generated from a Theme (Inca-style layout language)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from ..core.settings import cache_dir
from .icons import write_svg
from .themes import Theme

FONT_CANDIDATES = ("Inter", "Cantarell", "Ubuntu", "Noto Sans", "Fira Sans", "DejaVu Sans")
MONO_CANDIDATES = ("JetBrains Mono", "Fira Code", "Ubuntu Mono", "Source Code Pro", "DejaVu Sans Mono",
                   "Liberation Mono", "Monospace")
BASE_POINT_SIZE = 9.75


def _pick(candidates: tuple[str, ...], fallback: str) -> str:
    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            return name
    return fallback


def ui_family() -> str:
    return _pick(FONT_CANDIDATES, QApplication.font().family())


def mono_family() -> str:
    return _pick(MONO_CANDIDATES, QFontDatabase.systemFont(QFontDatabase.FixedFont).family())


def mono_font(scale: float = 1.0, size: float = 8.75) -> QFont:
    f = QFont(mono_family())
    f.setPointSizeF(size * scale)
    return f


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {int(alpha * 255)})"


def build_palette(t: Theme) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: t.bg,
        QPalette.WindowText: t.text,
        QPalette.Base: t.surface,
        QPalette.AlternateBase: t.surface_alt,
        QPalette.ToolTipBase: t.raised,
        QPalette.ToolTipText: t.text,
        QPalette.PlaceholderText: t.text_muted,
        QPalette.Text: t.text,
        QPalette.Button: t.surface_alt,
        QPalette.ButtonText: t.text,
        QPalette.BrightText: t.danger,
        QPalette.Highlight: t.sel_strong,
        QPalette.HighlightedText: t.text,
        QPalette.Link: t.accent,
        QPalette.Mid: t.border,
        QPalette.Dark: t.bg,
        QPalette.Light: t.raised,
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(t.text_muted))
    return p


def build_stylesheet(t: Theme, scale: float = 1.0, density: str = "comfortable",
                     icon_dir: Path | None = None) -> str:
    folder = icon_dir or cache_dir() / "icons"
    check = write_svg("check", t.accent_text, folder).as_posix()
    arrow = write_svg("chevron-down", t.text_muted, folder).as_posix()
    branch_open = write_svg("chevron-down", t.text_muted, folder, 2.0).as_posix()
    branch_closed = write_svg("chevron-right", t.text_muted, folder, 2.0).as_posix()
    pad = 5 if density == "comfortable" else 3
    row = 25 if density == "comfortable" else 21
    s = lambda v: max(1, round(v * scale))  # noqa: E731
    pt = lambda v: f"{v * scale:.2f}pt"  # noqa: E731
    mono = mono_family()
    return f"""
* {{ outline: none; }}
QMainWindow, QDialog {{ background: {t.bg}; }}
QWidget {{ color: {t.text}; }}
QToolTip {{ background: {t.raised}; color: {t.text}; border: 1px solid {t.border}; padding: 4px 7px; }}

/* Top bar and menus */
#TopBar {{ background: {t.bg}; }}
#AppName {{ font-weight: 700; font-size: {pt(10.5)}; }}
QMenuBar {{ background: transparent; border: none; }}
QMenuBar::item {{ background: transparent; padding: 4px 9px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {t.raised}; }}
QMenu {{ background: {t.surface}; border: 1px solid {t.border}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t.sel_strong}; }}
QMenu::item:disabled {{ color: {t.text_muted}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}

/* Panels */
#Panel {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 6px; }}
#Sidebar {{ background: {t.sidebar}; border: 1px solid {t.border}; border-radius: 6px; }}
#PanelTitle {{ font-weight: 600; font-size: {pt(10.5)}; }}
#SectionTitle {{ color: {t.text_muted}; font-size: {pt(7.75)}; font-weight: 600; letter-spacing: 0.6px; }}
#Muted {{ color: {t.text_muted}; }}
#Caption {{ color: {t.text_muted}; font-size: {pt(8.75)}; }}
#Mono {{ font-family: "{mono}"; color: {t.text_muted}; font-size: {pt(8.5)}; }}
#Accent {{ color: {t.accent}; }}
#Warning {{ color: {t.warning}; }}
#EmptyTitle {{ font-size: {pt(11)}; font-weight: 600; }}
#EmptyBody {{ color: {t.text_muted}; }}
#Preview {{ background: {t.field}; border: 1px solid {t.border}; border-radius: 6px; color: {t.text_muted}; }}
#InfoHeader {{ background: {t.surface_alt}; border-radius: 4px; }}
#KeyLabel {{ color: {t.text_muted}; }}
#Pill {{ background: {t.field}; border: 1px solid {t.border}; border-radius: {s(11)}px; }}
QToolButton#Pill {{ padding: 3px 12px 3px 9px; color: {t.text}; }}
QToolButton#Pill:hover {{ background: {t.surface_alt}; border-color: {t.raised}; }}

/* Buttons */
QPushButton, QToolButton {{
    background: {t.surface_alt}; border: 1px solid {t.border}; border-radius: 5px;
    padding: {pad - 1}px {pad + 5}px; min-height: {s(17)}px;
}}
QPushButton:hover, QToolButton:hover {{ background: {t.raised}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {t.sel_soft}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t.text_muted}; background: {t.surface}; }}
QPushButton#Primary {{ background: {t.accent}; color: {t.accent_text}; border: 1px solid {t.accent}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {QColor(t.accent).lighter(110).name()}; }}
QPushButton#Primary:disabled {{ background: {rgba(t.accent, 0.3)}; color: {rgba(t.accent_text, 0.6)}; border-color: transparent; }}
QToolButton#Flat {{ background: transparent; border: none; padding: {pad}px; }}
QToolButton#Flat:hover {{ background: {t.raised}; }}
QToolButton#Flat:checked {{ background: {t.sel_strong}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* Segmented toggles: [By kind | By name], [S M L], [Grid | List] */
#Segmented {{ background: {t.field}; border: 1px solid {t.border}; border-radius: 5px; }}
#Segmented QToolButton {{
    background: transparent; border: none; border-radius: 4px; padding: 2px {pad + 3}px;
    color: {t.text_muted}; min-height: {s(15)}px;
}}
#Segmented QToolButton:hover {{ color: {t.text}; }}
#Segmented QToolButton:checked {{ background: {t.sel_strong}; color: {t.text}; }}

/* Inputs */
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {t.field}; border: 1px solid {t.border}; border-radius: 5px;
    padding: {pad - 1}px 8px; selection-background-color: {t.sel_strong}; selection-color: {t.text};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {rgba(t.accent, 0.7)}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({arrow}); width: 11px; height: 11px; }}
QComboBox QAbstractItemView {{
    background: {t.surface}; border: 1px solid {t.border}; padding: 4px;
    selection-background-color: {t.sel_strong}; selection-color: {t.text};
}}

/* Lists, trees, tables */
QTreeView, QTableView, QListView, QListWidget, QTreeWidget {{
    background: transparent; border: none; alternate-background-color: {t.surface_alt};
    selection-background-color: {t.sel_soft}; selection-color: {t.text}; gridline-color: transparent;
}}
QTreeView::item, QTableView::item {{ min-height: {s(row)}px; padding: 0 4px; border: none; }}
QTreeView::item:hover, QTableView::item:hover {{ background: {rgba(t.raised, 0.55)}; }}
QTreeView::item:selected, QTableView::item:selected {{ background: {t.sel_soft}; color: {t.text}; }}
#Sidebar QTreeView::item {{ border-radius: 4px; }}
#Sidebar QTreeView::item:selected {{ background: {t.sel_strong}; }}
QTreeView::branch {{ background: transparent; }}
QTreeView::branch:has-children:open {{ image: url({branch_open}); }}
QTreeView::branch:has-children:closed {{ image: url({branch_closed}); }}
QListView#Grid::item {{ border-radius: 6px; }}
QListView#Grid::item:hover {{ background: {rgba(t.raised, 0.55)}; }}
QListView#Grid::item:selected {{ background: {t.sel_soft}; }}
QListWidget::item {{ border-radius: 4px; padding: 4px; }}
QListWidget::item:selected {{ background: {t.sel_strong}; color: {t.text}; }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{
    background: transparent; color: {t.text_muted}; border: none; border-bottom: 1px solid {t.border};
    padding: {pad}px 6px; font-size: {pt(7.75)}; font-weight: 600;
}}
QHeaderView::section:hover {{ color: {t.text}; }}
QHeaderView::down-arrow, QHeaderView::up-arrow {{ width: 0; height: 0; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle {{ background: {t.raised}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {t.text_muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 6px; }}
QStatusBar {{ background: {t.bg}; color: {t.text_muted}; font-size: {pt(8.75)}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {t.text_muted}; }}
QProgressBar {{
    background: {t.field}; border: 1px solid {t.border}; border-radius: 4px; max-height: 8px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}

/* Tabs: plain text tabs, the active one on a raised chip */
QTabWidget::pane {{ border: 1px solid {t.border}; border-radius: 6px; top: -1px; background: {t.surface}; }}
QTabBar::tab {{ background: transparent; color: {t.text_muted}; padding: {pad}px 12px; margin: 0 2px 6px 0;
    border-radius: 5px; }}
QTabBar::tab:selected {{ color: {t.text}; background: {t.raised}; }}
QTabBar::tab:hover {{ color: {t.text}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px; border: 1px solid {t.border}; background: {t.field};
}}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; image: url({check}); }}
QSlider::groove:horizontal {{ height: 4px; background: {t.raised}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t.text}; width: 13px; height: 13px; margin: -5px 0; border-radius: 6px; }}
"""


def apply_theme(app: QApplication, t: Theme, scale: float, density: str) -> None:
    app.setStyle("Fusion")
    app.setPalette(build_palette(t))
    font = QFont(ui_family())
    font.setPointSizeF(BASE_POINT_SIZE * scale)
    app.setFont(font)
    app.setStyleSheet(build_stylesheet(t, scale, density))
