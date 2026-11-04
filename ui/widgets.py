"""Componentes visuales reutilizables al estilo de la web clásica de Roblox."""
import hashlib
import time

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ui import theme
from ui.icons import G, glyph_icon, icon_font

current_theme = {"name": "classic"}

AVATAR_COLORS = ["#E2231A", "#00A2FF", "#02B757", "#F68802", "#8E44AD", "#D81B60",
                 "#3949AB", "#6D4C41", "#546E7A", "#00897B", "#C0CA33", "#5E35B1"]


def pal(key: str) -> str:
    return theme.PALETTES[current_theme["name"]][key]


def color_for(text: str) -> QColor:
    digest = hashlib.md5(text.encode("utf-8")).digest()
    return QColor(AVATAR_COLORS[digest[0] % len(AVATAR_COLORS)])


# --------------------------------------------------------------------------- estructura
def make_card(margins: int = 16, spacing: int = 10) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return frame, lay


def link_button(text: str, slot=None) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Link")
    btn.setCursor(Qt.PointingHandCursor)
    if slot:
        btn.clicked.connect(slot)
    return btn


def styled_button(text: str, kind: str = "", slot=None, big: bool = False, icon: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    names = {"primary": "PrimaryButton", "secondary": "SecondaryButton", "danger": "DangerButton"}
    if kind in names:
        btn.setObjectName(names[kind])
    if icon:
        btn.setIcon(glyph_icon(icon, "#FFFFFF" if kind in names else "#757575", 18 if big else 14))
        btn.setIconSize(QSize(18, 18) if big else QSize(14, 14))
    if big:
        btn.setProperty("class", "big")
        btn.setStyleSheet("font-size: 12.5pt; padding: 8px 26px;")
    btn.setCursor(Qt.PointingHandCursor)
    if slot:
        btn.clicked.connect(slot)
    return btn


def clear_layout(layout, keep: int = 0) -> None:
    """Vacía un layout ocultando sus widgets al momento (deleteLater solo los borra más tarde)."""
    while layout.count() > keep:
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
            item.layout().deleteLater()


def muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


class SectionHeader(QWidget):
    """Título de sección con enlaces a la derecha, como «Friends (81) ........ See All»."""

    def __init__(self, title: str):
        super().__init__()
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 14, 0, 4)
        self.title = QLabel(title)
        self.title.setObjectName("SectionTitle")
        self._lay.addWidget(self.title)
        self._lay.addStretch(1)

    def set_title(self, text: str) -> None:
        self.title.setText(text)

    def add_link(self, text: str, slot) -> QPushButton:
        btn = link_button(text, slot)
        self._lay.addWidget(btn)
        return btn

    def add_widget(self, widget: QWidget) -> None:
        self._lay.addWidget(widget)


class Page(QScrollArea):
    """Página con scroll y contenido centrado de ancho máximo fijo (como la web)."""

    def __init__(self, max_width: int = 1040):
        super().__init__()
        self.setObjectName("Page")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        outer = QWidget()
        outer.setObjectName("PageInner")
        h = QHBoxLayout(outer)
        h.setContentsMargins(24, 12, 24, 60)
        inner = QWidget()
        inner.setObjectName("PageInner")
        inner.setMaximumWidth(max_width)
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(6)
        h.addStretch(1)
        h.addWidget(inner, 100)
        h.addStretch(1)
        self.setWidget(outer)


