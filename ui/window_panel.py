"""Panel «Organizar ventanas» de la pestaña Instancias, con un dibujo de cómo van a quedar."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core import window_layout
from core.window_layout import MODES, ORDERS, SIZE_CUSTOM, SIZE_FIT, SIZE_PRESETS, Rect
from ui import bind, theme
from ui.context import AppContext
from ui.icons import G
from ui.widgets import make_card, muted_label, pal, styled_button
from utils import winapi
from utils.i18n import t

SAMPLE_WINDOWS = 4      # lo que se dibuja cuando aún no hay ninguna abierta


class LayoutPreview(QWidget):
    """Dibujo del monitor con el sitio de cada ventana."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(272, 164)
        self.area = Rect(0, 0, 1920, 1080)
        self.slots: list[Rect] = []
        self.names: list[str] = []

    def show_layout(self, area: Rect, slots: list[Rect], names: list[str]) -> None:
        self.area, self.slots, self.names = area, slots, names
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        scale = min((self.width() - 2) / max(self.area.w, 1), (self.height() - 2) / max(self.area.h, 1))
        width, height = self.area.w * scale, self.area.h * scale
        left, top = (self.width() - width) / 2, (self.height() - height) / 2
        screen = QRectF(left, top, width, height)
        p.setPen(QPen(QColor(pal("card_border")), 1))
        p.setBrush(QColor(pal("bg")))
        p.drawRoundedRect(screen, 4, 4)

        font = QFont(self.font())
        font.setPixelSize(10)
        p.setFont(font)
        accent = QColor(theme.ACCENTS["blue"])
        fill = QColor(accent)
        fill.setAlpha(70)
        for index, slot in enumerate(self.slots):
            rect = QRectF(left + (slot.x - self.area.x) * scale, top + (slot.y - self.area.y) * scale,
                          slot.w * scale, slot.h * scale).adjusted(1, 1, -1, -1)
            p.setPen(QPen(accent, 1))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 2, 2)
            name = self.names[index] if index < len(self.names) else str(index + 1)
            p.setPen(QColor(pal("text")))
            label = p.fontMetrics().elidedText(name, Qt.ElideRight, int(rect.width()) - 6)
            p.drawText(rect.adjusted(3, 2, -3, -2), Qt.AlignLeft | Qt.AlignTop, label)


