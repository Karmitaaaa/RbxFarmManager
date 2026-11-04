"""Pestaña Instancias: panel de clientes abiertos y opciones de rendimiento."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core import launcher
from core.models import (ST_FAILED, ST_INGAME, ST_LAUNCHING, ST_OPEN, ST_STOPPED, ST_WAIT_NET,
                         ST_WAIT_RECONNECT)
from ui import bind, theme
from ui.context import AppContext
from ui.icons import G
from ui.instance_card import InstanceCard
from ui.widgets import (EmptyState, FlowLayout, IconCircle, Page, SectionHeader, StatusPill, clear_layout,
                        make_card, muted_label, styled_button)
from utils.i18n import N_, t

COLS = [N_("Cuenta"), N_("Estado"), N_("Detalle"), "PID", "CPU", "RAM", N_("Juego"), N_("Reint."), "Anti-AFK", N_("Reconexión"), N_("Acciones")]


class InstancesTab(Page):
    def __init__(self, ctx: AppContext):
        super().__init__(max_width=1280)
        self.ctx = ctx
        self.rows: dict[str, dict] = {}

        # ---------------- contadores
        stats_card, stats_lay = make_card(16, 4)
        row = QHBoxLayout()
        self.counters = {}
        for key, label, glyph, color in (("ingame", t("En juego"), G.PLAY, theme.ACCENTS["green"]),
                                         ("open", t("Abiertas"), G.MONITOR, theme.ACCENTS["blue"]),
                                         ("retry", t("Reconectando"), G.SYNC, theme.ACCENTS["orange"]),
                                         ("failed", t("Fallidas"), G.CLOSE, theme.ACCENTS["red"]),
                                         ("ram", t("RAM total"), G.FLASH, "#8E44AD")):
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 22, 0)
            h.setSpacing(10)
            h.addWidget(IconCircle(glyph, 38, color))
            v = QVBoxLayout()
            v.setSpacing(0)
            num = QLabel("0")
            num.setObjectName("BigCounter")
            num.setStyleSheet("font-size: 17pt;")
            v.addWidget(num)
            v.addWidget(muted_label(label))
            h.addLayout(v)
            row.addWidget(box)
            self.counters[key] = num
        row.addStretch(1)
        self.mutex_label = muted_label("")
        self.mutex_label.setWordWrap(False)
        row.addWidget(self.mutex_label)
        stats_lay.addLayout(row)
        self.body.addWidget(stats_card)

        # ---------------- tabla
        self.header = SectionHeader(t("Instancias (0)"))
        self.view_link = self.header.add_link("", self.toggle_view)
        self.header.add_link(t("Limpiar cerradas"), self.clear_closed)
        self.header.add_link(t("Cerrar todas"), self.close_all)
        self.body.addWidget(self.header)
        self.empty = EmptyState(G.MONITOR, t("No hay instancias abiertas"),
                                t("Ve a Juegos y pulsa «Jugar» en un perfil, o usa «Juego rápido» en Inicio. "
                                "Aquí verás cada ventana de Roblox y su estado."),
                                t("Ir a Juegos"), lambda: ctx.navigate.emit("games"), G.GAME)
        self.body.addWidget(self.empty)
        self.cards: dict[str, InstanceCard] = {}
        self.frames: dict[str, QImage] = {}
        self.cards_host = QWidget()
        self.cards_grid = FlowLayout(14)
        self.cards_host.setLayout(self.cards_grid)
        self.body.addWidget(self.cards_host)
        card, lay = make_card(0, 0)
        self.table_card = card
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLS])
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setMinimumHeight(300)
        lay.addWidget(self.table)
        self.body.addWidget(card)

        # ---------------- rendimiento
        self.body.addWidget(SectionHeader(t("Rendimiento y lanzamiento")))
        card, lay = make_card(16, 8)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        cfg = ctx.cfg
        fps_row = QHBoxLayout()
        self.fps = bind.spin(cfg, "launch.fps_cap", 0, 360, " FPS")
        self.fps.setSpecialValueText(t("Sin límite"))
        fps_row.addWidget(self.fps)
        fps_row.addWidget(styled_button(t("Aplicar ahora"), "secondary", self.apply_fps))
        fps_row.addStretch(1)
        form.addRow(t("Límite de FPS"), fps_row)
        form.addRow(t("Espera entre lanzamientos"), bind.spin(cfg, "launch.delay_s", 0, 120, " s"))
        form.addRow(t("Tiempo máx. para detectar el proceso"), bind.spin(cfg, "launch.pid_timeout_s", 15, 300, " s"))
        form.addRow("", bind.check(cfg, "launch.multi_instance", t("Permitir varias instancias (mutex de un solo cliente)"),
                                   ctx.manager.set_multi_instance))
        form.addRow("", bind.check(cfg, "launch.auto_minimize", t("Minimizar las ventanas al abrirse")))
        form.addRow("", bind.check(cfg, "launch.low_priority", t("Prioridad de CPU baja para ahorrar recursos")))
        form.addRow("", bind.check(cfg, "launch.rename_windows", t("Poner el alias en el título de cada ventana")))
        form.addRow("", bind.check(cfg, "previews.enabled", t("Mostrar la vista previa de las ventanas")))
        form.addRow(t("Actualizar la vista previa cada"), bind.spin(cfg, "previews.interval_s", 1, 30, " s"))
        lay.addLayout(form)
        lay.addWidget(muted_label(t("El límite de FPS se escribe en ClientAppSettings.json de Roblox y afecta a las "
                                  "instancias que abras a partir de ahora. Si usas Bloxstrap, ajústalo también allí.")))
        self.body.addWidget(card)
        self.body.addStretch(1)

        ctx.manager.changed.connect(self.refresh)
        ctx.previews.frame.connect(self._new_frame)
        self.refresh()

    # La captura solo trabaja mientras esta pestaña está a la vista
    def showEvent(self, event):
        super().showEvent(event)
        self.ctx.previews.set_active(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.ctx.previews.set_active(False)

    def _new_frame(self, inst_id: str, image: QImage) -> None:
        self.frames[inst_id] = image
        if inst_id in self.cards:
            self.cards[inst_id].set_image(image)

    def toggle_view(self) -> None:
        view = self.ctx.cfg.get("previews.view", "cards")
        self.ctx.cfg.set("previews.view", "table" if view == "cards" else "cards")
        self.refresh()

    def _refresh_cards(self, instances: list) -> None:
        if list(self.cards) != [i.id for i in instances]:
            clear_layout(self.cards_grid)
            self.cards = {}
            for inst in instances:
                card = InstanceCard(self.ctx, inst)
                if inst.id in self.frames:
                    card.set_image(self.frames[inst.id])
                self.cards_grid.addWidget(card)
                self.cards[inst.id] = card
            self.frames = {k: v for k, v in self.frames.items() if k in self.cards}
        else:
            for inst in instances:
                self.cards[inst.id].refresh(inst)

    def apply_fps(self) -> None:
        n = launcher.apply_fps_cap(self.fps.value())
        if n:
            QMessageBox.information(self, "FPS", t("Límite aplicado en {0} instalación(es) de Roblox. Reinicia las instancias para que surta efecto.", n))
        else:
            QMessageBox.warning(self, "FPS", t("No se encontró ninguna instalación de Roblox Player."))

    def close_all(self) -> None:
        if QMessageBox.question(self, t("Cerrar todas"), t("¿Cerrar todas las instancias de Roblox?")) == QMessageBox.Yes:
            self.ctx.manager.close_all()

    def clear_closed(self) -> None:
        for inst in self.ctx.manager.snapshot():
            if inst.status in (ST_STOPPED, ST_FAILED) or (not inst.pid and inst.status not in
                                                          (ST_WAIT_RECONNECT, ST_WAIT_NET, ST_LAUNCHING)):
                self.ctx.manager.remove(inst.id)

    # ------------------------------------------------------------------ filas
    def _make_row(self, inst) -> dict:
        row = self.table.rowCount()
        self.table.insertRow(row)
        pill = StatusPill(inst.status)
        holder = QWidget()
        h = QHBoxLayout(holder)
        h.setContentsMargins(6, 0, 6, 0)
        h.addWidget(pill, 0, Qt.AlignCenter)
        self.table.setCellWidget(row, 1, holder)

        def centered(widget):
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(widget, 0, Qt.AlignCenter)
            return w

        afk = QCheckBox()
        afk.setChecked(inst.anti_afk)
        afk.toggled.connect(lambda on, i=inst.id: self._set_flag(i, "anti_afk", on))
        rec = QCheckBox()
        rec.setChecked(inst.auto_reconnect)
        rec.toggled.connect(lambda on, i=inst.id: self._set_flag(i, "auto_reconnect", on))
        self.table.setCellWidget(row, 8, centered(afk))
        self.table.setCellWidget(row, 9, centered(rec))

        actions = QWidget()
        a = QHBoxLayout(actions)
        a.setContentsMargins(4, 0, 4, 0)
        a.setSpacing(4)
        for text, glyph, kind, slot, tip in (
            (t("Ejecutar"), G.PLAY, "secondary", lambda _=False, i=inst.id: self.ctx.navigate.emit(f"run:{i}"),
             t("Macro o autoclicker en esta instancia")),
            ("", G.MONITOR, "", lambda _=False, i=inst.id: self.ctx.manager.focus(i), t("Traer la ventana al frente")),
            ("", G.REFRESH, "", lambda _=False, i=inst.id: self.ctx.manager.restart(i), t("Reiniciar (cerrar y abrir)")),
            ("", G.STOP, "danger", lambda _=False, i=inst.id: self.ctx.manager.close(i), t("Cerrar esta instancia")),
            ("", G.CLOSE, "", lambda _=False, i=inst.id: self.ctx.manager.remove(i), t("Quitar de la lista")),
        ):
            btn = styled_button(text, kind, slot, icon=glyph)
            btn.setStyleSheet("padding: 3px 8px; font-size: 9pt; min-height: 18px;")
            btn.setToolTip(tip)
            a.addWidget(btn)
        self.table.setCellWidget(row, 10, actions)
        for col in (0, 2, 3, 4, 5, 6, 7):
            self.table.setItem(row, col, QTableWidgetItem())
        return {"pill": pill, "afk": afk, "rec": rec}

    def _set_flag(self, inst_id: str, attr: str, value: bool) -> None:
        inst = self.ctx.manager.get(inst_id)
        if inst:
            setattr(inst, attr, value)
            if attr == "anti_afk":
                inst.next_afk_at = 0.0

    def refresh(self) -> None:
        instances = self.ctx.manager.snapshot()
        ids = [i.id for i in instances]
        # Reconstruye si cambiaron las filas (altas/bajas); si no, actualiza en sitio
        if list(self.rows.keys()) != ids:
            self.table.setRowCount(0)
            self.rows = {}
            for inst in instances:
                self.rows[inst.id] = self._make_row(inst)
        counts = {"ingame": 0, "open": 0, "retry": 0, "failed": 0}
        ram = 0.0
        for row, inst in enumerate(instances):
            widgets = self.rows[inst.id]
            widgets["pill"].set_status(inst.status)
            for key, value in (("afk", inst.anti_afk), ("rec", inst.auto_reconnect)):
                box = widgets[key]
                if box.isChecked() != value:
                    box.blockSignals(True)
                    box.setChecked(value)
                    box.blockSignals(False)
            values = {
                0: inst.account.alias,
                2: inst.detail,
                3: str(inst.pid or "—"),
                4: f"{inst.cpu:.1f}%" if inst.pid else "—",
                5: f"{inst.ram_mb:.0f} MB" if inst.pid else "—",
                6: inst.profile_name or inst.target.label,
                7: str(inst.retries),
            }
            for col, text in values.items():
                item = self.table.item(row, col)
                if item and item.text() != text:
                    item.setText(text)
            ram += inst.ram_mb if inst.pid else 0
            if inst.status == ST_INGAME:
                counts["ingame"] += 1
            elif inst.status == ST_OPEN:
                counts["open"] += 1
            elif inst.status in (ST_WAIT_RECONNECT, ST_WAIT_NET):
                counts["retry"] += 1
            elif inst.status == ST_FAILED:
                counts["failed"] += 1
        for key, value in counts.items():
            self.counters[key].setText(str(value))
        self.counters["ram"].setText(f"{ram / 1024:.1f} GB" if ram > 1024 else f"{ram:.0f} MB")
        self.header.set_title(t("Instancias ({0})", len(instances)))
        cards_view = self.ctx.cfg.get("previews.view", "cards") == "cards"
        self._refresh_cards(instances)
        self.empty.setVisible(not instances)
        self.cards_host.setVisible(bool(instances) and cards_view)
        self.table_card.setVisible(bool(instances) and not cards_view)
        self.view_link.setText(t("Ver como tabla") if cards_view else t("Ver con vista previa"))
        mutex = self.ctx.manager.mutex.active
        self.mutex_label.setText(t("● Multi-instancia activa") if mutex else t("○ Multi-instancia desactivada"))
        self.mutex_label.setStyleSheet(f"color: {'#02B757' if mutex else '#757575'}; font-weight: 600;")