# --------------------------------------------------------------------------- avatares
class Avatar(QWidget):
    """Círculo gris con una "cabeza" de bloque de color e iniciales, y burbuja de estado."""

    def __init__(self, text: str = "?", seed: str = "", size: int = 64):
        super().__init__()
        self.text, self.seed = text, seed or text
        self.selected = False
        self.badge: QColor | None = None
        self.photo: QPixmap | None = None
        self.setFixedSize(size, size)

    def set_photo(self, pixmap: QPixmap | None) -> None:
        self.photo = pixmap if pixmap is not None and not pixmap.isNull() else None
        self.update()

    def sizeHint(self) -> QSize:
        return self.size()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.width()
        ring = 3
        circle = QRectF(ring, ring, s - 2 * ring, s - 2 * ring)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal("avatar_bg")))
        p.drawEllipse(circle)

        if self.photo is not None:
            # Foto del avatar recortada en círculo sobre el fondo gris (como en la web clásica)
            clip = QPainterPath()
            clip.addEllipse(circle)
            p.save()
            p.setClipPath(clip)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawPixmap(circle.toRect(), self.photo)
            p.restore()
        else:
            head = circle.adjusted(s * 0.22, s * 0.2, -s * 0.22, -s * 0.24)
            p.setBrush(color_for(self.seed))
            p.drawRoundedRect(head, s * 0.1, s * 0.1)
            p.setPen(QColor("#FFFFFF"))
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(max(10, int(s * 0.22)))
            p.setFont(font)
            p.drawText(head, Qt.AlignCenter, self.text)

        if self.selected:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(theme.ACCENTS["blue"]), ring))
            p.drawEllipse(QRectF(ring / 2, ring / 2, s - ring, s - ring))
        if self.badge is not None:
            d = s * 0.3
            rect = QRectF(s - d - 1, s - d - 1, d, d)
            p.setPen(QPen(QColor(pal("card")), 2))
            p.setBrush(self.badge)
            p.drawEllipse(rect)


class AvatarTile(QWidget):
    toggled = Signal(str, bool)
    double_clicked = Signal(str)

    def __init__(self, key: str, name: str, initials: str, size: int = 72):
        super().__init__()
        self.key = key
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(size + 22)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.avatar = Avatar(initials, name, size)
        lay.addWidget(self.avatar, 0, Qt.AlignHCenter)
        self.label = QLabel(name)
        self.label.setAlignment(Qt.AlignHCenter)
        self.label.setStyleSheet("font-size: 9pt;")
        metrics = self.label.fontMetrics()
        self.label.setText(metrics.elidedText(name, Qt.ElideRight, size + 18))
        self.label.setToolTip(name)
        lay.addWidget(self.label)

    def set_selected(self, selected: bool) -> None:
        self.avatar.selected = selected
        self.avatar.update()

    def set_badge(self, color: str | None) -> None:
        self.avatar.badge = QColor(color) if color else None
        self.avatar.update()

    def set_photo(self, pixmap: QPixmap | None) -> None:
        self.avatar.set_photo(pixmap)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.set_selected(not self.avatar.selected)
            self.toggled.emit(self.key, self.avatar.selected)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.key)


class HStrip(QScrollArea):
    """Fila horizontal con scroll (para avatares y juegos)."""

    def __init__(self, height: int):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(height)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget "
                           "{ background: transparent; }")
        self.viewport().setAutoFillBackground(False)
        inner = QWidget()
        inner.setAutoFillBackground(False)
        self.row = QHBoxLayout(inner)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(12)
        self.row.addStretch(1)
        self.setWidget(inner)

    def clear(self) -> None:
        clear_layout(self.row, keep=1)

    def add(self, widget: QWidget) -> None:
        self.row.insertWidget(self.row.count() - 1, widget)


class FlowLayout(QLayout):
    """Coloca los elementos en filas que saltan de línea según el ancho (rejilla de juegos)."""

    def __init__(self, spacing: int = 14):
        super().__init__()
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect: QRect, apply: bool) -> int:
        x, y, row_h = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and row_h > 0:
                x, y = rect.x(), y + row_h + self._spacing
                row_h = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            row_h = max(row_h, hint.height())
        return y + row_h - rect.y()


def time_ago(stamp: float) -> str:
    if not stamp:
        return "Aún sin jugar"
    secs = max(0, time.time() - stamp)
    if secs < 90:
        return "Jugado hace un momento"
    if secs < 3600:
        return f"Jugado hace {secs / 60:.0f} min"
    if secs < 86400:
        return f"Jugado hace {secs / 3600:.0f} h"
    days = secs / 86400
    return f"Jugado hace {days:.0f} día{'s' if days >= 1.5 else ''}"


