"""Hotkeys globales con pynput (gancho de teclado de bajo nivel).

Formato de texto: "F6", "Ctrl+F7", "Ctrl+Shift+R". Se ignoran las pulsaciones inyectadas
por la propia app (macros/anti-AFK) para que no se disparen solas.
"""
import logging
import threading

from pynput import keyboard
from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

LLKHF_INJECTED = 0x10
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105

MODIFIER_VKS = {
    "ctrl": {0x11, 0xA2, 0xA3},
    "shift": {0x10, 0xA0, 0xA1},
    "alt": {0x12, 0xA4, 0xA5},
}

NAMED_VKS = {
    "SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09, "ESC": 0x1B, "BACKSPACE": 0x08,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27, "PAUSE": 0x13, "SCROLLLOCK": 0x91,
    "CAPSLOCK": 0x14, "NUMLOCK": 0x90, "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC,
}
for _i in range(1, 25):
    NAMED_VKS[f"F{_i}"] = 0x6F + _i
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    NAMED_VKS[_c] = ord(_c)
for _i in range(10):
    NAMED_VKS[f"NUM{_i}"] = 0x60 + _i

VK_NAMES = {v: k for k, v in NAMED_VKS.items()}


def vk_from_name(name: str) -> int | None:
    return NAMED_VKS.get(name.strip().upper())


def name_from_vk(vk: int) -> str:
    return VK_NAMES.get(vk, f"VK{vk:02X}")


def parse_hotkey(text: str) -> tuple[frozenset, int] | None:
    if not text:
        return None
    parts = [p.strip() for p in text.split("+") if p.strip()]
    mods, vk = set(), None
    for part in parts:
        low = part.lower()
        if low in MODIFIER_VKS:
            mods.add(low)
        elif low == "control":
            mods.add("ctrl")
        else:
            vk = vk_from_name(part)
    if vk is None:
        return None
    return frozenset(mods), vk


class HotkeyManager(QObject):
    """Emite triggered(nombre, presionado). Las señales Qt llegan al hilo de la UI de forma segura."""

    triggered = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self._bindings: dict[str, tuple[frozenset, int]] = {}
        self._held_mods: set[str] = set()
        self._active: set[str] = set()
        self._lock = threading.Lock()
        self._listener: keyboard.Listener | None = None
        self.paused = False

    def set_binding(self, name: str, hotkey: str) -> bool:
        parsed = parse_hotkey(hotkey)
        with self._lock:
            if parsed is None:
                self._bindings.pop(name, None)
                return False
            self._bindings[name] = parsed
        return True

    def start(self) -> None:
        if self._listener is None:
            self._listener = keyboard.Listener(win32_event_filter=self._filter)
            self._listener.daemon = True
            self._listener.start()
            log.info("Hotkeys globales activas")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _filter(self, msg, data):
        if data.flags & LLKHF_INJECTED:
            return False
        vk = data.vkCode
        down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
        for mod, vks in MODIFIER_VKS.items():
            if vk in vks:
                (self._held_mods.add if down else self._held_mods.discard)(mod)
                return False
        if self.paused:
            return False
        with self._lock:
            bindings = list(self._bindings.items())
        for name, (mods, bvk) in bindings:
            if bvk != vk:
                continue
            if down and mods == self._held_mods and name not in self._active:
                self._active.add(name)
                self.triggered.emit(name, True)
            elif not down and name in self._active:
                self._active.discard(name)
                self.triggered.emit(name, False)
        return False
