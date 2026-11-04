"""Configuración no sensible en JSON, con guardado automático (debounce desde la UI)."""
import copy
import json
import logging
import os
import threading

from utils.paths import config_path

log = logging.getLogger(__name__)

DEFAULTS = {
    "theme": "classic",                 # classic (claro) | dark
    "minimize_to_tray": True,
    "start_minimized": False,
    "main_account_id": "",              # cuenta que se saluda en la portada
    "download_avatars": True,           # fotos de avatar desde roblox.com
    "last_link": "",
    "sidebar_visible": True,
    "hide_onboarding": False,
    "launched_once": False,
    "launch": {
        "delay_s": 8,                   # espera entre lanzamientos
        "multi_instance": True,
        "fps_cap": 0,                   # 0 = sin límite
        "low_priority": False,
        "auto_minimize": False,
        "rename_windows": True,
        "pid_timeout_s": 60,
    },
    "antiafk": {
        "enabled": True,
        "min_s": 60,
        "max_s": 240,
        "action": "jump",               # jump | walk | camera | key | click
        "custom_key": "SPACE",
        "method": "focus",              # focus | post
        "pause_if_user_active_s": 4,
        "reminimize": True,
    },
    "reconnect": {
        "enabled": True,
        "max_attempts": 5,
        "base_delay_s": 10,
        "max_delay_s": 300,
        "disconnect_grace_s": 25,
        "check_internet": True,
        "join_timeout_s": 180,
        "restart_on_join_timeout": True,
        "reset_after_s": 300,
        "close_error_dialogs": True,
    },
    "clicker": {
        "button": "left",
        "interval_ms": 100,
        "random_ms": 0,
        "mode": "toggle",               # toggle | hold
        "count": 0,                     # 0 = infinito
        "position": "cursor",           # cursor | fixed
        "x": 0,
        "y": 0,
        "hold_ms": 10,
    },
    "clicker_presets": {},
    "macro": {
        "speed": 1.0,
        "repeat": 1,                    # 0 = infinito
        "loop_delay_ms": 500,
        "relative_mouse": False,
        "record_moves": True,
        "move_throttle_ms": 15,
        "focus_target": True,
    },
    "hotkeys": {
        "clicker": "F6",
        "macro_record": "F8",
        "macro_stop": "F9",
        "macro_play": "F10",
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    def __init__(self):
        self.path = config_path()
        self.data = copy.deepcopy(DEFAULTS)
        self.dirty = False
        self._lock = threading.RLock()
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                self.data = _merge(DEFAULTS, json.loads(self.path.read_text("utf-8")))
            except Exception as exc:
                log.error("settings.json dañado, se usan valores por defecto: %s", exc)

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), "utf-8")
            os.replace(tmp, self.path)
            self.dirty = False

    def save_if_dirty(self) -> None:
        if self.dirty:
            try:
                self.save()
            except Exception as exc:
                log.error("No se pudo guardar la configuración: %s", exc)

    def get(self, dotted: str, default=None):
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value) -> None:
        with self._lock:
            parts = dotted.split(".")
            node = self.data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            if node.get(parts[-1]) != value:
                node[parts[-1]] = value
                self.dirty = True

    def section(self, name: str) -> dict:
        return self.data.setdefault(name, {})