class GameCover(QWidget):
    """Portada del juego: su icono real de Roblox o, si no hay, un degradado con el mando."""

    def __init__(self, seed: str, width: int, height: int):
        super().__init__()
        self.seed = seed or "juego"
        self.photo: QPixmap | None = None
        self.setFixedSize(width, height)

    def set_photo(self, pixmap: QPixmap | None) -> None:
        self.photo = pixmap if pixmap is not None and not pixmap.isNull() else None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        p.setClipPath(path)
        if self.photo is not None:
            scaled = self.photo.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            p.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
            return
        grad = QLinearGradient(0, 0, rect.width(), rect.height())
        grad.setColorAt(0, color_for(self.seed).lighter(130))
        grad.setColorAt(1, color_for(self.seed[::-1]).darker(110))
        p.fillPath(path, QBrush(grad))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 45))
        p.drawEllipse(QRectF(-rect.width() * 0.2, rect.height() * 0.62, rect.width() * 1.4, rect.height() * 0.8))
        p.setPen(QColor(255, 255, 255, 230))
        p.setFont(icon_font(int(min(rect.width(), rect.height()) * 0.34)))
        p.drawText(rect, Qt.AlignCenter, G.GAME)


class GameCard(QFrame):
    """Tarjeta de perfil de juego al estilo de las miniaturas de juegos de la web clásica."""

    play_clicked = Signal(str)
    edit_clicked = Signal(str)
    menu_clicked = Signal(str)

    def __init__(self, game, subtitle: str, width: int = 190):
        super().__init__()
        self.game_id = game.id
        self.setObjectName("GameCard")
        self.setFixedWidth(width)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Doble clic para editar el perfil")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 10)
        lay.setSpacing(4)
        self.cover = GameCover(game.name, width - 2, int((width - 2) * 0.8))
        lay.addWidget(self.cover, 0, Qt.AlignHCenter)

        text = QVBoxLayout()
        text.setContentsMargins(10, 4, 10, 0)
        text.setSpacing(2)
        name = QLabel()
        name.setObjectName("CardTitle")
        name.setText(name.fontMetrics().elidedText(game.name, Qt.ElideRight, width - 24))
        name.setToolTip(game.name)
        text.addWidget(name)
        sub = muted_label(subtitle)
        sub.setWordWrap(False)
        sub.setStyleSheet("font-size: 9pt;")
        sub.setText(sub.fontMetrics().elidedText(subtitle, Qt.ElideRight, width - 24))
        sub.setToolTip(subtitle)
        text.addWidget(sub)
        self.status = QLabel()
        self.status.setStyleSheet("font-size: 9pt; font-weight: 600;")
        text.addWidget(self.status)
        lay.addLayout(text)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(10, 4, 10, 0)
        buttons.setSpacing(6)
        play = styled_button("Jugar", "primary", lambda: self.play_clicked.emit(self.game_id), icon=G.PLAY)
        buttons.addWidget(play, 1)
        more = styled_button("", "", lambda: self.menu_clicked.emit(self.game_id), icon=G.MORE)
        more.setFixedWidth(34)
        more.setToolTip("Más opciones")
        buttons.addWidget(more)
        lay.addLayout(buttons)
        self.last_played = game.last_played
        self.set_status(0, 0)

    def set_photo(self, pixmap: QPixmap | None) -> None:
        self.cover.set_photo(pixmap)

    def set_status(self, in_game: int, active: int) -> None:
        if active:
            self.status.setText(f"● {in_game} en juego · {active} abiertas")
            self.status.setStyleSheet(f"font-size: 9pt; font-weight: 600; color: {theme.ACCENTS['green']};")
        else:
            self.status.setText(time_ago(self.last_played))
            self.status.setStyleSheet(f"font-size: 9pt; color: {pal('muted')};")

    def mouseDoubleClickEvent(self, event):
        self.edit_clicked.emit(self.game_id)