class WindowPanel(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        cfg = ctx.cfg
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card, lay = make_card(16, 10)
        outer.addWidget(card)

        columns = QHBoxLayout()
        columns.setSpacing(20)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.mode = bind.combo(cfg, "windows.mode", MODES, self.update_preview)
        sizes = {SIZE_FIT: t("Llenar el monitor")}
        sizes.update({f"{w}x{h}": f"{w} × {h}" for w, h in SIZE_PRESETS})
        sizes[SIZE_CUSTOM] = t("Personalizado")
        self.size_box = bind.combo(cfg, "windows.size", sizes, self.update_preview)
        self.monitor = QComboBox()
        self.monitor.currentIndexChanged.connect(self._monitor_changed)
        self.order = bind.combo(cfg, "windows.order", ORDERS, lambda _: ctx.manager.changed.emit())
        self.columns = bind.spin(cfg, "windows.columns", 0, 20)
        self.columns.setSpecialValueText(t("Automático"))
        self.columns.valueChanged.connect(self.update_preview)
        self.gap = bind.spin(cfg, "windows.gap", 0, 100, " px")
        self.gap.valueChanged.connect(self.update_preview)
        self.width_box = bind.spin(cfg, "windows.width", 200, 7680, " px", 10)
        self.width_box.valueChanged.connect(self.update_preview)
        self.height_box = bind.spin(cfg, "windows.height", 150, 4320, " px", 10)
        self.height_box.valueChanged.connect(self.update_preview)

        self.custom_labels = [QLabel(t("Ancho")), QLabel(t("Alto"))]
        self.columns_label = QLabel(t("Columnas"))
        for row, (label_a, box_a, label_b, box_b) in enumerate((
            (QLabel(t("Distribución")), self.mode, QLabel(t("Tamaño")), self.size_box),
            (self.custom_labels[0], self.width_box, self.custom_labels[1], self.height_box),
            (QLabel(t("Monitor")), self.monitor, self.columns_label, self.columns),
            (QLabel(t("Orden")), self.order, QLabel(t("Separación")), self.gap),
        )):
            grid.addWidget(label_a, row, 0)
            grid.addWidget(box_a, row, 1)
            grid.addWidget(label_b, row, 2)
            grid.addWidget(box_b, row, 3)
        self.auto = bind.check(cfg, "windows.auto_arrange", t("Ordenar solas al abrirse una ventana nueva"))
        grid.addWidget(self.auto, 4, 0, 1, 4)
        columns.addLayout(grid, 1)

        side = QVBoxLayout()
        side.setSpacing(4)
        self.preview = LayoutPreview()
        side.addWidget(self.preview)
        self.summary = muted_label("")
        self.summary.setAlignment(Qt.AlignCenter)
        self.summary.setMaximumWidth(self.preview.width())
        side.addWidget(self.summary)
        side.addStretch(1)
        columns.addLayout(side)
        lay.addLayout(columns)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.apply_btn = styled_button(t("Ordenar ventanas"), "primary", lambda: ctx.manager.arrange(), icon=G.MONITOR)
        buttons.addWidget(self.apply_btn)
        self.show_btn = styled_button(t("Mostrar todas"), "", ctx.manager.restore_all)
        buttons.addWidget(self.show_btn)
        buttons.addStretch(1)
        lay.addLayout(buttons)
        lay.addWidget(muted_label(t("Las macros con clics usan posiciones de la pantalla: ordena las ventanas "
                                    "antes de grabarlas y no las cambies de sitio después.")))
        self.reload_monitors()

    def reload_monitors(self) -> None:
        """Vuelve a mirar los monitores: pueden conectarse o cambiar de resolución con la app abierta."""
        self.monitors = winapi.monitors()
        saved = self.ctx.cfg.get("windows.monitor", "")
        self.monitor.blockSignals(True)
        self.monitor.clear()
        for number, item in enumerate(self.monitors, 1):
            text = t("Monitor {0} · {1} × {2}", number, item["width"], item["height"])
            self.monitor.addItem(t("{0} (principal)", text) if item["primary"] else text, item["device"])
        self.monitor.setCurrentIndex(max(0, self.monitor.findData(saved)))
        self.monitor.blockSignals(False)
        self.update_preview()

    def _monitor_changed(self) -> None:
        self.ctx.cfg.set("windows.monitor", self.monitor.currentData() or "")
        self.update_preview()

    def update_preview(self, *_) -> None:
        cfg = self.ctx.cfg.section("windows")
        is_custom = cfg.get("size") == SIZE_CUSTOM
        for widget in (*self.custom_labels, self.width_box, self.height_box):
            widget.setVisible(is_custom)
        is_grid = cfg.get("mode") == "grid"
        self.columns.setEnabled(is_grid)
        self.columns_label.setEnabled(is_grid)

        instances = self.ctx.manager.window_instances()
        for button in (self.apply_btn, self.show_btn):
            button.setEnabled(bool(instances))
        monitor = window_layout.pick_monitor(cfg.get("monitor", ""), self.monitors)
        if monitor is None:
            return
        slots, overlap = window_layout.layout_for(len(instances) or SAMPLE_WINDOWS, cfg, monitor)
        names = [i.account.alias for i in instances]
        self.preview.show_layout(Rect(monitor["x"], monitor["y"], monitor["w"], monitor["h"]), slots, names)
        if not instances:
            self.summary.setText(t("Ejemplo con {0} ventanas", SAMPLE_WINDOWS))
        elif overlap:
            self.summary.setText(t("{0} ventanas: no caben todas, se superponen", len(instances)))
        else:
            self.summary.setText(t("{0} ventanas · {1} × {2} cada una", len(instances), slots[0].w, slots[0].h))
