"""Perfiles de juego en %APPDATA%\\RbxFarmManager\\games.json (no contiene secretos)."""
import json
import logging
import os
import threading
import time

from core.models import GameProfile
from utils.paths import app_dir

log = logging.getLogger(__name__)


class GameProfileStore:
    def __init__(self):
        self.path = app_dir() / "games.json"
        self._lock = threading.RLock()
        self._games: list[GameProfile] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text("utf-8"))
            self._games = [GameProfile.from_dict(g) for g in data.get("games", [])]
        except Exception as exc:
            log.error("games.json dañado, se ignora: %s", exc)

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"games": [g.to_dict() for g in self._games]}, indent=2,
                                      ensure_ascii=False), "utf-8")
            os.replace(tmp, self.path)

    def all(self) -> list[GameProfile]:
        """Ordenados por último uso (los más recientes primero), como «Continuar jugando»."""
        with self._lock:
            return sorted(self._games, key=lambda g: (g.last_played, g.created), reverse=True)

    def get(self, game_id: str) -> GameProfile | None:
        return next((g for g in self._games if g.id == game_id), None)

    def upsert(self, game: GameProfile) -> None:
        with self._lock:
            for i, existing in enumerate(self._games):
                if existing.id == game.id:
                    self._games[i] = game
                    break
            else:
                self._games.append(game)
            self.save()

    def delete(self, game_id: str) -> None:
        with self._lock:
            self._games = [g for g in self._games if g.id != game_id]
            self.save()

    def duplicate(self, game_id: str) -> GameProfile | None:
        original = self.get(game_id)
        if not original:
            return None
        data = original.to_dict()
        data.pop("id")
        data.update(name=f"{original.name} (copia)", created=time.time(), last_played=0.0)
        copy = GameProfile.from_dict(data)
        self.upsert(copy)
        return copy

    def forget_account(self, account_id: str) -> None:
        with self._lock:
            for game in self._games:
                if account_id in game.account_ids:
                    game.account_ids.remove(account_id)
            self.save()
