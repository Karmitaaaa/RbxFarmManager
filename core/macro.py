"""Grabación y reproducción de macros de teclado y ratón con tiempos exactos.

Formato de evento (tiempos en segundos desde el inicio de la grabación):
  {"t": 0.512, "type": "key",    "vk": 87, "scan": 17, "ext": false, "down": true}
  {"t": 0.900, "type": "move",   "x": 640, "y": 360}
  {"t": 1.020, "type": "button", "button": "left", "down": true, "x": 640, "y": 360}
  {"t": 1.300, "type": "wheel",  "delta": -120, "horizontal": false, "x": 640, "y": 360}
"""
import ctypes
import logging
import threading
import time

from pynput import keyboard, mouse
from PySide6.QtCore import QObject, Signal

from core.timing import high_resolution_timer, wait_until
from utils import winapi
from utils.i18n import t

log = logging.getLogger("macros")

LLKHF_INJECTED, LLKHF_EXTENDED, LLMHF_INJECTED = 0x10, 0x01, 0x01
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
MOUSE_BUTTON_MSGS = {
    0x201: ("left", True), 0x202: ("left", False),
    0x204: ("right", True), 0x205: ("right", False),
    0x207: ("middle", True), 0x208: ("middle", False),
}
WM_MOUSEMOVE, WM_MOUSEWHEEL, WM_MOUSEHWHEEL = 0x200, 0x20A, 0x20E


class MacroRecorder(QObject):
    state_changed = Signal(bool)
    counter = Signal(int)

    def __init__(self):
        super().__init__()
        self.events: list[dict] = []
        self._t0 = 0.0
        self._kb = None
        self._ms = None
        self._held: set[int] = set()
        self._ignore_vks: set[int] = set()
        self._record_moves = True
        self._throttle = 0.015
        self._last_move = 0.0
        self.recording = False

    def start(self, ignore_vks: set[int], record_moves: bool = True, throttle_ms: int = 15) -> None:
        if self.recording:
            return
        self.events = []
        self._held = set()
        self._ignore_vks = set(ignore_vks)
        self._record_moves = record_moves
        self._throttle = max(0, throttle_ms) / 1000.0
        self._t0 = time.perf_counter()
        self._kb = keyboard.Listener(win32_event_filter=self._kb_filter)
        self._ms = mouse.Listener(win32_event_filter=self._ms_filter)
        self._kb.start()
        self._ms.start()
        self.recording = True
        self.state_changed.emit(True)
        log.info(t("Grabación de macro iniciada"))

    def stop(self) -> list[dict]:
        if not self.recording:
            return self.events
        for listener in (self._kb, self._ms):
            if listener:
                listener.stop()
        self.recording = False
        # Suelta al final las teclas que seguían pulsadas para no dejarlas "pegadas" al reproducir
        t = self._now()
        for vk in self._held:
            self.events.append({"t": t, "type": "key", "vk": vk, "scan": 0, "ext": False, "down": False})
        self.state_changed.emit(False)
        log.info(t("Grabación detenida: %d eventos, %.1f s"), len(self.events), t)
        return self.events

    def _now(self) -> float:
        return round(time.perf_counter() - self._t0, 4)

    def _add(self, event: dict) -> None:
        self.events.append(event)
        if len(self.events) % 25 == 0:
            self.counter.emit(len(self.events))

    def _kb_filter(self, msg, data):
        if data.flags & LLKHF_INJECTED or data.vkCode in self._ignore_vks:
            return False
        down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
        vk = data.vkCode
        if down and vk in self._held:
            return False  # autorepetición del teclado
        (self._held.add if down else self._held.discard)(vk)
        self._add({"t": self._now(), "type": "key", "vk": vk, "scan": data.scanCode,
                   "ext": bool(data.flags & LLKHF_EXTENDED), "down": down})
        return False

    def _ms_filter(self, msg, data):
        if data.flags & LLMHF_INJECTED:
            return False
        x, y = data.pt.x, data.pt.y
        if msg == WM_MOUSEMOVE:
            if self._record_moves:
                now = time.perf_counter()
                if now - self._last_move >= self._throttle:
                    self._last_move = now
                    self._add({"t": self._now(), "type": "move", "x": x, "y": y})
        elif msg in MOUSE_BUTTON_MSGS:
            button, down = MOUSE_BUTTON_MSGS[msg]
            self._add({"t": self._now(), "type": "button", "button": button, "down": down, "x": x, "y": y})
        elif msg in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
            delta = ctypes.c_short((data.mouseData >> 16) & 0xFFFF).value
            self._add({"t": self._now(), "type": "wheel", "delta": delta,
                       "horizontal": msg == WM_MOUSEHWHEEL, "x": x, "y": y})
        return False


