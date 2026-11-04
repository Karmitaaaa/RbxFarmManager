"""Pestaña Macros: perfiles, grabación y reproducción."""
import logging
import time

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout)

from core.models import ST_INGAME, ST_OPEN
from ui import bind
from ui.context import AppContext
from ui.icons import G, GlyphLabel, glyph_icon
from ui.widgets import HotkeyEdit, Page, SectionHeader, make_card, muted_label, styled_button
from utils.hotkeys import parse_hotkey
from utils.i18n import N_, t

log = logging.getLogger("macros")

HOTKEYS = (("macro_record", N_("Grabar")), ("macro_stop", N_("Parar")), ("macro_play", N_("Reproducir")))


class MacrosTab(Page):
    def __init__(self, ctx: AppContext):
        super().__init__(max_width=1150)
        self.ctx = ctx
        cfg = ctx.cfg
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # ---------------- lista de perfiles
        left = QVBoxLayout()
        self.list_header = SectionHeader(t("Macros (0)"))
        self.list_header.add_link(t("Importar"), self.import_profile)
        self.list_header.add_link(t("Exportar"), self.export_profile)
        left.addWidget(self.list_header)
        card, lay = make_card(0, 0)
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(10, 10, 10, 4)
        filter_row.addWidget(GlyphLabel(G.GAME, 16))
        self.game_filter = QComboBox()
        self.game_filter.setToolTip(t("Muestra solo las macros de un juego"))
        self.game_filter.currentIndexChanged.connect(lambda _: self.refresh())
        filter_row.addWidget(self.game_filter, 1)
        lay.addLayout(filter_row)
        self.list = QListWidget()
        self.list.setMinimumHeight(360)
        self.list.setIconSize(QSize(30, 30))
        self.list.currentTextChanged.connect(self.show_details)
        self.list.itemDoubleClicked.connect(lambda _: self.play_selected())
        lay.addWidget(self.list)
        actions = QHBoxLayout()
        actions.setContentsMargins(10, 8, 10, 10)
        for text, glyph, slot in ((t("Renombrar"), G.RENAME, self.rename), (t("Duplicar"), G.COPY, self.duplicate),
                                  (t("Eliminar"), G.DELETE, self.delete)):
            actions.addWidget(styled_button(text, "", slot, icon=glyph))
        actions.addStretch(1)
        lay.addLayout(actions)
        left.addWidget(card)
        left.addStretch(1)

        # ---------------- detalle y control
        right = QVBoxLayout()
        right.addWidget(SectionHeader(t("Grabar y reproducir")))
        card, lay = make_card(18, 10)
        self.title = QLabel(t("Ninguna macro seleccionada"))
        self.title.setObjectName("CardTitle")
        self.info = muted_label("")
        lay.addWidget(self.title)
        lay.addWidget(self.info)
        game_row = QHBoxLayout()
        game_row.addWidget(QLabel(t("Juego de esta macro")))
        self.game_assign = QComboBox()
        self.game_assign.setToolTip(t("Organiza la macro dentro de un perfil de juego"))
        self.game_assign.currentIndexChanged.connect(self._assign_game)
        game_row.addWidget(self.game_assign, 1)
        lay.addLayout(game_row)

        self.state = QLabel("")
        self.state.setStyleSheet("font-weight: 700;")
        lay.addWidget(self.state)

        buttons = QHBoxLayout()
        self.rec_btn = styled_button(t("Grabar"), "danger", self.toggle_record, icon=G.RECORD)
        self.play_btn = styled_button(t("Reproducir"), "primary", self.play_selected, icon=G.PLAY)
        self.stop_btn = styled_button(t("Parar"), "", self.stop_all, icon=G.STOP)
        for b in (self.rec_btn, self.play_btn, self.stop_btn):
            b.setStyleSheet("font-size: 11.5pt; padding: 7px 18px;")
            buttons.addWidget(b)
        buttons.addStretch(1)
        lay.addLayout(buttons)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.addRow(t("Velocidad"), bind.dspin(cfg, "macro.speed", 0.1, 10.0, 0.1, "×"))
        repeat = bind.spin(cfg, "macro.repeat", 0, 1_000_000, t(" veces"))
        repeat.setSpecialValueText(t("Infinito"))
        form.addRow(t("Repeticiones"), repeat)
        form.addRow(t("Pausa entre bucles"), bind.spin(cfg, "macro.loop_delay_ms", 0, 3_600_000, " ms", 100))
        self.target = QComboBox()
        form.addRow(t("Instancia destino"), self.target)
        form.addRow("", bind.check(cfg, "macro.focus_target", t("Enfocar la instancia antes de cada bucle")))
        form.addRow("", bind.check(cfg, "macro.relative_mouse", t("Ratón relativo (útil para girar la cámara)")))
        form.addRow("", bind.check(cfg, "macro.record_moves", t("Grabar movimientos del ratón")))
        form.addRow(t("Muestreo del ratón"), bind.spin(cfg, "macro.move_throttle_ms", 0, 500, " ms"))
        lay.addLayout(form)
        right.addWidget(card)

        right.addWidget(SectionHeader(t("Hotkeys globales")))
        card, lay = make_card(16, 8)
        grid = QGridLayout()
        for row, (key, label) in enumerate(HOTKEYS):
            edit = HotkeyEdit(cfg.get(f"hotkeys.{key}", ""))
            edit.hotkey_changed.connect(lambda text, k=key: self.set_hotkey(k, text))
            grid.addWidget(QLabel(t(label)), row, 0)
            grid.addWidget(edit, row, 1)
        grid.setColumnStretch(2, 1)
        lay.addLayout(grid)
        lay.addWidget(muted_label(t("Las grabaciones hechas con la hotkey se guardan solas con fecha y hora; "
                                  "después puedes renombrarlas. «Reproducir» usa el perfil seleccionado aquí.")))
        self.used_by = muted_label("")
        lay.addWidget(self.used_by)
        right.addWidget(card)
        right.addStretch(1)

        columns.addLayout(left, 2)
        columns.addLayout(right, 3)
        self.body.addLayout(columns)
        self.body.addStretch(1)

        ctx.recorder.counter.connect(lambda n: self.state.setText(t("● Grabando… {0} eventos", n)))
        ctx.recorder.state_changed.connect(self._update_state)
        ctx.player.state_changed.connect(self._update_state)
        ctx.player.loop_done.connect(lambda n: self.state.setText(t("▶ Reproduciendo «{0}» · bucle {1}", ctx.player.current_name, n)))
        ctx.profiles_changed.connect(self.refresh)
        ctx.accounts_changed.connect(lambda: self.show_details(self.selected_name() or ""))
        ctx.games_changed.connect(self.refresh_games)
        ctx.avatars.updated.connect(lambda kind, _key: self.refresh() if kind == "game" else None)
        ctx.manager.changed.connect(self.refresh_targets)
        self.refresh_games()
        self.refresh_targets()
        self._update_state()

    # ------------------------------------------------------------------ juegos
    def refresh_games(self) -> None:
        games = self.ctx.games.all()
        for combo, first in ((self.game_filter, [("*", t("Todos los juegos")), ("", t("Sin juego asignado"))]),
                             (self.game_assign, [("", t("Sin juego"))])):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for key, label in first:
                combo.addItem(label, key)
            for game in games:
                combo.addItem(self._game_icon(game.id), game.name, game.id)
            combo.setCurrentIndex(max(0, combo.findData(current)))
            combo.blockSignals(False)
        self.refresh()

    def _game_icon(self, game_id: str) -> QIcon:
        game = self.ctx.games.get(game_id) if game_id else None
        photo = self.ctx.avatars.game_icon(game.place_id) if game else None
        return QIcon(photo) if photo else glyph_icon(G.GAME if game else G.RECORD, "#757575", 20)

    def set_game_filter(self, game_id: str) -> None:
        self.refresh_games()
        idx = self.game_filter.findData(game_id)
        if idx >= 0:
            self.game_filter.setCurrentIndex(idx)

    def _filter_game(self) -> str:
        """ID del juego filtrado ("" si el filtro es «Todos» o «Sin juego»)."""
        data = self.game_filter.currentData()
        return data if data not in ("*", None) else ""

    def _assign_game(self) -> None:
        name = self.selected_name()
        if not name:
            return
        self.ctx.profiles.set_game(name, self.game_assign.currentData() or "")
        self.refresh(select=name)

    # ------------------------------------------------------------------ lista
    def refresh(self, select: str | None = None) -> None:
        current = select or self.selected_name()
        wanted = self.game_filter.currentData()
        names = [n for n in self.ctx.profiles.names()
                 if wanted in ("*", None) or self.ctx.profiles.game_of(n) == wanted]
        self.list.blockSignals(True)
        self.list.clear()
        for name in names:
            game_id = self.ctx.profiles.game_of(name)
            game = self.ctx.games.get(game_id) if game_id else None
            item = QListWidgetItem(self._game_icon(game_id), name)
            item.setToolTip(t("Juego: {0}", game.name) if game else t("Sin juego asignado"))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.list_header.set_title(t("Macros ({0})", len(names)))
        if current in names:
            self.list.setCurrentRow(names.index(current))
        elif names:
            self.list.setCurrentRow(0)
        self.show_details(self.selected_name() or "")

    def selected_name(self) -> str | None:
        item = self.list.currentItem()
        return item.text() if item else None

    def show_details(self, name: str) -> None:
        self.game_assign.setEnabled(bool(name))
        if not name:
            self.title.setText(t("Ninguna macro seleccionada"))
            self.info.setText(t("Pulsa «Grabar» (o la hotkey) para crear tu primera macro. Si eliges un juego "
                              "en el filtro, la grabación se guardará dentro de ese juego."))
            self.used_by.setText("")
            return
        self.game_assign.blockSignals(True)
        self.game_assign.setCurrentIndex(max(0, self.game_assign.findData(self.ctx.profiles.game_of(name))))
        self.game_assign.blockSignals(False)
        try:
            data = self.ctx.profiles.load(name)
        except Exception as exc:
            self.info.setText(t("No se pudo leer: {0}", exc))
            return
        events = data.get("events", [])
        keys = sum(1 for e in events if e["type"] == "key" and e["down"])
        clicks = sum(1 for e in events if e["type"] == "button" and e["down"])
        created = time.strftime("%Y-%m-%d %H:%M", time.localtime(data.get("created", 0)))
        self.title.setText(name)
        self.info.setText(t("{0} eventos · {1:.1f} s · {2} teclas · {3} clicks · creado {4}", len(events), data.get('duration', 0), keys, clicks, created))
        users = [t("perfil «{0}»", g.name) for g in self.ctx.games.all() if g.macro_profile == name]
        users += [f"cuenta {a.alias}" for a in self.ctx.vault.accounts if a.macro_profile == name]
        self.used_by.setText((t("La usan: ") + ", ".join(users)) if users else
                             t("Nadie la usa todavía: asígnala en un perfil de juego o al editar una cuenta."))

    def refresh_targets(self) -> None:
        current = self.target.currentData()
        items = [("", t("Ninguna (donde esté el foco)"))]
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

    def select_target(self, inst_id: str) -> None:
        self.refresh_targets()
        idx = self.target.findData(inst_id)
        if idx >= 0:
            self.target.setCurrentIndex(idx)

    # ------------------------------------------------------------------ grabación
    def _ignored_vks(self) -> set[int]:
        vks = set()
        for key in ("macro_record", "macro_stop", "macro_play", "clicker"):
            parsed = parse_hotkey(self.ctx.cfg.get(f"hotkeys.{key}", ""))
            if parsed:
                vks.add(parsed[1])
        return vks

    def toggle_record(self) -> None:
        if self.ctx.recorder.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        if self.ctx.player.playing:
            self.ctx.player.stop()
        self.ctx.recorder.start(self._ignored_vks(), bool(self.ctx.cfg.get("macro.record_moves")),
                                int(self.ctx.cfg.get("macro.move_throttle_ms", 15)))

    def stop_recording(self) -> None:
        events = self.ctx.recorder.stop()
        if not events:
            self.ctx.notify.emit("warning", t("La grabación estaba vacía y no se guardó"))
            return
        name = time.strftime("Grabación %Y-%m-%d %H.%M.%S")
        game_id = self._filter_game()
        self.ctx.profiles.save(name, events, {"game_id": game_id})
        game = self.ctx.games.get(game_id) if game_id else None
        where = t(" en «{0}»", game.name) if game else ""
        self.ctx.notify.emit("info", t("Macro guardada como «{0}»{1} ({2} eventos)", name, where, len(events)))
        self.ctx.profiles_changed.emit()
        self.refresh(select=name)

    # ------------------------------------------------------------------ reproducción
    def play_selected(self) -> None:
        name = self.selected_name()
        if not name:
            return
        inst = self.ctx.manager.get(self.target.currentData() or "")
        self.play(name, inst)

    def play(self, name: str, inst=None) -> bool:
        if self.ctx.recorder.recording:
            return False
        if self.ctx.player.playing:
            self.ctx.notify.emit("warning", t("Ya hay una macro reproduciéndose; párala primero"))
            return False
        try:
            events = self.ctx.profiles.load(name)["events"]
        except Exception as exc:
            self.ctx.notify.emit("error", t("No se pudo cargar la macro «{0}»: {1}", name, exc))
            return False
        m = self.ctx.cfg.section("macro")
        return self.ctx.player.play(name, events, m.get("speed", 1.0), m.get("repeat", 1),
                                    m.get("loop_delay_ms", 500), m.get("relative_mouse", False), inst,
                                    m.get("focus_target", True))

    def stop_all(self) -> None:
        if self.ctx.recorder.recording:
            self.stop_recording()
        self.ctx.player.stop()

    def _update_state(self, *_):
        rec, play = self.ctx.recorder.recording, self.ctx.player.playing
        if rec:
            self.state.setText(t("● Grabando… pulsa Parar o la hotkey para terminar"))
            self.state.setStyleSheet("color: #E2231A; font-weight: 700;")
        elif play:
            self.state.setText(t("▶ Reproduciendo «{0}»", self.ctx.player.current_name))
            self.state.setStyleSheet("color: #02B757; font-weight: 700;")
        else:
            self.state.setText(t("Listo"))
            self.state.setStyleSheet("font-weight: 700;")
        self.rec_btn.setText(t("Terminar grabación") if rec else t("Grabar"))
        self.play_btn.setEnabled(not rec and not play)

    # ------------------------------------------------------------------ gestión de perfiles
    def set_hotkey(self, key: str, text: str) -> None:
        self.ctx.cfg.set(f"hotkeys.{key}", text)
        self.ctx.hotkeys.set_binding(key, text)

    def rename(self) -> None:
        name = self.selected_name()
        if not name:
            return
        new, ok = QInputDialog.getText(self, t("Renombrar"), t("Nuevo nombre:"), text=name)
        new = new.strip()
        if not ok or not new or new == name:
            return
        try:
            self.ctx.profiles.rename(name, new)
        except Exception as exc:
            QMessageBox.warning(self, t("Renombrar"), str(exc))
            return
        for acc in self.ctx.vault.accounts:
            if acc.macro_profile == name:
                acc.macro_profile = new
        self.ctx.vault.save()
        for game in self.ctx.games.all():
            if game.macro_profile == name:
                game.macro_profile = new
                self.ctx.games.upsert(game)
        self.ctx.profiles_changed.emit()
        self.ctx.accounts_changed.emit()
        self.ctx.games_changed.emit()
        self.refresh(select=new)

    def duplicate(self) -> None:
        name = self.selected_name()
        if name:
            new = self.ctx.profiles.duplicate(name)
            self.ctx.profiles_changed.emit()
            self.refresh(select=new)

    def delete(self) -> None:
        name = self.selected_name()
        if not name or QMessageBox.question(self, t("Eliminar"), t("¿Eliminar el perfil «{0}»?", name)) != QMessageBox.Yes:
            return
        self.ctx.profiles.delete(name)
        self.ctx.profiles_changed.emit()

    def import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, t("Importar macro"), "", t("Macro JSON (*.json)"))
        if not path:
            return
        try:
            name = self.ctx.profiles.import_file(path)
        except Exception as exc:
            QMessageBox.warning(self, t("Importar"), t("No se pudo importar: {0}", exc))
            return
        self.ctx.profiles_changed.emit()
        self.refresh(select=name)

    def export_profile(self) -> None:
        name = self.selected_name()
        if not name:
            return
        path, _ = QFileDialog.getSaveFileName(self, t("Exportar macro"), f"{name}.json", t("Macro JSON (*.json)"))
        if path:
            self.ctx.profiles.export_file(name, path)
