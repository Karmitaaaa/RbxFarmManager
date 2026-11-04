"""Tema inspirado en la web clásica de Roblox (2016-2018): barra azul, fondo gris, tarjetas blancas."""
from PySide6.QtGui import QFont, QFontDatabase

from utils.paths import app_dir

PALETTES = {
    "classic": {
        "nav": "#00A2FF", "nav_hover": "#0B8FDB", "nav_text": "#FFFFFF",
        "bg": "#E3E3E3", "card": "#FFFFFF", "card_border": "#D6D6D6",
        "text": "#191919", "muted": "#757575", "faint": "#B8B8B8",
        "input_bg": "#FFFFFF", "input_border": "#B8B8B8",
        "row_alt": "#F7F7F7", "selection": "#DCEFFC", "selection_text": "#191919",
        "avatar_bg": "#D4D4D4", "tile_text": "#191919", "sidebar": "#FFFFFF",
        "shadow": "#C6C6C6", "hover": "#F2F2F2",
    },
    "dark": {
        "nav": "#0A6EB0", "nav_hover": "#085C94", "nav_text": "#FFFFFF",
        "bg": "#191B1D", "card": "#232527", "card_border": "#393B3D",
        "text": "#F2F2F2", "muted": "#A5A7A9", "faint": "#5F6163",
        "input_bg": "#191B1D", "input_border": "#4A4C4E",
        "row_alt": "#2A2C2E", "selection": "#1B4A6B", "selection_text": "#FFFFFF",
        "avatar_bg": "#393B3D", "tile_text": "#F2F2F2", "sidebar": "#1F2123",
        "shadow": "#101112", "hover": "#2D2F31",
    },
}

ACCENTS = {
    "blue": "#00A2FF", "blue_hover": "#32B5FF",
    "green": "#02B757", "green_hover": "#3FC679",
    "red": "#E2231A", "red_hover": "#EB4F48",
    "orange": "#F68802", "gray": "#B8B8B8",
}

STATUS_COLORS = {
    "En juego": "#02B757", "Abierto": "#00A2FF", "Lanzando": "#00A2FF",
    "Reconectando": "#F68802", "Sin internet": "#F68802",
    "Desconectado": "#E2231A", "Error": "#E2231A", "Fallido": "#E2231A",
    "Cerrado": "#B8B8B8", "Detenido": "#B8B8B8",
}


def app_font() -> QFont:
    families = set(QFontDatabase.families())
    chosen = [f for f in ("Source Sans Pro", "Source Sans 3", "Segoe UI") if f in families] or ["Segoe UI"]
    font = QFont()
    font.setFamilies(chosen)
    font.setPointSizeF(10.5)
    return font


CHECK_SVG = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path d='M3.5 8.5l3 3 6-6.5' "
             "fill='none' stroke='white' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/></svg>")


def _check_icon_path() -> str:
    path = app_dir() / "check.svg"
    if not path.exists():
        path.write_text(CHECK_SVG, "utf-8")
    return path.as_posix()


