"""Pestaña Anti-AFK / Reconexión."""
import threading
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QFormLayout, QHBoxLayout, QHeaderView, QListWidget,
                               QListWidgetItem, QTableWidget, QTableWidgetItem, QVBoxLayout)

from core.anti_afk import ACTIONS, METHODS
from core.models import ST_INGAME, ST_OPEN
from ui import bind, theme
from ui.context import AppContext
from ui.widgets import HotkeyEdit, Page, SectionHeader, make_card, muted_label, styled_button
from utils.i18n import t


class AfkTab(Page):
    def __init__(self, ctx: AppContext):
        super().__init__(max_width=1200)
        self.ctx = ctx
        cfg = ctx.cfg
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # ---------------- Anti-AFK
        left = QVBoxLayout()
        left.addWidget(SectionHeader("Anti-AFK"))
        card, lay = make_card(16, 8)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.addRow("", bind.check(cfg, "antiafk.enabled", t("Anti-AFK activado (global)")))
        interval = QHBoxLayout()
        self.min_s = bind.spin(cfg, "antiafk.min_s", 10, 1200, " s")
        self.max_s = bind.spin(cfg, "antiafk.max_s", 10, 1200, " s")
        self.min_s.valueChanged.connect(lambda v: self.max_s.setValue(max(v, self.max_s.value())))
        self.max_s.valueChanged.connect(lambda v: self.min_s.setValue(min(v, self.min_s.value())))
        interval.addWidget(self.min_s)
        interval.addWidget(muted_label("–"))
        interval.addWidget(self.max_s)
        interval.addStretch(1)
        form.addRow(t("Intervalo aleatorio"), interval)
        form.addRow(t("Acción"), bind.combo(cfg, "antiafk.action", ACTIONS))
        key = HotkeyEdit(cfg.get("antiafk.custom_key", "SPACE"))
        key.hotkey_changed.connect(lambda v: cfg.set("antiafk.custom_key", v.split("+")[-1] if v else "SPACE"))
        form.addRow(t("Tecla personalizada"), key)
        form.addRow(t("Método"), bind.combo(cfg, "antiafk.method", METHODS))
        form.addRow(t("Esperar si usas el PC"), bind.spin(cfg, "antiafk.pause_if_user_active_s", 0, 60, " s"))
        form.addRow("", bind.check(cfg, "antiafk.reminimize", t("Volver a minimizar la ventana tras actuar")))
        lay.addLayout(form)
        lay.addWidget(muted_label(t("Roblox expulsa tras 20 min sin actividad. Con «Foco breve» la ventana se "
                                  "enfoca ~0,3 s y luego se devuelve el foco a la que estabas usando; si estás "
                                  "escribiendo o moviendo el ratón, espera unos segundos. Actívalo o desactívalo "
                                  "por instancia en la pestaña Instancias.")))
        lay.addWidget(styled_button(t("Probar ahora en todas las instancias"), "secondary", self.test_now))
        left.addWidget(card)

        left.addWidget(SectionHeader(t("Próximas acciones")))
        card, lay = make_card(0, 0)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([t("Cuenta"), "Anti-AFK", t("Última"), t("Próxima en")])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(180)
        lay.addWidget(self.table)
        left.addWidget(card)
        left.addStretch(1)

        # ---------------- Reconexión
        right = QVBoxLayout()
        right.addWidget(SectionHeader(t("Auto-reconexión")))
        card, lay = make_card(16, 8)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.addRow("", bind.check(cfg, "reconnect.enabled", t("Reconectar automáticamente")))
        form.addRow(t("Intentos máximos"), bind.spin(cfg, "reconnect.max_attempts", 1, 100))
        form.addRow(t("Espera inicial"), bind.spin(cfg, "reconnect.base_delay_s", 1, 600, " s"))
        form.addRow(t("Espera máxima"), bind.spin(cfg, "reconnect.max_delay_s", 5, 3600, " s"))
        form.addRow(t("Margen ante desconexión"), bind.spin(cfg, "reconnect.disconnect_grace_s", 5, 300, " s"))
        form.addRow(t("Tiempo máx. para entrar"), bind.spin(cfg, "reconnect.join_timeout_s", 30, 900, " s"))
        form.addRow("", bind.check(cfg, "reconnect.restart_on_join_timeout", t("Reiniciar si no entra al juego a tiempo")))
        form.addRow("", bind.check(cfg, "reconnect.check_internet", t("Detectar caídas de internet (no gasta intentos)")))
        form.addRow(t("Reiniciar contador tras"), bind.spin(cfg, "reconnect.reset_after_s", 30, 7200, t(" s en juego")))
        lay.addLayout(form)
        lay.addWidget(muted_label(t("Detecta: proceso cerrado, ventanas de error/crash del cliente, desconexión del "
                                  "servidor (leyendo el archivo de log de Roblox, sin tocar su memoria) y caída "
                                  "de internet. La espera crece así: inicial × 2 por intento, hasta la máxima. "
                                  "El margen evita falsos positivos durante los teletransportes.")))
        right.addWidget(card)

        events_header = SectionHeader(t("Eventos de conexión"))
        events_header.add_link(t("Limpiar"), lambda: self.events.clear())
        right.addWidget(events_header)
        card, lay = make_card(0, 0)
        self.events = QListWidget()
        self.events.setMinimumHeight(220)
        self.events.setWordWrap(True)
        lay.addWidget(self.events)
        right.addWidget(card)
        right.addStretch(1)

        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        self.body.addLayout(columns)
        self.body.addStretch(1)

        ctx.manager.notify.connect(self.add_event)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)

    def add_event(self, level: str, text: str) -> None:
        icon = {"error": "⛔", "warning": "⚠"}.get(level, "✔")
        item = QListWidgetItem(f"{icon}  {time.strftime('%Y-%m-%d %H:%M:%S')}  {text}")
        if level in ("error", "warning"):
            item.setForeground(QColor(theme.ACCENTS["red" if level == "error" else "orange"]))
        self.events.insertItem(0, item)
        while self.events.count() > 300:
            self.events.takeItem(self.events.count() - 1)

    def test_now(self) -> None:
        targets = [i for i in self.ctx.manager.snapshot() if i.status in (ST_OPEN, ST_INGAME) and i.hwnd]
        if not targets:
            self.add_event("warning", t("No hay instancias abiertas para probar el anti-AFK"))
            return

        def _run():
            for inst in targets:
                self.ctx.anti_afk.perform(inst)
                time.sleep(0.3)

        threading.Thread(target=_run, name="afk-test", daemon=True).start()

    def refresh(self) -> None:
        if not self.isVisible():
            return
        instances = self.ctx.manager.snapshot()
        self.table.setRowCount(len(instances))
        now = time.time()
        for row, inst in enumerate(instances):
            last = time.strftime("%H:%M:%S", time.localtime(inst.last_afk_at)) if inst.last_afk_at else "—"
            if not inst.anti_afk:
                nxt = "desactivado"
            elif inst.status not in (ST_OPEN, ST_INGAME):
                nxt = f"({t(inst.status).lower()})"
            elif inst.next_afk_at:
                nxt = f"{max(0, inst.next_afk_at - now):.0f} s"
            else:
                nxt = "programando…"
            for col, text in enumerate([inst.account.alias, t("Sí") if inst.anti_afk else t("No"), last, nxt]):
                self.table.setItem(row, col, QTableWidgetItem(text))
