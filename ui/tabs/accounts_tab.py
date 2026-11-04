"""Pestaña Inicio: portada al estilo «Home» clásico (saludo, primeros pasos, juegos y cuentas)."""
import logging
import os
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMenu, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from core.launcher import parse_target
from core.models import LOGIN_METHODS, ST_INGAME, ST_LAUNCHING, ST_OPEN, ST_WAIT_RECONNECT
from storage import crypto
from ui import theme
from ui.context import AppContext
from ui.dialogs import AccountDialog, PasswordDialog
from ui.icons import G, icon_font
from ui.tabs.games_tab import GameActions, update_card_status
from ui.widgets import (AddCard, Avatar, AvatarTile, GameCard, HStrip, IconCircle, Page, SectionHeader, clear_layout,
                        link_button, make_card, muted_label, styled_button)

log = logging.getLogger("cuentas")

COLS = ["", "Alias", "Usuario", "Inicio de sesión", "Etiquetas", "Macro", "Notas"]


def greeting(hour: int | None = None) -> str:
    hour = time.localtime().tm_hour if hour is None else hour
    if 5 <= hour < 12:
        return "Buenos días"
    if 12 <= hour < 20:
        return "Buenas tardes"
    return "Buenas noches"


class ClickableAvatar(Avatar):
    clicked = Signal()

    def __init__(self, *args):
        super().__init__(*args)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class AccountsTab(Page):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.selected: set[str] = set()
        self.filter_text = ""
        self._updating = False
        self.tiles: dict[str, AvatarTile] = {}

        # ---------------- Saludo con la cuenta principal
        hello_row = QHBoxLayout()
        hello_row.setContentsMargins(0, 8, 0, 0)
        self.hello_avatar = ClickableAvatar("RF", "RbxFarm", 104)
        self.hello_avatar.setToolTip("Clic para elegir la cuenta principal")
        self.hello_avatar.clicked.connect(self._choose_main_menu)
        hello_row.addWidget(self.hello_avatar)
        hello_text = QVBoxLayout()
        hello_text.setSpacing(2)
        hello_text.addStretch(1)
        self.hello_title = QLabel()
        self.hello_title.setObjectName("Hello")
        self.hello_user = QLabel()
        self.hello_user.setStyleSheet("font-size: 12pt; font-weight: 600;")
        self.hello_sub = QLabel()
        self.hello_sub.setObjectName("HelloSub")
        hello_text.addWidget(self.hello_title)
        hello_text.addWidget(self.hello_user)
        hello_text.addWidget(self.hello_sub)
        hello_text.addStretch(1)
        hello_row.addSpacing(14)
        hello_row.addLayout(hello_text, 1)
        self.body.addLayout(hello_row)

        # ---------------- Primeros pasos
        self.onboarding, lay = make_card(18, 10)
        head = QHBoxLayout()
        head.addWidget(IconCircle(G.FLASH, 36, theme.ACCENTS["green"]))
        head_text = QVBoxLayout()
        head_text.setSpacing(0)
        title = QLabel("Primeros pasos")
        title.setObjectName("CardTitle")
        head_text.addWidget(title)
        head_text.addWidget(muted_label("Sigue estos pasos una vez y después solo tendrás que pulsar «Jugar»."))
        head.addLayout(head_text, 1)
        head.addWidget(link_button("Ocultar", self._hide_onboarding))
        lay.addLayout(head)
        self.steps = QVBoxLayout()
        self.steps.setSpacing(4)
        lay.addLayout(self.steps)
        self.body.addWidget(self.onboarding)

        # ---------------- Continuar jugando (perfiles de juego)
        self.game_actions = GameActions(ctx, self)
        self.game_cards: dict[str, GameCard] = {}
        games_header = SectionHeader("Continuar jugando")
        games_header.add_link("Ver todos", lambda: ctx.navigate.emit("games"))
        games_header.add_link("+ Nuevo perfil", lambda: self.game_actions.new())
        self.body.addWidget(games_header)
        self.games_strip = HStrip(318)
        self.body.addWidget(self.games_strip)

        # ---------------- Cuentas (avatares)
        self.accounts_header = SectionHeader("Cuentas (0)")
        self.accounts_header.add_link("Todas", self.select_all)
        self.accounts_header.add_link("Ninguna", self.select_none)
        self.accounts_header.add_link("+ Agregar", self.add_account)
        self.body.addWidget(self.accounts_header)
        card, lay = make_card(14, 6)
        self.strip = HStrip(116)
        lay.addWidget(self.strip)
        self.empty_hint = muted_label("Aún no hay cuentas. Pulsa «+ Agregar» para crear la primera.")
        lay.addWidget(self.empty_hint)
        legend = muted_label("Clic en un avatar para seleccionarlo · doble clic para editar · "
                             "punto verde = en juego, azul = abriendo, naranja = reconectando")
        legend.setStyleSheet("font-size: 8.5pt;")
        lay.addWidget(legend)
        self.body.addWidget(card)

        # ---------------- Juego rápido (sin perfil)
        quick_header = SectionHeader("Juego rápido")
        quick_header.add_link("Guardar como perfil de juego",
                              lambda: self.game_actions.new(self.link.text().strip(), list(self.selected)))
        self.body.addWidget(quick_header)
        card, lay = make_card(16, 10)
        lay.addWidget(muted_label("Para probar un juego una vez con las cuentas seleccionadas arriba. Si lo vas a "
                                  "repetir, guárdalo como perfil de juego."))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.link = QLineEdit(ctx.cfg.get("last_link", ""))
        self.link.setPlaceholderText("PlaceId o enlace: https://www.roblox.com/games/123456/…  "
                                     "(también enlaces de servidor privado o /share?code=…)")
        self.job = QLineEdit()
        self.job.setPlaceholderText("JobId (opcional) para entrar a un servidor concreto")
        self.private_chk = QCheckBox("Servidor privado")
        self.private_code = QLineEdit()
        self.private_code.setPlaceholderText("Código del servidor privado (linkCode)")
        self.private_code.setEnabled(False)
        self.private_chk.toggled.connect(self.private_code.setEnabled)
        grid.addWidget(QLabel("Juego"), 0, 0)
        grid.addWidget(self.link, 0, 1, 1, 3)
        grid.addWidget(QLabel("Servidor"), 1, 0)
        grid.addWidget(self.job, 1, 1)
        grid.addWidget(self.private_chk, 1, 2)
        grid.addWidget(self.private_code, 1, 3)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(3, 2)
        lay.addLayout(grid)
        play_row = QHBoxLayout()
        self.play_hint = muted_label("")
        play_row.addWidget(self.play_hint, 1)
        self.play_btn = styled_button("Jugar", "primary", self.launch_selected, big=True, icon=G.PLAY)
        self.play_btn.setMinimumWidth(220)
        play_row.addWidget(self.play_btn)
        lay.addLayout(play_row)
        self.body.addWidget(card)

        # ---------------- Tabla de cuentas
        table_header = SectionHeader("Detalle de cuentas")
        table_header.add_link("Editar", self.edit_current)
        table_header.add_link("Eliminar", self.delete_selected)
        table_header.add_link("Importar", self.import_accounts)
        table_header.add_link("Exportar", self.export_accounts)
        self.body.addWidget(table_header)
        card, lay = make_card(0, 0)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.setMinimumHeight(260)
        self.table.itemChanged.connect(self._table_item_changed)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.edit_account(self._row_id(r)))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        lay.addWidget(self.table)
        self.body.addWidget(card)
        self.body.addStretch(1)

        ctx.accounts_changed.connect(self.refresh)
        ctx.accounts_changed.connect(lambda: self.refresh_games())
        ctx.manager.changed.connect(self.refresh_status)
        ctx.avatars.updated.connect(self._avatar_updated)
        self.greeting_timer = QTimer(self)
        self.greeting_timer.timeout.connect(self.refresh_hello)
        self.greeting_timer.start(60_000)  # cambia de «Buenos días» a «Buenas tardes» sin reiniciar
        ctx.games_changed.connect(self.refresh_games)
        ctx.profiles_changed.connect(self.refresh_onboarding)
        ctx.manager.changed.connect(lambda: update_card_status(ctx, self.game_cards))
        self.refresh()
        self.refresh_games()

    # ------------------------------------------------------------------ juegos y primeros pasos
    def refresh_games(self) -> None:
        self.games_strip.clear()
        self.game_cards = {}
        height = 0
        for game in self.ctx.games.all():
            card = self.game_actions.build_card(game, 178)
            self.games_strip.add(card)
            self.game_cards[game.id] = card
            height = max(height, card.sizeHint().height())
        add = AddCard("Nuevo perfil de juego", 178, height or 264)
        self.games_strip.setFixedHeight((height or 264) + 14)
        add.clicked.connect(lambda: self.game_actions.new())
        self.games_strip.add(add)
        update_card_status(self.ctx, self.game_cards)
        self.refresh_onboarding()

    def refresh_onboarding(self) -> None:
        cfg = self.ctx.cfg
        steps = [
            ("Agrega tu primera cuenta", "Con su cookie o con la sesión de Roblox que ya tengas abierta.",
             bool(self.accounts), "Agregar cuenta", self.add_account),
            ("Crea un perfil de juego", "Elige el juego (o servidor privado) y qué cuentas entran.",
             bool(self.ctx.games.all()), "Crear perfil", lambda: self.game_actions.new()),
            ("Graba una macro (opcional)", "En Macros: elige el juego en el filtro y pulsa Grabar.",
             bool(self.ctx.profiles.names()), "Ir a Macros", lambda: self.ctx.navigate.emit("macros")),
            ("Pulsa «Jugar» en la tarjeta del juego", "Se abren todas sus cuentas, con anti-AFK y reconexión.",
             bool(cfg.get("launched_once")), "", None),
        ]
        done = sum(1 for s in steps if s[2])
        self.onboarding.setVisible(not cfg.get("hide_onboarding") and done < len(steps))
        clear_layout(self.steps)
        next_pending = next((i for i, s in enumerate(steps) if not s[2]), None)
        for i, (title, text, is_done, button, slot) in enumerate(steps):
            row = QHBoxLayout()
            row.setSpacing(12)
            mark = QLabel(G.CHECK if is_done else str(i + 1))
            if is_done:
                mark.setFont(icon_font(12))
            mark.setAlignment(Qt.AlignCenter)
            mark.setFixedSize(26, 26)
            color = theme.ACCENTS["green"] if is_done else (theme.ACCENTS["blue"] if i == next_pending
                                                            else theme.ACCENTS["gray"])
            mark.setStyleSheet(f"background: {color}; color: #FFFFFF; border-radius: 13px; font-weight: 700;")
            row.addWidget(mark)
            label = QLabel(f"<b>{title}</b><br><span style='color:gray'>{text}</span>")
            if is_done:
                label.setStyleSheet("color: gray;")
            row.addWidget(label, 1)
            if button and not is_done:
                btn = styled_button(button, "secondary" if i == next_pending else "", slot)
                row.addWidget(btn)
            self.steps.addLayout(row)

    def _hide_onboarding(self) -> None:
        self.ctx.cfg.set("hide_onboarding", True)
        self.onboarding.hide()

    # ------------------------------------------------------------------ saludo
    def main_account(self):
        if not self.accounts:
            return None
        main_id = self.ctx.cfg.get("main_account_id")
        return next((a for a in self.accounts if a.id == main_id), self.accounts[0])

    def refresh_hello(self) -> None:
        acc = self.main_account()
        if acc:
            name = acc.username or acc.alias
            self.hello_avatar.text, self.hello_avatar.seed = acc.initials, acc.alias
            self.hello_avatar.set_photo(self.ctx.avatars.pixmap(acc))
            detail = f"@{acc.username}" if acc.username else acc.alias
            if acc.username and acc.alias.lower() != acc.username.lower():
                detail += f"  ·  {acc.alias}"
            self.hello_user.setText(detail + "  ·  cuenta principal")
        else:
            name = os.environ.get("USERNAME") or "jugador"
            self.hello_avatar.text, self.hello_avatar.seed = name[:2].upper(), name
            self.hello_avatar.set_photo(None)
            self.hello_user.setText("Agrega una cuenta para ver aquí su nombre y su foto")
        self.hello_title.setText(f"{greeting()}, {name}")

    def set_main_account(self, acc_id: str) -> None:
        self.ctx.cfg.set("main_account_id", acc_id)
        self.refresh_hello()

    def _choose_main_menu(self) -> None:
        if not self.accounts:
            return self.add_account()
        current = self.main_account()
        menu = QMenu(self)
        menu.addSection("Cuenta principal")
        for acc in self.accounts:
            label = f"{acc.alias} (@{acc.username})" if acc.username else acc.alias
            action = menu.addAction(label, lambda a=acc.id: self.set_main_account(a))
            action.setCheckable(True)
            action.setChecked(acc is current)
        menu.exec(QCursor.pos())

    def _avatar_updated(self, kind: str, key: str) -> None:
        if kind == "game":
            for game_id, card in self.game_cards.items():
                game = self.ctx.games.get(game_id)
                if game and str(game.place_id) == key:
                    card.set_photo(self.ctx.avatars.game_icon(game.place_id))
            return
        acc_id = key
        acc = self.ctx.vault.get(acc_id)
        if acc and acc_id in self.tiles:
            self.tiles[acc_id].set_photo(self.ctx.avatars.pixmap(acc))
        main = self.main_account()
        if main and main.id == acc_id:
            self.refresh_hello()

    # ------------------------------------------------------------------ datos
    @property
    def accounts(self):
        return self.ctx.vault.accounts

    def _visible(self, acc) -> bool:
        if not self.filter_text:
            return True
        hay = " ".join([acc.alias, acc.username, acc.notes, *acc.tags]).lower()
        return self.filter_text in hay

    def set_filter(self, text: str) -> None:
        self.filter_text = text.strip().lower()
        self.refresh()

    def selected_accounts(self):
        return [a for a in self.accounts if a.id in self.selected]

    def refresh(self) -> None:
        self._updating = True
        ids = {a.id for a in self.accounts}
        self.selected &= ids
        visible = [a for a in self.accounts if self._visible(a)]

        self.strip.clear()
        self.tiles = {}
        for acc in visible:
            tile = AvatarTile(acc.id, acc.alias, acc.initials)
            tile.set_selected(acc.id in self.selected)
            tile.set_photo(self.ctx.avatars.pixmap(acc))
            tile.toggled.connect(self._tile_toggled)
            tile.double_clicked.connect(self.edit_account)
            self.strip.add(tile)
            self.tiles[acc.id] = tile
        self.empty_hint.setVisible(not self.accounts)
        self.accounts_header.set_title(f"Cuentas ({len(self.accounts)})")

        self.table.setRowCount(len(visible))
        for row, acc in enumerate(visible):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if acc.id in self.selected else Qt.Unchecked)
            chk.setData(Qt.UserRole, acc.id)
            self.table.setItem(row, 0, chk)
            values = [acc.alias, acc.username or "—", LOGIN_METHODS.get(acc.login_method, acc.login_method),
                      ", ".join(acc.tags), acc.macro_profile or "—", acc.notes.replace("\n", " ")]
            for col, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                if col == 1:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, col, item)
        self._updating = False
        self._update_play_button()
        self.refresh_status()
        self.refresh_hello()
        self.refresh_onboarding()

    def refresh_status(self) -> None:
        running = {}
        for inst in self.ctx.manager.snapshot():
            running[inst.account.id] = inst.status
        colors = {ST_INGAME: theme.ACCENTS["green"], ST_OPEN: theme.ACCENTS["blue"],
                  ST_LAUNCHING: theme.ACCENTS["blue"], ST_WAIT_RECONNECT: theme.ACCENTS["orange"]}
        for acc_id, tile in self.tiles.items():
            tile.set_badge(colors.get(running.get(acc_id)))
        in_game = sum(1 for s in running.values() if s == ST_INGAME)
        self.hello_sub.setText(f"{len(self.accounts)} cuentas guardadas · {in_game} en juego · "
                               f"{len(self.selected)} seleccionadas")

    def _update_play_button(self) -> None:
        n = len(self.selected)
        self.play_btn.setText(f"Jugar con {n} cuenta{'s' if n != 1 else ''}" if n else "Jugar")
        self.play_btn.setEnabled(n > 0)
        self.play_hint.setText("" if n else "Selecciona una o más cuentas arriba para lanzarlas juntas.")
        self.refresh_status()

    # ------------------------------------------------------------------ selección
    def _set_selected(self, acc_id: str, on: bool) -> None:
        (self.selected.add if on else self.selected.discard)(acc_id)

    def _tile_toggled(self, acc_id: str, on: bool) -> None:
        self._set_selected(acc_id, on)
        self._updating = True
        for row in range(self.table.rowCount()):
            if self._row_id(row) == acc_id:
                self.table.item(row, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self._updating = False
        self._update_play_button()

    def _table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != 0:
            return
        acc_id = item.data(Qt.UserRole)
        on = item.checkState() == Qt.Checked
        self._set_selected(acc_id, on)
        if acc_id in self.tiles:
            self.tiles[acc_id].set_selected(on)
        self._update_play_button()

    def _row_id(self, row: int) -> str | None:
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def select_all(self) -> None:
        self.selected = {a.id for a in self.accounts if self._visible(a)}
        self.refresh()

    def select_none(self) -> None:
        self.selected = set()
        self.refresh()

    # ------------------------------------------------------------------ CRUD
    def _presets(self) -> list[str]:
        return sorted(self.ctx.cfg.get("clicker_presets", {}).keys())

    def add_account(self) -> None:
        dlg = AccountDialog(None, self.ctx.profiles.names(), self._presets(), self)
        if dlg.exec():
            self.ctx.vault.upsert(dlg.account)
            self.selected.add(dlg.account.id)
            log.info("Cuenta agregada: %s", dlg.account.alias)
            self.ctx.accounts_changed.emit()

    def edit_account(self, acc_id: str | None) -> None:
        acc = self.ctx.vault.get(acc_id) if acc_id else None
        if not acc:
            return
        dlg = AccountDialog(acc, self.ctx.profiles.names(), self._presets(), self)
        if dlg.exec():
            self.ctx.vault.upsert(dlg.account)
            self.ctx.manager.update_account(dlg.account)
            log.info("Cuenta editada: %s", dlg.account.alias)
            self.ctx.accounts_changed.emit()

    def edit_current(self) -> None:
        row = self.table.currentRow()
        if row < 0 and len(self.selected) == 1:
            return self.edit_account(next(iter(self.selected)))
        self.edit_account(self._row_id(row))

    def delete_selected(self) -> None:
        targets = list(self.selected)
        if not targets and self.table.currentRow() >= 0:
            targets = [self._row_id(self.table.currentRow())]
        if not targets:
            QMessageBox.information(self, "Eliminar", "Marca las cuentas que quieres eliminar.")
            return
        names = ", ".join(a.alias for a in self.accounts if a.id in targets)
        if QMessageBox.question(self, "Eliminar cuentas",
                                f"¿Eliminar {len(targets)} cuenta(s)?\n{names}") != QMessageBox.Yes:
            return
        self.ctx.vault.delete(targets)
        for acc_id in targets:
            self.ctx.games.forget_account(acc_id)
        self.selected -= set(targets)
        log.info("Eliminadas %d cuentas", len(targets))
        self.ctx.accounts_changed.emit()

    def _table_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        acc_id = self._row_id(row) if row >= 0 else None
        if not acc_id:
            return
        menu = QMenu(self)
        menu.addAction("Editar", lambda: self.edit_account(acc_id))
        menu.addAction("Lanzar solo esta", lambda: self.launch_accounts([self.ctx.vault.get(acc_id)]))
        menu.addAction("Marcar como cuenta principal", lambda: self.set_main_account(acc_id))
        menu.addSeparator()

        def _delete():
            self.selected = {acc_id}
            self.delete_selected()

        menu.addAction("Eliminar", _delete)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ import / export
    def export_accounts(self) -> None:
        if not self.accounts:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar cuentas cifradas", "cuentas.rbxvault",
                                              "Baúl RbxFarm (*.rbxvault)")
        if not path:
            return
        only = list(self.selected) or None
        pw = PasswordDialog.ask(self, "Contraseña de exportación",
                                "El archivo se cifrará con esta contraseña (la necesitarás para importarlo). "
                                + ("Se exportarán solo las cuentas seleccionadas." if only else
                                   "Se exportarán todas las cuentas."), confirm=True)
        if pw is None:
            return
        try:
            n = self.ctx.vault.export_to(path, pw, only)
            QMessageBox.information(self, "Exportar", f"{n} cuenta(s) exportadas cifradas.")
        except Exception as exc:
            QMessageBox.critical(self, "Exportar", f"No se pudo exportar: {exc}")

    def import_accounts(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar cuentas cifradas", "", "Baúl RbxFarm (*.rbxvault);;Todos (*.*)")
        if not path:
            return
        pw = PasswordDialog.ask(self, "Importar", "Contraseña con la que se exportó el archivo.")
        if pw is None:
            return
        try:
            added, updated = self.ctx.vault.import_from(path, pw)
        except crypto.WrongPassword:
            QMessageBox.warning(self, "Importar", "Contraseña incorrecta.")
            return
        except Exception as exc:
            QMessageBox.critical(self, "Importar", f"No se pudo importar: {exc}")
            return
        QMessageBox.information(self, "Importar", f"{added} nuevas, {updated} actualizadas.")
        self.ctx.accounts_changed.emit()

    # ------------------------------------------------------------------ lanzar
    def launch_selected(self) -> None:
        self.launch_accounts(self.selected_accounts())

    def launch_accounts(self, accounts) -> None:
        accounts = [a for a in accounts if a]
        if not accounts:
            QMessageBox.information(self, "Jugar", "Selecciona al menos una cuenta.")
            return
        try:
            target = parse_target(self.link.text(), self.job.text(),
                                  self.private_code.text() if self.private_chk.isChecked() else "")
        except ValueError as exc:
            QMessageBox.warning(self, "Jugar", str(exc))
            return
        self.ctx.cfg.set("last_link", self.link.text().strip())
        self.ctx.cfg.set("launched_once", True)
        self.ctx.manager.launch(accounts, target)
        self.refresh_onboarding()
        self.ctx.navigate.emit("instances")