class MacroPlayer(QObject):
    state_changed = Signal(bool)
    loop_done = Signal(int)

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.current_name = ""
        self.instance = None

    @property
    def playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def play(self, name: str, events: list[dict], speed: float = 1.0, repeat: int = 1,
             loop_delay_ms: int = 500, relative_mouse: bool = False, instance=None,
             focus_target: bool = True) -> bool:
        if self.playing or not events:
            return False
        self._stop.clear()
        self.current_name = name
        self.instance = instance
        args = (events, max(0.05, float(speed)), int(repeat), max(0, int(loop_delay_ms)) / 1000.0,
                relative_mouse, focus_target)
        self._thread = threading.Thread(target=self._run, args=args, name="macro-player", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _run(self, events, speed, repeat, loop_delay, relative_mouse, focus_target) -> None:
        inst = self.instance
        if inst:
            inst.macro_running = True
        self.state_changed.emit(True)
        target = f" en {inst.account.alias}" if inst else ""
        log.info(t("Reproduciendo «%s»%s (x%.2f, %s)"), self.current_name, target, speed,
                 "infinito" if repeat == 0 else f"{repeat} veces")
        loops = 0
        try:
            with high_resolution_timer():
                while not self._stop.is_set() and (repeat == 0 or loops < repeat):
                    with winapi.INPUT_LOCK:
                        if inst and focus_target and inst.hwnd:
                            winapi.focus_window(inst.hwnd)
                        self._play_once(events, speed, relative_mouse)
                    loops += 1
                    self.loop_done.emit(loops)
                    if repeat == 0 or loops < repeat:
                        # Entre bucles se libera el candado para que el anti-AFK de otras cuentas pueda actuar
                        if not wait_until(time.perf_counter() + loop_delay, self._stop):
                            break
        except Exception:
            log.exception("Error reproduciendo la macro")
        finally:
            if inst:
                inst.macro_running = False
            self.state_changed.emit(False)
            log.info(t("Macro «%s» detenida tras %d bucle(s)"), self.current_name, loops)

    def _play_once(self, events, speed, relative_mouse) -> None:
        held_keys: dict[int, tuple[int, bool]] = {}
        held_buttons: set[str] = set()
        last_pos = None
        start = time.perf_counter()
        try:
            for ev in events:
                if not wait_until(start + ev["t"] / speed, self._stop):
                    return
                kind = ev["type"]
                if kind == "key":
                    winapi.key_event(ev["vk"], ev["down"], ev.get("scan") or None, ev.get("ext"))
                    if ev["down"]:
                        held_keys[ev["vk"]] = (ev.get("scan") or 0, ev.get("ext", False))
                    else:
                        held_keys.pop(ev["vk"], None)
                    continue
                if kind in ("move", "button", "wheel") and "x" in ev:
                    if relative_mouse:
                        if last_pos is not None and kind == "move":
                            winapi.mouse_move_rel(ev["x"] - last_pos[0], ev["y"] - last_pos[1])
                    elif kind == "move" or last_pos != (ev["x"], ev["y"]):
                        winapi.mouse_move_abs(ev["x"], ev["y"])
                    last_pos = (ev["x"], ev["y"])
                if kind == "button":
                    winapi.mouse_button(ev["button"], ev["down"])
                    (held_buttons.add if ev["down"] else held_buttons.discard)(ev["button"])
                elif kind == "wheel":
                    winapi.mouse_wheel(ev["delta"], ev.get("horizontal", False))
        finally:
            for vk, (scan, ext) in held_keys.items():
                winapi.key_event(vk, False, scan or None, ext)
            for button in held_buttons:
                winapi.mouse_button(button, False)