class AddCard(QFrame):
    """Tarjeta con borde discontinuo para crear algo nuevo."""

    clicked = Signal()

    def __init__(self, text: str, width: int = 190, height: int = 300):
        super().__init__()
        self.setObjectName("AddCard")
        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        circle = QLabel(G.ADD)
        circle.setFont(icon_font(22))
        circle.setAlignment(Qt.AlignCenter)
        circle.setFixedSize(56, 56)
        circle.setStyleSheet(f"background: {theme.ACCENTS['blue']}; color: #FFFFFF; border-radius: 28px;")
        lay.addWidget(circle, 0, Qt.AlignHCenter)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {theme.ACCENTS['blue']}; font-weight: 600; background: transparent;")
        lay.addWidget(label)
        lay.addStretch(1)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class IconCircle(QLabel):
    def __init__(self, glyph: str, size: int = 44, color: str | None = None):
        super().__init__(glyph)
        self.setFont(icon_font(int(size * 0.45)))
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(size, size)
        self.setStyleSheet(f"background: {color or theme.ACCENTS['blue']}; color: #FFFFFF; "
                           f"border-radius: {size // 2}px;")


class PageHeader(QWidget):
    """Cabecera de cada sección: icono, título y una frase que explica para qué sirve."""

    def __init__(self, glyph: str, title: str, subtitle: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 6)
        lay.setSpacing(14)
        lay.addWidget(IconCircle(glyph, 48))
        text = QVBoxLayout()
        text.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        text.addWidget(title_label)
        sub = muted_label(subtitle)
        sub.setStyleSheet("font-size: 10.5pt;")
        text.addWidget(sub)
        lay.addLayout(text, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)

    def add_action(self, button: QPushButton) -> QPushButton:
        self.actions.addWidget(button)
        return button


class EmptyState(QFrame):
    """Estado vacío amable: icono grande, explicación y un botón que dice qué hacer."""

    def __init__(self, glyph: str, title: str, text: str, button_text: str = "", slot=None,
                 button_glyph: str | None = None):
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 28, 24, 28)
        lay.setSpacing(8)
        lay.addWidget(IconCircle(glyph, 64, theme.ACCENTS["gray"]), 0, Qt.AlignHCenter)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        title_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(title_label)
        body = muted_label(text)
        body.setAlignment(Qt.AlignCenter)
        lay.addWidget(body)
        if button_text:
            btn = styled_button(button_text, "secondary", slot, icon=button_glyph)
            lay.addWidget(btn, 0, Qt.AlignHCenter)


class StatusPill(QLabel):
    def __init__(self, status: str = ""):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(20)
        self.setMinimumWidth(96)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        color = theme.STATUS_COLORS.get(status, theme.ACCENTS["gray"])
        self.setText(status)
        self.setStyleSheet(f"background:{color}; color:#FFFFFF; border-radius:9px; padding:1px 10px;"
                           f"font-weight:700; font-size:9pt;")


# --------------------------------------------------------------------------- hotkey
_QT_KEY_NAMES = {
    Qt.Key.Key_Space: "SPACE", Qt.Key.Key_Insert: "INSERT", Qt.Key.Key_Delete: "DELETE",
    Qt.Key.Key_Home: "HOME", Qt.Key.Key_End: "END", Qt.Key.Key_PageUp: "PAGEUP",
    Qt.Key.Key_PageDown: "PAGEDOWN", Qt.Key.Key_Pause: "PAUSE", Qt.Key.Key_ScrollLock: "SCROLLLOCK",
    Qt.Key.Key_Up: "UP", Qt.Key.Key_Down: "DOWN", Qt.Key.Key_Left: "LEFT", Qt.Key.Key_Right: "RIGHT",
    Qt.Key.Key_Tab: "TAB", Qt.Key.Key_Return: "ENTER", Qt.Key.Key_Enter: "ENTER",
}


