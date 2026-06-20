"""Modern dark theme (QSS) for the desktop app."""

from pathlib import Path

ACCENT = "#7c5cff"
ACCENT_HOVER = "#8f73ff"
BG = "#15151c"
PANEL = "#1e1e28"
CARD = "#262633"
BORDER = "#33334a"
TEXT = "#e8e8f0"
MUTED = "#9a9ab0"

# absolute path to the checkmark asset (Qt QSS needs forward-slashed absolute url)
CHECK_ICON = (Path(__file__).resolve().parent / "assets" / "check.png").as_posix()

QSS = f"""
* {{
    font-family: -apple-system, "SF Pro Text", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QWidget {{ background: {BG}; }}

/* Labels must be transparent, otherwise the darker window BG shows as a rectangle
   behind text that sits on lighter cards/panels. */
QLabel {{ background: transparent; }}
QLabel#H1 {{ font-size: 18px; font-weight: 700; }}
QLabel#H2 {{ font-size: 14px; font-weight: 600; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Status {{ color: {ACCENT}; font-weight: 600; }}
QCheckBox {{ background: transparent; }}

/* Cards / panels */
QFrame#Card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}

/* Buttons */
QPushButton {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 8px 14px;
    color: {TEXT};
}}
QPushButton:hover {{ background: #2f2f40; }}
QPushButton:disabled {{ color: #5a5a70; background: #20202a; }}

QPushButton#Primary {{
    background: {ACCENT};
    border: none;
    font-weight: 600;
    color: white;
}}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Primary:disabled {{ background: #3a3550; color: #8a86a0; }}

QPushButton#Ghost {{ background: transparent; border: 1px solid {BORDER}; }}
QPushButton#Ghost:hover {{ background: {CARD}; }}

QPushButton#Mini {{ padding: 4px 10px; font-size: 12px; border-radius: 7px; }}

/* Text fields */
QPlainTextEdit, QLineEdit {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px;
    selection-background-color: {ACCENT};
}}
QPlainTextEdit:focus, QLineEdit:focus {{ border: 1px solid {ACCENT}; }}

/* Spin boxes */
QSpinBox, QDoubleSpinBox {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 5px 8px;
    min-width: 64px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: #5a5a70; }}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 18px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid {MUTED}; width: 0; height: 0; margin-bottom: 1px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {MUTED}; width: 0; height: 0; margin-top: 1px;
}}
QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {{ border-bottom-color: {ACCENT}; }}
QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {{ border-top-color: {ACCENT}; }}

/* Check box */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 20px; height: 20px;
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {CARD};
}}
QCheckBox::indicator:hover {{ border: 1px solid {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    image: url("{CHECK_ICON}");
}}

/* Combo */
QComboBox {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 6px 10px;
}}
QComboBox:hover {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ width: 10px; height: 10px; }}
/* Popup: keep corners square so the rounded border has no leftover square bg.
   Style the inner view, not the popup window, to avoid the corner artifact. */
QComboBox QAbstractItemView {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 4px;
    selection-background-color: {ACCENT};
    selection-color: white;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    min-height: 26px;
    padding: 4px 8px;
    border-radius: 6px;
}}

/* Job list */
QListWidget {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 6px;
    outline: none;
}}
QListWidget::item {{
    background: {CARD};
    border-radius: 9px;
    padding: 10px;
    margin: 3px;
}}
QListWidget::item:selected {{
    background: {ACCENT};
    color: white;
}}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent;
    padding: 9px 18px;
    margin-right: 4px;
    border-radius: 9px;
    color: {MUTED};
}}
QTabBar::tab:selected {{ background: {PANEL}; color: {TEXT}; font-weight: 600; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}

/* Splitter handle */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 10px; }}

/* Video surface */
QVideoWidget {{ background: #000; }}

/* Tooltips */
QToolTip {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
}}
"""
