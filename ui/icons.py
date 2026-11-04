"""Iconos vectoriales con la fuente de iconos de Windows (Segoe Fluent Icons / Segoe MDL2 Assets)."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QLabel


class G:
    MENU = ""
    HOME = ""
    GAME = ""
    PEOPLE = ""
    PERSON = ""
    MONITOR = ""
    CLOCK = ""
    MOUSE = ""
    RECORD = ""
    SETTINGS = ""
    DOC = ""
    PLAY = ""
    STOP = ""
    ADD = ""
    EDIT = ""
    DELETE = ""
    MORE = ""
    BELL = ""
    REFRESH = ""
    DOWNLOAD = ""
    UPLOAD = ""
    COPY = ""
    RENAME = ""
    CHECK = ""
    CLOSE = ""
    INFO = ""
    FOLDER = ""
    FLASH = ""
    TIMER = ""
    LOCK = ""
    SYNC = ""
    LIST = ""
    SEARCH = ""


_family: str | None = None


def icon_font(px: int) -> QFont:
    global _family
    if _family is None:
        families = set(QFontDatabase.families())
        _family = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families),
                       "Segoe MDL2 Assets")
    font = QFont(_family)
    font.setPixelSize(px)
    return font


def glyph_pixmap(glyph: str, color: str, px: int, dpr: float = 2.0) -> QPixmap:
    size = int(px * dpr)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setPen(QColor(color))
    p.setFont(icon_font(size))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, glyph)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def glyph_icon(glyph: str, color: str = "#757575", px: int = 16) -> QIcon:
    icon = QIcon()
    icon.addPixmap(glyph_pixmap(glyph, color, px), QIcon.Normal)
    icon.addPixmap(glyph_pixmap(glyph, "#C8C8C8", px), QIcon.Disabled)
    return icon


class GlyphLabel(QLabel):
    """Icono como texto: hereda el color del tema (cambia solo con el tema claro/oscuro)."""

    def __init__(self, glyph: str, px: int = 16, color: str | None = None):
        super().__init__(glyph)
        self.setFont(icon_font(px))
        self.setAlignment(Qt.AlignCenter)
        self.setFixedWidth(px + 8)
        if color:
            self.setStyleSheet(f"color: {color}; background: transparent;")
