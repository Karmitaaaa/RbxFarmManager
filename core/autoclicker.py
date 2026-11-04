"""Autoclicker con intervalo aleatorizable, modo alternar/mantener y límite de clicks."""
import logging
import random
import threading
import time

from PySide6.QtCore import QObject, Signal

from core.timing import high_resolution_timer, wait_until
from utils import winapi
from utils.i18n import N_, t

log = logging.getLogger("autoclicker")

BUTTONS = {"left": N_("Izquierdo"), "right": N_("Derecho"), "middle": N_("Medio")}


class AutoClicker(QObject):
    state_changed = Signal(bool)
    progress = Signal(int)

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.settings: dict = {}
        self.target_hwnd: int | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, settings: dict, target_hwnd: int | None = None) -> None:
        if self.running:
            return
        self.settings = dict(settings)
        self.target_hwnd = target_hwnd
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="autoclicker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def toggle(self, settings: dict, target_hwnd: int | None = None) -> None:
        if self.running:
            self.stop()
        else:
            self.start(settings, target_hwnd)

    def on_hotkey(self, pressed: bool, settings: dict) -> None:
        if settings.get("mode") == "hold":
            if pressed:
                self.start(settings)
            else:
                self.stop()
        elif pressed:
            self.toggle(settings)

    def _run(self) -> None:
        s = self.settings
        button = s.get("button", "left")
        interval = max(1, int(s.get("interval_ms", 100))) / 1000.0
        jitter = max(0, int(s.get("random_ms", 0))) / 1000.0
        hold = max(0, int(s.get("hold_ms", 10))) / 1000.0
        limit = int(s.get("count", 0))
        fixed = s.get("position") == "fixed"
        x, y = int(s.get("x", 0)), int(s.get("y", 0))

        if self.target_hwnd:
            rect = winapi.client_rect_on_screen(self.target_hwnd)
            winapi.focus_window(self.target_hwnd)
            if fixed and rect:  # en modo ventana, la posición es relativa al área cliente
                x, y = rect[0] + x, rect[1] + y

        self.state_changed.emit(True)
        log.info(t("Autoclicker iniciado (%s, %d ms ±%d, %s)"), t(BUTTONS.get(button, button)),
                 int(interval * 1000), int(jitter * 1000), "infinito" if not limit else f"{limit} clicks")
        count = 0
        try:
            with high_resolution_timer():
                next_at = time.perf_counter()
                while not self._stop.is_set() and (limit == 0 or count < limit):
                    with winapi.INPUT_LOCK:
                        if fixed:
                            winapi.mouse_move_abs(x, y)
                        winapi.mouse_click(button, hold)
                    count += 1
                    if count % 10 == 0 or count == limit:
                        self.progress.emit(count)
                    delay = interval + (random.uniform(-jitter, jitter) if jitter else 0.0)
                    next_at = max(next_at + max(delay, 0.001), time.perf_counter())
                    if not wait_until(next_at, self._stop):
                        break
        except Exception:
            log.exception("Error en el autoclicker")
        finally:
            self.progress.emit(count)
            self.state_changed.emit(False)
            log.info(t("Autoclicker detenido tras %d clicks"), count)