def stylesheet(theme: str = "classic") -> str:
    p = dict(PALETTES.get(theme, PALETTES["classic"]))
    p.update(ACCENTS)
    p["check_svg"] = _check_icon_path()
    return """
QWidget {{ color: {text}; }}
QMainWindow, #Page, #PageInner, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {bg}; }}
QToolTip {{ background: #191919; color: #FFFFFF; border: none; padding: 4px 8px; }}

/* ---------- barra superior ---------- */
#TopBar {{ background: {nav}; }}
#TopBar QLabel {{ color: {nav_text}; }}
#Brand {{ color: {nav_text}; font-size: 17pt; font-weight: 800; padding-right: 10px; }}
#NavButton {{
    background: transparent; color: {nav_text}; border: none; border-radius: 0;
    font-size: 11.5pt; font-weight: 700; padding: 0 10px; min-height: 40px;
}}
#NavButton:hover {{ background: {nav_hover}; }}
#NavButton[active="true"] {{ background: {nav_hover}; border-bottom: 3px solid #FFFFFF; }}
#IconButton {{
    background: transparent; border: none; border-radius: 0; color: {nav_text}; padding: 0; min-height: 46px;
}}
#IconButton:hover {{ background: {nav_hover}; }}
#TopSearch {{
    background: #FFFFFF; color: #191919; border: none; border-radius: 3px;
    padding: 5px 8px; min-height: 22px; font-size: 10.5pt;
}}
#TopStat {{ color: {nav_text}; font-weight: 700; padding: 0 6px; }}
#Badge {{
    background: {red}; color: #FFFFFF; border-radius: 8px; font-size: 8pt; font-weight: 700;
    min-width: 16px; max-height: 16px; padding: 0 4px;
}}

/* ---------- barra lateral ---------- */
#Sidebar {{ background: {sidebar}; border-right: 1px solid {card_border}; }}
#Sidebar QLabel {{ background: transparent; }}
#SideButton {{
    background: transparent; border: none; border-left: 4px solid transparent; border-radius: 0;
    padding: 0; min-height: 38px; font-size: 11pt; font-weight: 400; text-align: left;
}}
#SideButton:hover {{ background: {hover}; }}
#SideButton[active="true"] {{ background: {selection}; border-left: 4px solid {blue}; }}
#SideSection {{ color: {muted}; font-size: 8.5pt; font-weight: 700; padding: 16px 18px 6px 18px; }}
#Sidebar #SideBadge {{
    background: {blue}; color: #FFFFFF; border-radius: 9px; padding: 1px 7px; font-size: 8pt; font-weight: 700;
}}

/* ---------- textos ---------- */
#Hello {{ font-size: 28pt; font-weight: 300; }}
#HelloSub {{ color: {muted}; font-size: 11pt; }}
#PageTitle {{ font-size: 21pt; font-weight: 300; }}
#SectionTitle {{ font-size: 15pt; font-weight: 400; }}
#Muted {{ color: {muted}; }}
#CardTitle {{ font-size: 12pt; font-weight: 600; }}
#BigCounter {{ font-size: 22pt; font-weight: 300; }}

/* ---------- tarjetas ---------- */
#Card {{
    background: {card}; border: 1px solid {card_border}; border-bottom: 2px solid {shadow}; border-radius: 5px;
}}
#Card QLabel, #Card QCheckBox, #Card QRadioButton {{ background: transparent; }}
#GameCard {{
    background: {card}; border: 1px solid {card_border}; border-bottom: 2px solid {shadow}; border-radius: 6px;
}}
#GameCard:hover {{ border-color: {blue}; }}
#GameCard QLabel {{ background: transparent; }}
#AddCard {{ background: transparent; border: 2px dashed {faint}; border-radius: 6px; }}
#AddCard:hover {{ border-color: {blue}; background: {card}; }}

/* ---------- enlaces "Ver todo" ---------- */
#Link {{ background: transparent; border: none; color: {blue}; font-size: 11pt; padding: 2px 4px; }}
#Link:hover {{ text-decoration: underline; }}
#Link:disabled {{ color: {faint}; }}

/* ---------- botones ---------- */
QPushButton {{
    background: {card}; color: {text}; border: 1px solid {input_border}; border-radius: 3px;
    padding: 5px 14px; font-weight: 600; min-height: 20px;
}}
QPushButton:hover {{ border-color: {text}; }}
QPushButton:disabled {{ color: {faint}; border-color: {card_border}; }}
#PrimaryButton {{ background: {green}; border: 1px solid {green}; color: #FFFFFF; }}
#PrimaryButton:hover {{ background: {green_hover}; border-color: {green_hover}; }}
#SecondaryButton {{ background: {blue}; border: 1px solid {blue}; color: #FFFFFF; }}
#SecondaryButton:hover {{ background: {blue_hover}; border-color: {blue_hover}; }}
#DangerButton {{ background: {red}; border: 1px solid {red}; color: #FFFFFF; }}
#DangerButton:hover {{ background: {red_hover}; border-color: {red_hover}; }}
#PrimaryButton:disabled, #SecondaryButton:disabled, #DangerButton:disabled {{
    background: {faint}; border-color: {faint}; color: #FFFFFF;
}}

/* ---------- entradas ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {input_bg}; color: {text}; border: 1px solid {input_border}; border-radius: 3px;
    padding: 4px 6px; selection-background-color: {blue}; selection-color: #FFFFFF;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {blue};
}}
QComboBox QAbstractItemView {{
    background: {card}; color: {text}; border: 1px solid {input_border};
    selection-background-color: {selection}; selection-color: {selection_text};
}}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QCheckBox::indicator, QTableWidget::indicator, QListWidget::indicator {{
    width: 15px; height: 15px; border: 1px solid {input_border}; border-radius: 3px; background: {input_bg};
}}
QCheckBox::indicator:hover, QTableWidget::indicator:hover, QListWidget::indicator:hover {{ border-color: {blue}; }}
QCheckBox::indicator:checked, QTableWidget::indicator:checked, QListWidget::indicator:checked {{
    background: {blue}; border-color: {blue}; image: url("{check_svg}");
}}
QRadioButton::indicator {{
    width: 15px; height: 15px; border: 1px solid {input_border}; border-radius: 8px; background: {input_bg};
}}
QRadioButton::indicator:checked {{ background: {blue}; border-color: {blue}; }}

/* ---------- tablas y listas ---------- */
QTableWidget, QListWidget {{
    background: {card}; alternate-background-color: {row_alt}; border: none;
    gridline-color: transparent; selection-background-color: {selection}; selection-color: {selection_text};
}}
QListWidget::item {{ padding: 6px 8px; }}
QHeaderView::section {{
    background: {card}; color: {muted}; border: none; border-bottom: 1px solid {card_border};
    padding: 6px 8px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {card}; border: none; }}

/* ---------- barras de scroll ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {faint}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {faint}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- panel de notificaciones (como el "Chat" clásico) ---------- */
#NotifyHeader {{
    background: {blue}; color: #FFFFFF; border: none; border-radius: 0;
    font-weight: 700; text-align: left; padding: 6px 12px;
}}
#NotifyHeader:hover {{ background: {blue_hover}; }}
#NotifyBody {{ background: {card}; border: 1px solid {card_border}; border-bottom: none; }}

QMenu {{ background: {card}; color: {text}; border: 1px solid {card_border}; }}
QMenu::item {{ padding: 6px 22px; }}
QMenu::item:selected {{ background: {selection}; color: {selection_text}; }}
QDialog {{ background: {bg}; }}
""".format(**p)
