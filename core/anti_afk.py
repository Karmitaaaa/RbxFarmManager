"""Anti-AFK: envía una entrada mínima a cada ventana de Roblox cada cierto tiempo aleatorio.

Métodos:
  - "focus": enfoca la ventana un instante, envía la tecla con SendInput (scancodes) y devuelve
    el foco a la ventana que tenías. Es el método fiable con Roblox.
  - "post": PostMessage a la ventana sin tocar el foco. No roba foco, pero Roblox suele ignorarlo.
"""
import logging
import random
import threading
import time

from PySide6.QtCore import QObject, Signal

from core.models import ST_INGAME, ST_OPEN
from storage.config import Config
from utils import winapi
from utils.hotkeys import vk_from_name
from utils.i18n import N_, t

log = logging.getLogger("anti-afk")

ACTIONS = {
    "jump": N_("Saltar (Espacio)"),
    "walk": N_("Paso adelante/atrás (W/S)"),
    "camera": N_("Girar cámara (← →)"),
    "key": N_("Tecla personalizada"),
    "click": N_("Click derecho en el centro"),
}
METHODS = {
    "focus": N_("Foco breve + SendInput (recomendado)"),
    "post": N_("Mensajes de ventana (sin foco, puede no funcionar)"),
}

VK_SPACE, VK_W, VK_S, VK_LEFT, VK_RIGHT = 0x20, 0x57, 0x53, 0x25, 0x27


class AntiAfk(QObject):
    acted = Signal(str)  # id de instancia

    def __init__(self, manager, config: Config):
        super().__init__()
        self.manager = manager
        self.cfg = config
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="anti-afk", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()

    def _schedule(self, inst) -> None:
        lo = float(self.cfg.get("antiafk.min_s", 60))
        hi = max(lo, float(self.cfg.get("antiafk.max_s", 240)))
        inst.next_afk_at = time.time() + random.uniform(lo, hi)

    def _loop(self) -> None:
        while not self._stop.wait(1.0):
            if not self.cfg.get("antiafk.enabled"):
                continue
            now = time.time()
            for inst in self.manager.snapshot():
                if (not inst.anti_afk or inst.macro_running or inst.status not in (ST_OPEN, ST_INGAME)
                        or not winapi.is_window(inst.hwnd)):
                    continue
                if inst.next_afk_at == 0:
                    self._schedule(inst)
                    continue
                if now < inst.next_afk_at:
                    continue
                pause = float(self.cfg.get("antiafk.pause_if_user_active_s", 4))
                if (self.cfg.get("antiafk.method") == "focus" and pause > 0
                        and winapi.seconds_since_user_input() < pause):
                    inst.next_afk_at = now + 3  # el usuario está usando el PC: esperamos
                    continue
                try:
                    self.perform(inst)
                except Exception:
                    log.exception("Fallo del anti-AFK en %s", inst.account.alias)
                self._schedule(inst)

    def perform(self, inst) -> None:
        action = self.cfg.get("antiafk.action", "jump")
        method = self.cfg.get("antiafk.method", "focus")
        hwnd = inst.hwnd
        with winapi.INPUT_LOCK:
            if method == "post":
                self._do_post(hwnd, action)
            else:
                previous = winapi.foreground_window()
                was_minimized = winapi.is_minimized(hwnd)
                if not winapi.focus_window(hwnd):
                    log.warning(t("%s: no se pudo enfocar la ventana para el anti-AFK"), inst.account.alias)
                    return
                time.sleep(0.12)
                self._do_sendinput(hwnd, action)
                time.sleep(0.05)
                if was_minimized and self.cfg.get("antiafk.reminimize"):
                    winapi.minimize(hwnd)
                if previous and previous != hwnd and winapi.is_window(previous):
                    winapi.focus_window(previous)
        inst.last_afk_at = time.time()
        log.info(t("%s: anti-AFK (%s)"), inst.account.alias, t(ACTIONS.get(action, action)))
        self.acted.emit(inst.id)

    def _custom_vk(self) -> int:
        return vk_from_name(self.cfg.get("antiafk.custom_key", "SPACE")) or VK_SPACE

    def _do_sendinput(self, hwnd: int, action: str) -> None:
        if action == "walk":
            winapi.tap_key(VK_W, 0.12)
            time.sleep(0.05)
            winapi.tap_key(VK_S, 0.12)
        elif action == "camera":
            winapi.tap_key(VK_LEFT, 0.1)
            time.sleep(0.05)
            winapi.tap_key(VK_RIGHT, 0.1)
        elif action == "key":
            winapi.tap_key(self._custom_vk())
        elif action == "click":
            rect = winapi.client_rect_on_screen(hwnd)
            if rect:
                old = winapi.cursor_pos()
                x, y, w, h = rect
                winapi.mouse_move_abs(x + w // 2, y + h // 2)
                winapi.mouse_click("right", 0.03)
                winapi.mouse_move_abs(*old)
        else:
            winapi.tap_key(VK_SPACE)

    def _do_post(self, hwnd: int, action: str) -> None:
        if action == "walk":
            winapi.post_key(hwnd, VK_W, 0.12)
            winapi.post_key(hwnd, VK_S, 0.12)
        elif action == "camera":
            winapi.post_key(hwnd, VK_LEFT, 0.1)
            winapi.post_key(hwnd, VK_RIGHT, 0.1)
        elif action == "key":
            winapi.post_key(hwnd, self._custom_vk())
        else:
            winapi.post_key(hwnd, VK_SPACE)
