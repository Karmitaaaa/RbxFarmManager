"""Perfiles de macro: un archivo JSON por perfil en %APPDATA%\\RbxFarmManager\\macros."""
import json
import re
import shutil
import time
from pathlib import Path

from utils.paths import macros_dir
from utils.i18n import t

_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe(name: str) -> str:
    name = _BAD_CHARS.sub("_", name).strip(" .")
    if not name:
        raise ValueError(t("Nombre de perfil vacío"))
    return name


class MacroProfileStore:
    def __init__(self, folder: Path | None = None):
        self.folder = folder or macros_dir()
        self._game_cache: dict[str, tuple[float, str]] = {}

    def _file(self, name: str) -> Path:
        return self.folder / f"{_safe(name)}.json"

    def game_of(self, name: str) -> str:
        """ID del perfil de juego al que pertenece la macro ("" = sin juego). Cacheado por fecha."""
        path = self._file(name)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return ""
        cached = self._game_cache.get(name)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            game_id = self.load(name).get("meta", {}).get("game_id", "")
        except Exception:
            game_id = ""
        self._game_cache[name] = (mtime, game_id)
        return game_id

    def set_game(self, name: str, game_id: str) -> None:
        data = self.load(name)
        data.setdefault("meta", {})["game_id"] = game_id
        self._file(name).write_text(json.dumps(data, ensure_ascii=False), "utf-8")

    def names_for_game(self, game_id: str) -> list[str]:
        return [n for n in self.names() if self.game_of(n) == game_id]

    def names(self) -> list[str]:
        return sorted((p.stem for p in self.folder.glob("*.json")), key=str.lower)

    def exists(self, name: str) -> bool:
        return self._file(name).exists()

    def load(self, name: str) -> dict:
        return json.loads(self._file(name).read_text("utf-8"))

    def save(self, name: str, events: list[dict], meta: dict | None = None) -> None:
        duration = events[-1]["t"] if events else 0.0
        data = {"name": name, "version": 1, "created": time.time(), "duration": duration,
                "events": events, "meta": meta or {}}
        self._file(name).write_text(json.dumps(data, ensure_ascii=False), "utf-8")

    def rename(self, old: str, new: str) -> None:
        if self.exists(new):
            raise FileExistsError(t("Ya existe un perfil llamado «{0}»", new))
        data = self.load(old)
        data["name"] = new
        self._file(new).write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        self._file(old).unlink()

    def duplicate(self, name: str) -> str:
        n, new = 2, t("{0} (copia)", name)
        while self.exists(new):
            new = t("{0} (copia {1})", name, n)
            n += 1
        data = self.load(name)
        data["name"] = new
        self._file(new).write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        return new

    def delete(self, name: str) -> None:
        self._file(name).unlink(missing_ok=True)

    def import_file(self, path: str) -> str:
        data = json.loads(Path(path).read_text("utf-8"))
        if not isinstance(data.get("events"), list):
            raise ValueError(t("El archivo no es un perfil de macro válido"))
        name = _safe(data.get("name") or Path(path).stem)
        base, n = name, 2
        while self.exists(name):
            name = f"{base} ({n})"
            n += 1
        data["name"] = name
        self._file(name).write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        return name

    def export_file(self, name: str, path: str) -> None:
        shutil.copyfile(self._file(name), path)