def _qt_key_name(key: int) -> str | None:
    f1 = Qt.Key.Key_F1.value
    if f1 <= key <= Qt.Key.Key_F24.value:
        return f"F{key - f1 + 1}"
    if Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value or Qt.Key.Key_0.value <= key <= Qt.Key.Key_9.value:
        return chr(key)
    for qk, name in _QT_KEY_NAMES.items():
        if qk.value == key:
            return name
    return None


class HotkeyEdit(QLineEdit):
    """Campo que captura una combinación: haz clic y pulsa la tecla. Retroceso la borra."""

    hotkey_changed = Signal(str)

    def __init__(self, value: str = ""):
        super().__init__(value)
        self.setReadOnly(True)
        self.setPlaceholderText("Pulsa una tecla…")
        self.setToolTip("Haz clic y pulsa la combinación (p. ej. F6 o Ctrl+F7). Retroceso para borrar.")
        self.setMaximumWidth(150)

    def keyPressEvent(self, event):
        key = int(event.key())
        if key == Qt.Key.Key_Backspace.value:
            self.setText("")
            self.hotkey_changed.emit("")
            return
        name = _qt_key_name(key)
        if not name:
            return
        mods = event.modifiers()
        parts = []
        if mods & Qt.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.AltModifier:
            parts.append("Alt")
        if mods & Qt.ShiftModifier:
            parts.append("Shift")
        text = "+".join(parts + [name])
        self.setText(text)
        self.hotkey_changed.emit(text)


# --------------------------------------------------------------------------- notificaciones
class NotificationsDock(QWidget):
    """Pestaña azul plegable abajo a la derecha (como el «Chat» de la web clásica)."""

    LEVEL_ICONS = {"error": "⛔", "warning": "⚠", "info": "ℹ"}

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.unread = 0
        self.expanded = False
        self.setFixedWidth(300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.list = QListWidget()
        self.list.setObjectName("NotifyBody")
        self.list.setWordWrap(True)
        self.list.setFixedHeight(260)
        self.list.hide()
        self.header = QPushButton()
        self.header.setObjectName("NotifyHeader")
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.clicked.connect(self.toggle)
        lay.addWidget(self.list)
        lay.addWidget(self.header)
        self._refresh_header()
        parent.installEventFilter(self)
        self._reposition()

    def add(self, level: str, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        item = QListWidgetItem(f"{self.LEVEL_ICONS.get(level, 'ℹ')}  {stamp}  {text}")
        if level == "error":
            item.setForeground(QColor(theme.ACCENTS["red"]))
        elif level == "warning":
            item.setForeground(QColor(theme.ACCENTS["orange"]))
        self.list.insertItem(0, item)
        while self.list.count() > 100:
            self.list.takeItem(self.list.count() - 1)
        if not self.expanded:
            self.unread += 1
        self._refresh_header()

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self.list.setVisible(self.expanded)
        if self.expanded:
            self.unread = 0
        self._refresh_header()
        self.adjustSize()
        self._reposition()

    def _refresh_header(self) -> None:
        arrow = "▾" if self.expanded else "▴"
        badge = f"   ({self.unread} nuevas)" if self.unread else ""
        self.header.setText(f"Notificaciones{badge}   {arrow}")

    def _reposition(self) -> None:
        parent = self.parentWidget()
        self.adjustSize()
        self.move(parent.width() - self.width() - 16, parent.height() - self.height())
        self.raise_()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self._reposition()
        return False


# --------------------------------------------------------------------------- icono
def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENTS["blue"]))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        p.setBrush(QColor(theme.ACCENTS["green"]))
        p.drawEllipse(QRectF(size * 0.62, size * 0.62, size * 0.3, size * 0.3))
        p.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(int(size * 0.5))
        p.setFont(font)
        p.drawText(QRectF(0, -size * 0.04, size * 0.92, size), Qt.AlignCenter, "RF")
        p.end()
        icon.addPixmap(pm)
    return icon


def spacer_v(height: int) -> QWidget:
    w = QWidget()
    w.setFixedHeight(height)
    w.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    return w
