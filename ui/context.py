"""Contexto compartido entre pestañas: servicios del núcleo + señales de la aplicación."""
import time

from PySide6.QtCore import QObject, Signal

from core.anti_afk import AntiAfk
from core.autoclicker import AutoClicker
from core.instance_manager import InstanceManager
from core.launcher import parse_target
from core.macro import MacroPlayer, MacroRecorder
from storage.config import Config
from storage.games import GameProfileStore
from storage.profiles import MacroProfileStore
from storage.vault import Vault
from ui.avatars import AvatarCache
from utils.hotkeys import HotkeyManager


class AppContext(QObject):
    accounts_changed = Signal()
    games_changed = Signal()
    profiles_changed = Signal()
    presets_changed = Signal()
    navigate = Signal(str)
    notify = Signal(str, str)            # nivel, texto (para el panel y la bandeja)
    theme_changed = Signal(str)

    def __init__(self, config: Config, vault: Vault):
        super().__init__()
        self.cfg = config
        self.vault = vault
        self.profiles = MacroProfileStore()
        self.manager = InstanceManager(config)
        self.anti_afk = AntiAfk(self.manager, config)
        self.clicker = AutoClicker()
        self.recorder = MacroRecorder()
        self.player = MacroPlayer()
        self.hotkeys = HotkeyManager()
        self.avatars = AvatarCache(config, vault)
        self.games = GameProfileStore()
        self.manager.notify.connect(self.notify)

    def launch_game(self, game_id: str) -> str | None:
        """Lanza las cuentas de un perfil de juego. Devuelve un mensaje de error o None."""
        game = self.games.get(game_id)
        if not game:
            return "El perfil de juego ya no existe."
        accounts = [a for a in (self.vault.get(i) for i in game.account_ids) if a]
        if not accounts:
            return f"«{game.name}» no tiene cuentas asignadas. Edítalo y marca las cuentas que deben entrar."
        try:
            target = parse_target(game.link, game.job_id, game.private_code)
        except ValueError as exc:
            return f"El enlace de «{game.name}» no es válido: {exc}"
        game.last_played = time.time()
        self.games.upsert(game)
        self.cfg.set("launched_once", True)
        self.manager.launch(accounts, target, profile=game)
        self.games_changed.emit()
        return None

    def macro_for(self, inst) -> tuple[str, str]:
        """(macro, preset de autoclicker) que corresponden a una instancia: primero su perfil de juego."""
        game = self.games.get(inst.profile_id) if inst.profile_id else None
        if game and (game.macro_profile or game.clicker_preset):
            return game.macro_profile, game.clicker_preset
        return inst.account.macro_profile, inst.account.clicker_preset

    def auto_run_for(self, inst) -> tuple[str, str] | None:
        """Qué iniciar automáticamente al entrar en juego (None = nada)."""
        game = self.games.get(inst.profile_id) if inst.profile_id else None
        enabled = game.auto_run if game else inst.account.auto_macro
        return self.macro_for(inst) if enabled else None

    def start(self) -> None:
        self.manager.start()
        self.anti_afk.start()
        for name, combo in self.cfg.get("hotkeys", {}).items():
            self.hotkeys.set_binding(name, combo)
        self.hotkeys.start()

    def shutdown(self) -> None:
        self.clicker.stop()
        self.player.stop()
        if self.recorder.recording:
            self.recorder.stop()
        self.hotkeys.stop()
        self.anti_afk.shutdown()
        self.manager.shutdown()
        self.cfg.save_if_dirty()
