"""Tarjeta de una instancia: vista previa de su ventana, estado, consumo y acciones."""
import time

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from core.window_layout import SIZE_PRESETS
from ui import theme
from ui.context import AppContext
from ui.icons import G, glyph_icon, icon_font
from ui.widgets import Avatar, StatusPill, muted_label, styled_button
from utils import winapi
from utils.i18n import t


def format_uptime(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return t("{0} min", minutes)
    return t("{0} h {1} min", minutes // 60, minutes % 60)


class PreviewView(QWidget):
    """Imagen de la ventana. Sin imagen muestra un aviso; minimizada, la última imagen atenuada."""

    clicked = Signal()

    def __init__(self, width: int, height: int):
        super().__init__()
        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(t("Clic para traer la ventana al frente"))
        self.image: QImage | None = None
        self.minimized = False

    def set_image(self, image: QImage) -> None:
        self.image = image
        self.update()

    def set_minimized(self, minimized: bool) -> None:
        if minimized != self.minimized:
            self.minimized = minimized
            self.update()

    def _caption(self, painter: QPainter, rect: QRectF, text: str) -> None:
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(rect.adjusted(0, 34, 0, 0), Qt.AlignCenter, text)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 5, 5)
        p.setClipPath(path)
        p.fillRect(rect, QColor("#191B1D"))
        if self.image is not None:
            scaled = self.image.size().scaled(self.size(), Qt.KeepAspectRatio)
            target = QRectF((rect.width() - scaled.width()) / 2, (rect.height() - scaled.height()) / 2,
                            scaled.width(), scaled.height())
            p.drawImage(target, self.image)
        if self.image is None or self.minimized:
            if self.image is not None:
                p.fillRect(rect, QColor(0, 0, 0, 150))
            p.setPen(QColor(255, 255, 255, 200))
            p.setFont(icon_font(26))
            p.drawText(rect.adjusted(0, -16, 0, 0), Qt.AlignCenter, G.MONITOR)
            self._caption(p, rect, t("Minimizada") if self.minimized else t("Esperando la ventana…"))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class InstanceCard(QFrame):
    WIDTH = 296

    def __init__(self, ctx: AppContext, inst):
        super().__init__()
        self.ctx, self.inst_id = ctx, inst.id
        self.setObjectName("GameCard")
        self.setFixedWidth(self.WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 10)
        lay.setSpacing(6)

        width = self.WIDTH - 2
        self.preview = PreviewView(width, int(width * 9 / 16))
        self.preview.clicked.connect(lambda: ctx.manager.focus(self.inst_id))
        lay.addWidget(self.preview)
        self.pill = StatusPill(inst.status)
        self.pill.setMinimumWidth(0)
        self.pill.setParent(self.preview)
        self.pill.move(8, 8)

        head = QHBoxLayout()
        head.setContentsMargins(10, 2, 10, 0)
        head.setSpacing(8)
        self.avatar = Avatar(inst.account.initials, inst.account.alias, 36)
        self.avatar.set_photo(ctx.avatars.pixmap(inst.account))
        head.addWidget(self.avatar)
        names = QVBoxLayout()
        names.setSpacing(0)
        self.name = QLabel()
        self.name.setObjectName("CardTitle")
        self.game = muted_label("")
        self.game.setWordWrap(False)
        self.game.setStyleSheet("font-size: 9pt;")
        names.addWidget(self.name)
        names.addWidget(self.game)
        head.addLayout(names, 1)
        lay.addLayout(head)

        chips = QHBoxLayout()
        chips.setContentsMargins(10, 0, 10, 0)
        chips.setSpacing(4)
        self.usage = QLabel()
        self.usage.setObjectName("Chip")
        chips.addWidget(self.usage)
        chips.addStretch(1)
        self.afk = self._toggle("Anti-AFK", "anti_afk", t("Anti-AFK en esta instancia"))
        self.reconnect = self._toggle(t("Reconexión"), "auto_reconnect", t("Volver a entrar si se cae"))
        chips.addWidget(self.afk)
        chips.addWidget(self.reconnect)
        lay.addLayout(chips)

        self.detail = muted_label("")
        self.detail.setWordWrap(False)
        self.detail.setContentsMargins(10, 0, 10, 0)
        self.detail.setStyleSheet("font-size: 9pt;")
        lay.addWidget(self.detail)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(10, 0, 10, 0)
        buttons.setSpacing(6)
        buttons.addWidget(styled_button(t("Mostrar"), "", lambda: ctx.manager.focus(self.inst_id)), 1)
        buttons.addWidget(styled_button(t("Minimizar"), "", lambda: ctx.manager.minimize(self.inst_id)), 1)
        run = styled_button("", "secondary", lambda: ctx.navigate.emit(f"run:{self.inst_id}"), icon=G.PLAY)
        run.setToolTip(t("Macro o autoclicker en esta instancia"))
        run.setFixedWidth(36)
        buttons.addWidget(run)
        more = styled_button("", "", self._menu, icon=G.MORE)
        more.setToolTip(t("Más opciones"))
        more.setFixedWidth(36)
        buttons.addWidget(more)
        lay.addLayout(buttons)
        self.refresh(inst)

    def _toggle(self, text: str, attr: str, tip: str) -> QPushButton:
        chip = QPushButton(text)
        chip.setObjectName("ChipToggle")
        chip.setCheckable(True)
        chip.setCursor(Qt.PointingHandCursor)
        chip.setToolTip(tip)

        def changed(on: bool) -> None:
            inst = self.ctx.manager.get(self.inst_id)
            if inst:
                setattr(inst, attr, on)
                if attr == "anti_afk":
                    inst.next_afk_at = 0.0

        chip.toggled.connect(changed)
        return chip

    def _menu(self) -> None:
        manager, inst_id = self.ctx.manager, self.inst_id
        menu = QMenu(self)
        self._size_menu(menu)
        by_hand = self.ctx.cfg.get("windows.order", "list") == "list"
        for text, delta in ((t("Mover antes"), -1), (t("Mover después"), 1)):
            action = menu.addAction(text, lambda _=False, d=delta: manager.move_in_list(inst_id, d))
            action.setEnabled(by_hand)
        menu.addSeparator()
        menu.addAction(glyph_icon(G.REFRESH), t("Reiniciar"), lambda: manager.restart(inst_id))
        menu.addAction(glyph_icon(G.STOP, theme.ACCENTS["red"]), t("Cerrar instancia"), lambda: manager.close(inst_id))
        menu.addSeparator()
        menu.addAction(glyph_icon(G.CLOSE), t("Quitar de la lista"), lambda: manager.remove(inst_id))
        menu.exec(QCursor.pos())

    def _size_menu(self, menu: QMenu) -> None:
        manager, inst_id = self.ctx.manager, self.inst_id
        sizes = menu.addMenu(glyph_icon(G.MONITOR), t("Tamaño de la ventana"))
        inst = manager.get(inst_id)
        sizes.setEnabled(bool(inst and winapi.is_window(inst.hwnd)))
        for width, height in SIZE_PRESETS:
            sizes.addAction(f"{width} × {height}",
                            lambda _=False, w=width, h=height: manager.resize_window(inst_id, w, h))
        width, height = int(self.ctx.cfg.get("windows.width", 800)), int(self.ctx.cfg.get("windows.height", 600))
        sizes.addAction(t("Personalizado ({0} × {1})", width, height),
                        lambda: manager.resize_window(inst_id, width, height))
        sizes.addSeparator()
        sizes.addAction(t("Maximizar"), lambda: manager.maximize(inst_id))

    def set_image(self, image: QImage) -> None:
        self.preview.set_image(image)

    def refresh(self, inst) -> None:
        self.pill.set_status(inst.status)
        self.pill.adjustSize()
        self.avatar.set_photo(self.ctx.avatars.pixmap(inst.account))
        width = self.WIDTH - 72
        self.name.setText(self.name.fontMetrics().elidedText(inst.account.alias, Qt.ElideRight, width))
        game = inst.profile_name or inst.target.label
        if inst.pid and inst.started_at:
            game = f"{game} · {format_uptime(time.time() - inst.started_at)}"
        self.game.setText(self.game.fontMetrics().elidedText(game, Qt.ElideRight, width))
        self.game.setToolTip(inst.profile_name or inst.target.label)
        self.usage.setText(f"CPU {inst.cpu:.0f}% · {inst.ram_mb:.0f} MB" if inst.pid else t("CPU — · — MB"))
        for chip, value in ((self.afk, inst.anti_afk), (self.reconnect, inst.auto_reconnect)):
            if chip.isChecked() != value:
                chip.blockSignals(True)
                chip.setChecked(value)
                chip.blockSignals(False)
        detail = inst.detail or " "
        self.detail.setText(self.detail.fontMetrics().elidedText(detail, Qt.ElideRight, self.WIDTH - 22))
        self.detail.setToolTip(inst.detail)
        self.preview.set_minimized(winapi.is_window(inst.hwnd) and winapi.is_minimized(inst.hwnd))
