"""Pestaña Autoclicker."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                               QVBoxLayout)

from core.autoclicker import BUTTONS
from core.models import ST_INGAME, ST_OPEN
from ui import bind
from ui.context import AppContext
from ui.widgets import HotkeyEdit, Page, SectionHeader, make_card, muted_label, styled_button
from utils import winapi
from utils.i18n import t

SETTING_KEYS = ("button", "interval_ms", "random_ms", "mode", "count", "position", "x", "y", "hold_ms")


class ClickerTab(Page):
    def __init__(self, ctx: AppContext):
        super().__init__(max_width=1100)
        self.ctx = ctx
        cfg = ctx.cfg
        self._countdown = 0
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # ---------------- ajustes
        left = QVBoxLayout()
        left.addWidget(SectionHeader("Autoclicker"))
        card, lay = make_card(16, 8)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        self.widgets = [
            bind.combo(cfg, "clicker.button", BUTTONS),
            bind.spin(cfg, "clicker.interval_ms", 1, 600000, " ms"),
            bind.spin(cfg, "clicker.random_ms", 0, 10000, " ms"),
            bind.spin(cfg, "clicker.hold_ms", 0, 2000, " ms"),
            bind.combo(cfg, "clicker.mode", {"toggle": t("Alternar (pulsa para iniciar/parar)"),
                                             "hold": t("Mantener (clica mientras mantienes la tecla)")}),
        ]
        form.addRow(t("Botón"), self.widgets[0])
        form.addRow(t("Intervalo"), self.widgets[1])
        form.addRow(t("Variación aleatoria ±"), self.widgets[2])
        form.addRow(t("Duración de cada click"), self.widgets[3])
        form.addRow(t("Modo de la hotkey"), self.widgets[4])

        count_row = QHBoxLayout()
        self.count = bind.spin(cfg, "clicker.count", 0, 10_000_000, t(" clicks"))
        self.count.setSpecialValueText(t("Infinito"))
        self.infinite = QCheckBox(t("Infinito"))
        self.infinite.setChecked(self.count.value() == 0)
        self.infinite.toggled.connect(lambda on: self.count.setValue(0 if on else max(100, self.count.value())))
        self.count.valueChanged.connect(lambda v: self.infinite.setChecked(v == 0))
        count_row.addWidget(self.count)
        count_row.addWidget(self.infinite)
        count_row.addStretch(1)
        form.addRow(t("Cantidad"), count_row)
        self.widgets.append(self.count)

        self.position = bind.combo(cfg, "clicker.position", {"cursor": t("Donde esté el cursor"),
                                                             "fixed": t("Posición fija")})
        form.addRow(t("Posición"), self.position)
        xy = QHBoxLayout()
        self.x = bind.spin(cfg, "clicker.x", -10000, 20000)
        self.y = bind.spin(cfg, "clicker.y", -10000, 20000)
        self.x.setPrefix("X ")
        self.y.setPrefix("Y ")
        self.capture_btn = styled_button(t("Capturar (3 s)"), "", self.start_capture)
        xy.addWidget(self.x)
        xy.addWidget(self.y)
        xy.addWidget(self.capture_btn)
        xy.addStretch(1)
        form.addRow(t("Coordenadas"), xy)
        self.widgets += [self.position, self.x, self.y]

        self.target = QComboBox()
        form.addRow(t("Ventana destino"), self.target)
        lay.addLayout(form)
        lay.addWidget(muted_label(t("Con una ventana destino, la app la enfoca antes de empezar y las "
                                  "coordenadas fijas se toman relativas a su área de juego.")))
        left.addWidget(card)

        left.addWidget(SectionHeader(t("Presets (asignables a cuentas)")))
        card, lay = make_card(16, 8)
        row = QHBoxLayout()
        self.presets = QComboBox()
        self.presets.setMinimumWidth(200)
        row.addWidget(self.presets, 1)
        row.addWidget(styled_button(t("Cargar"), "", self.load_preset))
        row.addWidget(styled_button(t("Guardar como…"), "secondary", self.save_preset))
        row.addWidget(styled_button(t("Eliminar"), "", self.delete_preset))
        lay.addLayout(row)
        left.addWidget(card)
        left.addStretch(1)

        # ---------------- control
        right = QVBoxLayout()
        right.addWidget(SectionHeader(t("Control")))
        card, lay = make_card(20, 12)
        self.state = QLabel(t("Detenido"))
        self.state.setObjectName("BigCounter")
        self.state.setAlignment(Qt.AlignCenter)
        self.clicks = muted_label(t("0 clicks"))
        self.clicks.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.state)
        lay.addWidget(self.clicks)
        self.toggle_btn = styled_button(t("Iniciar"), "primary", self.toggle, big=True)
        lay.addWidget(self.toggle_btn)
        hk = QHBoxLayout()
        hk.addWidget(QLabel(t("Hotkey global")))
        self.hotkey = HotkeyEdit(cfg.get("hotkeys.clicker", "F6"))
        self.hotkey.hotkey_changed.connect(self.set_hotkey)
        hk.addWidget(self.hotkey)
        hk.addStretch(1)
        lay.addLayout(hk)
        lay.addWidget(muted_label(t("La hotkey funciona aunque la app esté minimizada o en la bandeja.")))
        right.addWidget(card)
        right.addStretch(1)

        columns.addLayout(left, 3)
        columns.addLayout(right, 2)
        self.body.addLayout(columns)
        self.body.addStretch(1)

        ctx.clicker.state_changed.connect(self._state_changed)
        ctx.clicker.progress.connect(lambda n: self.clicks.setText(f"{n:,} clicks".replace(",", ".")))
        ctx.manager.changed.connect(self.refresh_targets)
        ctx.presets_changed.connect(self.refresh_presets)
        self.refresh_targets()
        self.refresh_presets()

    # ------------------------------------------------------------------ control
    def settings(self) -> dict:
        return dict(self.ctx.cfg.get("clicker", {}))

    def target_hwnd(self) -> int | None:
        inst = self.ctx.manager.get(self.target.currentData() or "")
        return inst.hwnd if inst and winapi.is_window(inst.hwnd) else None

    def toggle(self) -> None:
        self.ctx.clicker.toggle(self.settings(), self.target_hwnd())

    def start_for_instance(self, inst_id: str, preset: str) -> None:
        settings = self.ctx.cfg.get("clicker_presets", {}).get(preset) or self.settings()
        inst = self.ctx.manager.get(inst_id)
        self.ctx.clicker.start(settings, inst.hwnd if inst else None)

    def _state_changed(self, running: bool) -> None:
        self.state.setText(t("En marcha") if running else t("Detenido"))
        self.state.setStyleSheet(f"color: {'#02B757' if running else ''};")
        self.toggle_btn.setText(t("Detener") if running else t("Iniciar"))
        self.toggle_btn.setObjectName("DangerButton" if running else "PrimaryButton")
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)

    def set_hotkey(self, text: str) -> None:
        self.ctx.cfg.set("hotkeys.clicker", text)
        self.ctx.hotkeys.set_binding("clicker", text)

    def refresh_targets(self) -> None:
        current = self.target.currentData()
        items = [("", t("Pantalla completa (sin ventana)"))]
        items += [(i.id, f"{i.account.alias} (PID {i.pid})") for i in self.ctx.manager.snapshot()
                  if i.status in (ST_OPEN, ST_INGAME) and i.hwnd]
        if [self.target.itemData(k) for k in range(self.target.count())] == [k for k, _ in items]:
            return
        self.target.blockSignals(True)
        self.target.clear()
        for key, label in items:
            self.target.addItem(label, key)
        self.target.setCurrentIndex(max(0, self.target.findData(current)))
        self.target.blockSignals(False)

    # ------------------------------------------------------------------ captura
    def start_capture(self) -> None:
        self._countdown = 3
        self.capture_btn.setEnabled(False)
        self._tick()

    def _tick(self) -> None:
        if self._countdown > 0:
            self.capture_btn.setText(t("Mueve el ratón… {0}", self._countdown))
            self._countdown -= 1
            QTimer.singleShot(1000, self._tick)
            return
        x, y = winapi.cursor_pos()
        hwnd = self.target_hwnd()
        rect = winapi.client_rect_on_screen(hwnd) if hwnd else None
        if rect:
            x, y = x - rect[0], y - rect[1]
        self.x.setValue(x)
        self.y.setValue(y)
        self.position.setCurrentIndex(self.position.findData("fixed"))
        self.capture_btn.setText(t("Capturar (3 s)"))
        self.capture_btn.setEnabled(True)

    # ------------------------------------------------------------------ presets
    def refresh_presets(self) -> None:
        current = self.presets.currentText()
        self.presets.clear()
        self.presets.addItems(sorted(self.ctx.cfg.get("clicker_presets", {}).keys()))
        idx = self.presets.findText(current)
        if idx >= 0:
            self.presets.setCurrentIndex(idx)

    def save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, t("Guardar preset"), t("Nombre del preset:"),
                                        text=self.presets.currentText())
        name = name.strip()
        if not ok or not name:
            return
        presets = dict(self.ctx.cfg.get("clicker_presets", {}))
        presets[name] = {k: self.settings().get(k) for k in SETTING_KEYS}
        self.ctx.cfg.set("clicker_presets", presets)
        self.ctx.presets_changed.emit()
        self.presets.setCurrentText(name)

    def load_preset(self) -> None:
        preset = self.ctx.cfg.get("clicker_presets", {}).get(self.presets.currentText())
        if not preset:
            return
        for key, value in preset.items():
            self.ctx.cfg.set(f"clicker.{key}", value)
        for widget in self.widgets:
            widget.reload()

    def delete_preset(self) -> None:
        name = self.presets.currentText()
        if not name or QMessageBox.question(self, t("Eliminar preset"), t("¿Eliminar «{0}»?", name)) != QMessageBox.Yes:
            return
        presets = dict(self.ctx.cfg.get("clicker_presets", {}))
        presets.pop(name, None)
        self.ctx.cfg.set("clicker_presets", presets)
        self.ctx.presets_changed.emit()
