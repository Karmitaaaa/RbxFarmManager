"""Pestaña Instancias: panel de clientes abiertos y opciones de rendimiento."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core import launcher
from core.models import ST_FAILED, ST_INGAME, ST_OPEN, ST_STOPPED, ST_WAIT_NET, ST_WAIT_RECONNECT
from ui import bind, theme
from ui.context import AppContext
from ui.icons import G
from ui.widgets import (EmptyState, IconCircle, Page, SectionHeader, StatusPill, make_card, muted_label,
                        styled_button)

COLS = ["Cuenta", "Estado", "Detalle", "PID", "CPU", "RAM", "Juego", "Reint.", "Anti-AFK", "Reconexión", "Acciones"]


class InstancesTab(Page):
    def __init__(self, ctx: AppContext):
        super().__init__(max_width=1280)
        self.ctx = ctx
        self.rows: dict[str, dict] = {}

        # ---------------- contadores
        stats_card, stats_lay = make_card(16, 4)
        row = QHBoxLayout()
        self.counters = {}
        for key, label, glyph, color in (("ingame", "En juego", G.PLAY, theme.ACCENTS["green"]),
                                         ("open", "Abiertas", G.MONITOR, theme.ACCENTS["blue"]),
                                         ("retry", "Reconectando", G.SYNC, theme.ACCENTS["orange"]),
                                         ("failed", "Fallidas", G.CLOSE, theme.ACCENTS["red"]),
                                         ("ram", "RAM total", G.FLASH, "#8E44AD")):
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
        self.header = SectionHeader("Instancias (0)")
        self.header.add_link("Limpiar cerradas", self.clear_closed)
        self.header.add_link("Cerrar todas", self.close_all)
        self.body.addWidget(self.header)
        self.empty = EmptyState(G.MONITOR, "No hay instancias abiertas",
                                "Ve a Juegos y pulsa «Jugar» en un perfil, o usa «Juego rápido» en Inicio. "
                                "Aquí verás cada ventana de Roblox y su estado.",
                                "Ir a Juegos", lambda: ctx.navigate.emit("games"), G.GAME)
        self.body.addWidget(self.empty)
        card, lay = make_card(0, 0)
        self.table_card = card
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
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
        self.body.addWidget(SectionHeader("Rendimiento y lanzamiento"))
        card, lay = make_card(16, 8)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        cfg = ctx.cfg
        fps_row = QHBoxLayout()
        self.fps = bind.spin(cfg, "launch.fps_cap", 0, 360, " FPS")
        self.fps.setSpecialValueText("Sin límite")
        fps_row.addWidget(self.fps)
        fps_row.addWidget(styled_button("Aplicar ahora", "secondary", self.apply_fps))
        fps_row.addStretch(1)
        form.addRow("Límite de FPS", fps_row)
        form.addRow("Espera entre lanzamientos", bind.spin(cfg, "launch.delay_s", 0, 120, " s"))
        form.addRow("Tiempo máx. para detectar el proceso", bind.spin(cfg, "launch.pid_timeout_s", 15, 300, " s"))
        form.addRow("", bind.check(cfg, "launch.multi_instance", "Permitir varias instancias (mutex de un solo cliente)",
                                   ctx.manager.set_multi_instance))
        form.addRow("", bind.check(cfg, "launch.auto_minimize", "Minimizar las ventanas al abrirse"))
        form.addRow("", bind.check(cfg, "launch.low_priority", "Prioridad de CPU baja para ahorrar recursos"))
        form.addRow("", bind.check(cfg, "launch.rename_windows", "Poner el alias en el título de cada ventana"))
        lay.addLayout(form)
        lay.addWidget(muted_label("El límite de FPS se escribe en ClientAppSettings.json de Roblox y afecta a las "
                                  "instancias que abras a partir de ahora. Si usas Bloxstrap, ajústalo también allí."))
        self.body.addWidget(card)
        self.body.addStretch(1)

        ctx.manager.changed.connect(self.refresh)
        self.refresh()

    def apply_fps(self) -> None:
        n = launcher.apply_fps_cap(self.fps.value())
        if n:
            QMessageBox.information(self, "FPS", f"Límite aplicado en {n} instalación(es) de Roblox. "
                                                 "Reinicia las instancias para que surta efecto.")
        else:
            QMessageBox.warning(self, "FPS", "No se encontró ninguna instalación de Roblox Player.")

    def close_all(self) -> None:
        if QMessageBox.question(self, "Cerrar todas", "¿Cerrar todas las instancias de Roblox?") == QMessageBox.Yes:
            self.ctx.manager.close_all()

    def clear_closed(self) -> None:
        for inst in self.ctx.manager.snapshot():
            if inst.status in (ST_STOPPED, ST_FAILED) or (not inst.pid and inst.status not in
                                                          (ST_WAIT_RECONNECT, ST_WAIT_NET, "Lanzando")):
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
            ("Ejecutar", G.PLAY, "secondary", lambda _=False, i=inst.id: self.ctx.navigate.emit(f"run:{i}"),
             "Macro o autoclicker en esta instancia"),
            ("", G.MONITOR, "", lambda _=False, i=inst.id: self.ctx.manager.focus(i), "Traer la ventana al frente"),
            ("", G.REFRESH, "", lambda _=False, i=inst.id: self.ctx.manager.restart(i), "Reiniciar (cerrar y abrir)"),
            ("", G.STOP, "danger", lambda _=False, i=inst.id: self.ctx.manager.close(i), "Cerrar esta instancia"),
            ("", G.CLOSE, "", lambda _=False, i=inst.id: self.ctx.manager.remove(i), "Quitar de la lista"),
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
        self.header.set_title(f"Instancias ({len(instances)})")
        self.empty.setVisible(not instances)
        self.table_card.setVisible(bool(instances))
        mutex = self.ctx.manager.mutex.active
        self.mutex_label.setText("● Multi-instancia activa" if mutex else "○ Multi-instancia desactivada")
        self.mutex_label.setStyleSheet(f"color: {'#02B757' if mutex else '#757575'}; font-weight: 600;")
