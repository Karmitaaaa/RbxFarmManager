"""Caché de imágenes de Roblox (fotos de avatar e iconos de juegos).

Se descargan de roblox.com en segundo plano (datos públicos, sin cookie) y se guardan en disco.
"""
import logging
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

from core import roblox_api
from core.models import Account
from storage.config import Config
from storage.vault import Vault
from ui.workers import run_async
from utils.paths import avatars_dir

log = logging.getLogger("imagenes")

REFRESH_AFTER_S = 24 * 3600   # vuelve a descargar una vez al día
RETRY_AFTER_S = 10 * 60       # tras un fallo, espera antes de reintentar


def _download_avatar(user_id: int, username: str) -> int:
    if not user_id:
        user_id = roblox_api.resolve_user_id(username)
    (avatars_dir() / f"{user_id}.png").write_bytes(roblox_api.fetch_headshot(user_id))
    return user_id


def _download_game_icon(place_id: int) -> int:
    (avatars_dir() / f"game_{place_id}.png").write_bytes(roblox_api.fetch_game_icon(place_id))
    return place_id


class AvatarCache(QObject):
    updated = Signal(str, str)  # ("account", id de cuenta) | ("game", place_id)

    def __init__(self, config: Config, vault: Vault):
        super().__init__()
        self.cfg = config
        self.vault = vault
        self._pixmaps: dict[str, tuple[float, QPixmap]] = {}
        self._pending: set[str] = set()
        self._failed: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("download_avatars", True))

    def _from_disk(self, path) -> QPixmap | None:
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
        cached = self._pixmaps.get(str(path))
        if cached is None or cached[0] != mtime:
            cached = (mtime, QPixmap(str(path)))
            self._pixmaps[str(path)] = cached
        return None if cached[1].isNull() else cached[1]

    def _stale(self, path) -> bool:
        return not path.exists() or time.time() - path.stat().st_mtime > REFRESH_AFTER_S

    def _can_fetch(self, key: str) -> bool:
        return key not in self._pending and time.time() - self._failed.get(key, 0) >= RETRY_AFTER_S

    # ------------------------------------------------------------------ avatares
    def pixmap(self, account: Account | None) -> QPixmap | None:
        """Foto del avatar si ya está en disco; si falta o está vieja, la pide en segundo plano."""
        if account is None or not self.enabled:
            return None
        path = avatars_dir() / f"{account.user_id}.png" if account.user_id else None
        if (path is None or self._stale(path)) and (account.user_id or account.username):
            self._fetch_avatar(account)
        return self._from_disk(path) if path is not None else None

    def _fetch_avatar(self, account: Account) -> None:
        key = f"account:{account.id}"
        if not self._can_fetch(key):
            return
        self._pending.add(key)
        acc_id, alias = account.id, account.alias

        def done(user_id: int):
            self._pending.discard(key)
            acc = self.vault.get(acc_id)
            if acc is not None and acc.user_id != user_id:
                acc.user_id = user_id
                self.vault.save()
            self.updated.emit("account", acc_id)

        def fail(exc: Exception):
            self._pending.discard(key)
            self._failed[key] = time.time()
            log.debug("No se pudo descargar el avatar de %s: %s", alias, exc)

        run_async(_download_avatar, account.user_id, account.username, on_done=done, on_error=fail)

    # ------------------------------------------------------------------ juegos
    def game_icon(self, place_id: int) -> QPixmap | None:
        if not place_id or not self.enabled:
            return None
        path = avatars_dir() / f"game_{place_id}.png"
        key = f"game:{place_id}"
        if self._stale(path) and self._can_fetch(key):
            self._pending.add(key)

            def done(pid: int):
                self._pending.discard(key)
                self.updated.emit("game", str(pid))

            def fail(exc: Exception):
                self._pending.discard(key)
                self._failed[key] = time.time()
                log.debug("No se pudo descargar el icono del juego %s: %s", place_id, exc)

            run_async(_download_game_icon, place_id, on_done=done, on_error=fail)
        return self._from_disk(path)
