"""Pestaña Juegos: perfiles de juego en tarjetas (crear, editar, jugar)."""
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget

from core.models import ACTIVE_STATES, ST_INGAME
from ui.context import AppContext
from ui.game_dialog import GameProfileDialog
from ui.icons import G
from ui.widgets import AddCard, EmptyState, FlowLayout, GameCard, Page, clear_layout
from utils.i18n import t

log = logging.getLogger("juegos")


def game_subtitle(ctx: AppContext, game) -> str:
    n = sum(1 for i in game.account_ids if ctx.vault.get(i))
    parts = [f"{n} cuenta{'s' if n != 1 else ''}"]
    if game.macro_profile:
        parts.append(t("macro «{0}»", game.macro_profile))
    elif game.clicker_preset:
        parts.append(t("clicker «{0}»", game.clicker_preset))
    if game.private_code or "privateServerLinkCode" in game.link or "/share" in game.link:
        parts.append("privado")
    return " · ".join(parts)


class GameActions:
    """Acciones comunes de un perfil de juego (las usan Inicio y Juegos)."""

    def __init__(self, ctx: AppContext, parent: QWidget):
        self.ctx, self.parent = ctx, parent

    def new(self, link: str = "", accounts: list[str] | None = None) -> None:
        dlg = GameProfileDialog(self.ctx, None, self.parent, preset_link=link, preset_accounts=accounts)
        if dlg.exec():
            self.ctx.games.upsert(dlg.game)
            log.info(t("Perfil de juego creado: %s"), dlg.game.name)
            self.ctx.games_changed.emit()

    def edit(self, game_id: str) -> None:
        game = self.ctx.games.get(game_id)
        if not game:
            return
        dlg = GameProfileDialog(self.ctx, game, self.parent)
        if dlg.exec():
            self.ctx.games.upsert(dlg.game)
            self.ctx.games_changed.emit()

    def play(self, game_id: str) -> None:
        error = self.ctx.launch_game(game_id)
        if error:
            QMessageBox.information(self.parent, t("Jugar"), error)
            game = self.ctx.games.get(game_id)
            if game and not any(self.ctx.vault.get(i) for i in game.account_ids):
                self.edit(game_id)
            return
        self.ctx.navigate.emit("instances")

    def menu(self, game_id: str) -> None:
        game = self.ctx.games.get(game_id)
        if not game:
            return
        m = QMenu(self.parent)
        m.addAction(t("Jugar"), lambda: self.play(game_id))
        m.addAction(t("Editar perfil…"), lambda: self.edit(game_id))
        m.addAction(t("Ver sus macros"), lambda: self.ctx.navigate.emit(f"macros:{game_id}"))
        m.addAction(t("Duplicar"), lambda: (self.ctx.games.duplicate(game_id), self.ctx.games_changed.emit()))
        m.addSeparator()
        m.addAction(t("Cerrar sus instancias"), lambda: self.close_instances(game_id))
        m.addAction(t("Eliminar perfil"), lambda: self.delete(game_id))
        m.exec(QCursor.pos())

    def close_instances(self, game_id: str) -> None:
        for inst in self.ctx.manager.snapshot():
            if inst.profile_id == game_id and inst.status in ACTIVE_STATES:
                self.ctx.manager.close(inst.id)

    def delete(self, game_id: str) -> None:
        game = self.ctx.games.get(game_id)
        if game and QMessageBox.question(self.parent, t("Eliminar perfil"),
                                         t("¿Eliminar el perfil «{0}»?\nLas cuentas y macros no se borran.", game.name)
                                         ) == QMessageBox.Yes:
            self.ctx.games.delete(game_id)
            self.ctx.games_changed.emit()

    def build_card(self, game, width: int = 190) -> GameCard:
        card = GameCard(game, game_subtitle(self.ctx, game), width)
        card.set_photo(self.ctx.avatars.game_icon(game.place_id))
        card.play_clicked.connect(self.play)
        card.edit_clicked.connect(self.edit)
        card.menu_clicked.connect(self.menu)
        return card


def update_card_status(ctx: AppContext, cards: dict) -> None:
    counts: dict[str, list[int]] = {}
    for inst in ctx.manager.snapshot():
        if inst.profile_id and inst.status in ACTIVE_STATES:
            c = counts.setdefault(inst.profile_id, [0, 0])
            c[1] += 1
            c[0] += inst.status == ST_INGAME
    for game_id, card in cards.items():
        card.set_status(*counts.get(game_id, [0, 0]))


class GamesTab(Page):
    def __init__(self, ctx: AppContext):
        super().__init__(max_width=1240)
        self.ctx = ctx
        self.actions = GameActions(ctx, self)
        self.cards: dict[str, GameCard] = {}

        self.empty = EmptyState(G.GAME, t("Aún no tienes perfiles de juego"),
                                t("Un perfil guarda el juego (o servidor privado), qué cuentas entran y qué macro "
                                "usan. Después basta con pulsar «Jugar»."),
                                t("Crear mi primer perfil"), self.actions.new, G.ADD)
        self.body.addWidget(self.empty)
        self.grid_host = QWidget()
        self.grid = FlowLayout(16)
        self.grid_host.setLayout(self.grid)
        self.body.addWidget(self.grid_host)
        self.body.addStretch(1)

        ctx.games_changed.connect(self.refresh)
        ctx.accounts_changed.connect(self.refresh)
        ctx.manager.changed.connect(lambda: update_card_status(ctx, self.cards))
        ctx.avatars.updated.connect(self._image_updated)
        self.refresh()

    def refresh(self) -> None:
        clear_layout(self.grid)
        self.cards = {}
        games = self.ctx.games.all()
        for game in games:
            card = self.actions.build_card(game, 200)
            self.grid.addWidget(card)
            self.cards[game.id] = card
        if games:
            add = AddCard(t("Nuevo perfil de juego"), 200, self.cards[games[0].id].sizeHint().height())
            add.clicked.connect(self.actions.new)
            self.grid.addWidget(add)
        self.empty.setVisible(not games)
        self.grid_host.setVisible(bool(games))
        update_card_status(self.ctx, self.cards)

    def _image_updated(self, kind: str, key: str) -> None:
        if kind != "game":
            return
        for game in self.ctx.games.all():
            if str(game.place_id) == key and game.id in self.cards:
                self.cards[game.id].set_photo(self.ctx.avatars.game_icon(game.place_id))
