"""Diálogo para crear o editar un perfil de juego."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QVBoxLayout)

from core import roblox_api
from core.launcher import parse_target
from core.models import GameProfile
from ui.context import AppContext
from ui.icons import G
from ui.widgets import Avatar, GameCover, make_card, muted_label, styled_button
from ui.workers import run_async


class GameProfileDialog(QDialog):
    def __init__(self, ctx: AppContext, game: GameProfile | None = None, parent=None,
                 preset_link: str = "", preset_accounts: list[str] | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.game = GameProfile.from_dict(game.to_dict()) if game else GameProfile(name="", link=preset_link)
        if preset_accounts and not game:
            self.game.account_ids = list(preset_accounts)
        self.setWindowTitle("Editar perfil de juego" if game else "Nuevo perfil de juego")
        self.setMinimumWidth(720)
        g = self.game

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)

        # ---------------- cabecera: portada + nombre + enlace
        card, lay = make_card(16, 10)
        top = QHBoxLayout()
        top.setSpacing(16)
        self.cover = GameCover(g.name or "nuevo", 120, 120)
        top.addWidget(self.cover, 0, Qt.AlignTop)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        self.name = QLineEdit(g.name)
        self.name.setPlaceholderText("Nombre del perfil (se rellena solo al detectar el juego)")
        self.link = QLineEdit(g.link)
        self.link.setPlaceholderText("PlaceId o enlace del juego / servidor privado / share")
        self.link.editingFinished.connect(self._auto_detect)
        link_row = QHBoxLayout()
        link_row.addWidget(self.link, 1)
        self.detect_btn = styled_button("Detectar", "", self.detect, icon=G.SYNC)
        self.detect_btn.setToolTip("Busca en Roblox el nombre y el icono del juego")
        link_row.addWidget(self.detect_btn)
        self.job = QLineEdit(g.job_id)
        self.job.setPlaceholderText("Opcional: entrar a un servidor concreto")
        self.private = QLineEdit(g.private_code)
        self.private.setPlaceholderText("Opcional: código de servidor privado (linkCode)")
        form.addRow("Nombre", self.name)
        form.addRow("Juego", link_row)
        form.addRow("JobId", self.job)
        form.addRow("Servidor privado", self.private)
        top.addLayout(form, 1)
        lay.addLayout(top)
        self.detect_status = muted_label("")
        lay.addWidget(self.detect_status)
        outer.addWidget(card)

        # ---------------- cuentas + automatización
        cols = QHBoxLayout()
        cols.setSpacing(12)

        card, lay = make_card(14, 8)
        head = QHBoxLayout()
        title = QLabel("Cuentas que entran")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.count_label = muted_label("")
        head.addWidget(self.count_label)
        lay.addLayout(head)
        self.accounts = QListWidget()
        self.accounts.setIconSize(QSize(28, 28))
        self.accounts.setMinimumHeight(220)
        for acc in ctx.vault.accounts:
            item = QListWidgetItem(f"{acc.alias}" + (f"   @{acc.username}" if acc.username else ""))
            item.setData(Qt.UserRole, acc.id)
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked if acc.id in g.account_ids else Qt.Unchecked)
            avatar = Avatar(acc.initials, acc.alias, 28)
            avatar.set_photo(ctx.avatars.pixmap(acc))
            item.setIcon(avatar.grab())
            self.accounts.addItem(item)
        self.accounts.itemChanged.connect(lambda _: self._update_count())
        lay.addWidget(self.accounts)
        if not ctx.vault.accounts:
            lay.addWidget(muted_label("Todavía no tienes cuentas. Agrégalas en Inicio y vuelve aquí."))
        links = QHBoxLayout()
        links.addWidget(styled_button("Todas", "", lambda: self._check_all(True)))
        links.addWidget(styled_button("Ninguna", "", lambda: self._check_all(False)))
        links.addStretch(1)
        lay.addLayout(links)
        cols.addWidget(card, 1)

        card, lay = make_card(14, 8)
        title = QLabel("Automatización")
        title.setObjectName("CardTitle")
        lay.addWidget(title)
        form = QFormLayout()
        form.setHorizontalSpacing(10)
        self.macro = QComboBox()
        self.macro.addItem("(ninguna)", "")
        own = ctx.profiles.names_for_game(g.id) if game else []
        for name in own:
            self.macro.addItem(f"★ {name}", name)
        for name in ctx.profiles.names():
            if name not in own:
                self.macro.addItem(name, name)
        self.macro.setCurrentIndex(max(0, self.macro.findData(g.macro_profile)))
        self.clicker = QComboBox()
        self.clicker.addItem("(ninguno)", "")
        for name in sorted(ctx.cfg.get("clicker_presets", {}).keys()):
            self.clicker.addItem(name, name)
        self.clicker.setCurrentIndex(max(0, self.clicker.findData(g.clicker_preset)))
        form.addRow("Macro", self.macro)
        form.addRow("Autoclicker", self.clicker)
        lay.addLayout(form)
        self.auto_run = QCheckBox("Iniciarlos solos al entrar al servidor")
        self.auto_run.setChecked(g.auto_run)
        self.anti_afk = QCheckBox("Anti-AFK activado")
        self.anti_afk.setChecked(g.anti_afk)
        self.reconnect = QCheckBox("Reconectar si se cae")
        self.reconnect.setChecked(g.auto_reconnect)
        for box in (self.auto_run, self.anti_afk, self.reconnect):
            lay.addWidget(box)
        lay.addWidget(muted_label("★ = macros guardadas en este juego. Si no eliges nada, se usa la "
                                  "macro de cada cuenta."))
        lay.addWidget(QLabel("Notas"))
        self.notes = QPlainTextEdit(g.notes)
        self.notes.setFixedHeight(60)
        lay.addWidget(self.notes)
        lay.addStretch(1)
        cols.addWidget(card, 1)
        outer.addLayout(cols)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(styled_button("Cancelar", "", self.reject))
        save = styled_button("Guardar perfil", "secondary", self._save, icon=G.CHECK)
        save.setDefault(True)
        row.addWidget(save)
        outer.addLayout(row)

        self._update_count()
        self._refresh_cover()
        ctx.avatars.updated.connect(self._image_updated)

    # ------------------------------------------------------------------ helpers
    def _check_all(self, on: bool) -> None:
        for i in range(self.accounts.count()):
            self.accounts.item(i).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _checked_ids(self) -> list[str]:
        return [self.accounts.item(i).data(Qt.UserRole) for i in range(self.accounts.count())
                if self.accounts.item(i).checkState() == Qt.Checked]

    def _update_count(self) -> None:
        n = len(self._checked_ids())
        self.count_label.setText(f"{n} seleccionada{'s' if n != 1 else ''}")

    def _place_id(self) -> int:
        try:
            return parse_target(self.link.text(), self.job.text(), self.private.text()).place_id
        except ValueError:
            return 0

    def _refresh_cover(self) -> None:
        self.cover.seed = self.name.text() or self.link.text() or "nuevo"
        self.cover.set_photo(self.ctx.avatars.game_icon(self._place_id()))

    def _image_updated(self, kind: str, key: str) -> None:
        if kind == "game" and key == str(self._place_id()):
            self._refresh_cover()

    def _auto_detect(self) -> None:
        if self.link.text().strip() and not self.name.text().strip():
            self.detect()
        else:
            self._refresh_cover()

    def detect(self) -> None:
        place_id = self._place_id()
        if not place_id:
            self.detect_status.setText("Pega un PlaceId o un enlace de juego válido para detectarlo.")
            return
        self.detect_btn.setEnabled(False)
        self.detect_status.setText("Buscando el juego en Roblox…")
        self._refresh_cover()

        def done(info: dict):
            self.detect_btn.setEnabled(True)
            if not self.name.text().strip():
                self.name.setText(info["name"])
            extra = f" · de {info['creator']}" if info.get("creator") else ""
            self.detect_status.setText(f"✔ {info['name']}{extra} · {info.get('playing', 0):,} jugando ahora"
                                       .replace(",", "."))
            self._refresh_cover()

        def fail(exc):
            self.detect_btn.setEnabled(True)
            self.detect_status.setText(f"No se pudo detectar: {exc}")

        run_async(roblox_api.game_info, place_id, on_done=done, on_error=fail)

    def _save(self) -> None:
        try:
            target = parse_target(self.link.text(), self.job.text(), self.private.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Enlace no válido", str(exc))
            return
        name = self.name.text().strip() or target.label
        g = self.game
        g.name = name
        g.link = self.link.text().strip()
        g.job_id = self.job.text().strip()
        g.private_code = self.private.text().strip()
        g.place_id = target.place_id
        g.account_ids = self._checked_ids()
        g.macro_profile = self.macro.currentData()
        g.clicker_preset = self.clicker.currentData()
        g.auto_run = self.auto_run.isChecked()
        g.anti_afk = self.anti_afk.isChecked()
        g.auto_reconnect = self.reconnect.isChecked()
        g.notes = self.notes.toPlainText().strip()
        self.accept()
