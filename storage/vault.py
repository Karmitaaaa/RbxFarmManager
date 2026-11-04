"""Baúl cifrado de cuentas. Nunca se escribe en texto plano ni sale del equipo."""
import json
import logging
import os
import threading
from pathlib import Path

from core.models import Account
from storage import crypto
from utils.paths import vault_path
from utils.i18n import t

log = logging.getLogger(__name__)


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class Vault:
    def __init__(self, path: Path | None = None):
        self.path = path or vault_path()
        self.accounts: list[Account] = []
        self.mode: str | None = None
        self._password: str | None = None
        self._lock = threading.RLock()
        self.unlocked = False

    # ------------------------------------------------------------------ estado
    def exists(self) -> bool:
        return self.path.exists()

    def stored_mode(self) -> str | None:
        if not self.exists():
            return None
        try:
            return crypto.read_envelope(self.path.read_bytes())["mode"]
        except crypto.BadFile:
            return None

    def create(self, mode: str, password: str | None = None) -> None:
        with self._lock:
            self.mode, self._password = mode, password
            self.accounts = []
            self.unlocked = True
            self.save()
        log.info(t("Baúl de cuentas creado (modo %s)"), mode)

    def unlock(self, password: str | None = None) -> None:
        with self._lock:
            raw = self.path.read_bytes()
            env = crypto.read_envelope(raw)
            data = json.loads(crypto.unseal(raw, password).decode("utf-8"))
            self.mode = env["mode"]
            self._password = password if self.mode == "password" else None
            self.accounts = [Account.from_dict(a) for a in data.get("accounts", [])]
            self.unlocked = True
        log.info(t("Baúl desbloqueado: %d cuentas"), len(self.accounts))

    def lock(self) -> None:
        with self._lock:
            self.accounts = []
            self._password = None
            self.unlocked = False

    def change_protection(self, mode: str, password: str | None = None) -> None:
        with self._lock:
            self.mode, self._password = mode, password
            self.save()
        log.info(t("Protección del baúl cambiada a %s"), mode)

    # ------------------------------------------------------------------ CRUD
    def save(self) -> None:
        with self._lock:
            if not self.unlocked:
                return
            payload = json.dumps({"accounts": [a.to_dict() for a in self.accounts]}).encode("utf-8")
            _atomic_write(self.path, crypto.seal(payload, self.mode, self._password))

    def get(self, account_id: str) -> Account | None:
        return next((a for a in self.accounts if a.id == account_id), None)

    def upsert(self, account: Account) -> None:
        with self._lock:
            for i, existing in enumerate(self.accounts):
                if existing.id == account.id:
                    self.accounts[i] = account
                    break
            else:
                self.accounts.append(account)
            self.save()

    def delete(self, account_ids: list[str]) -> None:
        with self._lock:
            self.accounts = [a for a in self.accounts if a.id not in set(account_ids)]
            self.save()

    # ------------------------------------------------------------------ import/export
    def export_to(self, path: str, password: str, account_ids: list[str] | None = None) -> int:
        with self._lock:
            chosen = [a for a in self.accounts if account_ids is None or a.id in account_ids]
            payload = json.dumps({"accounts": [a.to_dict() for a in chosen]}).encode("utf-8")
        # Las exportaciones siempre usan contraseña para poder llevarlas a otro equipo
        Path(path).write_bytes(crypto.seal(payload, "password", password))
        log.info(t("Exportadas %d cuentas cifradas a %s"), len(chosen), path)
        return len(chosen)

    def import_from(self, path: str, password: str) -> tuple[int, int]:
        data = json.loads(crypto.unseal(Path(path).read_bytes(), password).decode("utf-8"))
        added = updated = 0
        with self._lock:
            ids = {a.id: i for i, a in enumerate(self.accounts)}
            for item in data.get("accounts", []):
                acc = Account.from_dict(item)
                if acc.id in ids:
                    self.accounts[ids[acc.id]] = acc
                    updated += 1
                else:
                    self.accounts.append(acc)
                    added += 1
            self.save()
        log.info(t("Importadas %d cuentas nuevas, %d actualizadas"), added, updated)
        return added, updated
