"""Temporización precisa: sube la resolución del temporizador de Windows a 1 ms mientras se usa."""
import ctypes
import threading
import time
from contextlib import contextmanager

_winmm = ctypes.WinDLL("winmm")
_users = 0
_lock = threading.Lock()


@contextmanager
def high_resolution_timer():
    global _users
    with _lock:
        if _users == 0:
            _winmm.timeBeginPeriod(1)
        _users += 1
    try:
        yield
    finally:
        with _lock:
            _users -= 1
            if _users == 0:
                _winmm.timeEndPeriod(1)


def wait_until(deadline: float, stop: threading.Event) -> bool:
    """Espera hasta deadline (perf_counter). Devuelve False si se pidió parar."""
    while True:
        if stop.is_set():
            return False
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return True
        if remaining > 0.003:
            time.sleep(min(remaining - 0.002, 0.05))
        # los últimos ~2 ms se esperan activamente para no pasarse
