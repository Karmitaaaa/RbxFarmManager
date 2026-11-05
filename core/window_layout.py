"""Organización de ventanas: calcula dónde va cada una y las coloca.

Solo mueve y redimensiona ventanas con las APIs públicas de Windows, igual que hacerlo con el ratón.
"""
import logging
import math
from dataclasses import dataclass

from utils import winapi
from utils.i18n import N_

log = logging.getLogger("ventanas")

MODES = {"grid": N_("Cuadrícula"), "row": N_("En fila"), "column": N_("En columna"), "cascade": N_("En cascada")}
ORDERS = {"list": N_("Como en la lista"), "account": N_("Por cuenta"), "game": N_("Por juego")}
SIZE_PRESETS = ((1280, 720), (960, 540), (800, 600), (640, 480), (480, 360), (320, 240))
SIZE_FIT, SIZE_CUSTOM = "fit", "custom"
CASCADE_STEP = 36
GAME_RATIO = 16 / 9


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass
class ArrangeResult:
    placed: int = 0
    limited: bool = False       # alguna ventana no aceptó un tamaño tan pequeño
    overlap: bool = False       # no caben todas sin superponerse


def _best_columns(count: int, area: Rect, gap: int) -> int:
    """Columnas con las que las ventanas quedan más parecidas a 16:9 y sobran menos huecos."""
    def score(cols: int) -> tuple[float, int]:
        rows = math.ceil(count / cols)
        width = max((area.w - gap * (cols - 1)) / cols, 1)
        height = max((area.h - gap * (rows - 1)) / rows, 1)
        return abs(math.log(width / height / GAME_RATIO)), cols * rows - count

    return min(range(1, count + 1), key=score)


def _step(available: int, size: int, gap: int, parts: int) -> int:
    """Distancia entre ventanas: se reduce si no caben, para que ninguna salga del monitor."""
    return size + gap if parts < 2 else min(size + gap, max(available - size, 0) // (parts - 1))


def _fixed_columns(count: int, area: Rect, size: tuple[int, int], gap: int) -> int:
    """Columnas con las que se tapan menos unas a otras; si caben enteras, las que llenan mejor las filas."""
    width, height = min(size[0], area.w), min(size[1], area.h)

    def score(cols: int) -> tuple[float, int, int]:
        rows = math.ceil(count / cols)
        hidden = (max(0.0, 1 - _step(area.w, width, gap, cols) / width) * (cols > 1)
                  + max(0.0, 1 - _step(area.h, height, gap, rows) / height) * (rows > 1))
        return hidden, cols * rows - count, -cols

    return min(range(1, count + 1), key=score)


def compute_layout(count: int, area: Rect, mode: str = "grid", size: tuple[int, int] | None = None,
                   columns: int = 0, gap: int = 0) -> tuple[list[Rect], bool]:
    """Devuelve el sitio de cada ventana y si se superponen. size=None reparte todo el monitor."""
    if count <= 0:
        return [], False

    if mode == "cascade":
        width, height = size or (area.w * 7 // 10, area.h * 7 // 10)
        width, height = min(width, area.w), min(height, area.h)
        step_x = min(CASCADE_STEP, _step(area.w, width, 0, count))
        step_y = min(CASCADE_STEP, _step(area.h, height, 0, count))
        return [Rect(area.x + i * step_x, area.y + i * step_y, width, height) for i in range(count)], False

    if mode == "row":
        cols = count
    elif mode == "column":
        cols = 1
    elif columns > 0:
        cols = min(columns, count)
    elif size is None:
        cols = _best_columns(count, area, gap)
    else:
        cols = _fixed_columns(count, area, size, gap)
    rows = math.ceil(count / cols)

    if size is None:
        width = max((area.w - gap * (cols - 1)) // cols, 1)
        height = max((area.h - gap * (rows - 1)) // rows, 1)
        step_x, step_y = width + gap, height + gap
    else:
        width, height = min(size[0], area.w), min(size[1], area.h)
        step_x, step_y = _step(area.w, width, gap, cols), _step(area.h, height, gap, rows)
    overlap = (cols > 1 and step_x < width) or (rows > 1 and step_y < height)
    return ([Rect(area.x + (i % cols) * step_x, area.y + (i // cols) * step_y, width, height)
             for i in range(count)], overlap)


def parse_size(cfg: dict) -> tuple[int, int] | None:
    """Convierte el ajuste de tamaño («fit», «custom» o «800x600») en (ancho, alto), o None para llenar."""
    value = cfg.get("size", SIZE_FIT)
    if value == SIZE_FIT:
        return None
    if value == SIZE_CUSTOM:
        return int(cfg.get("width", 800)), int(cfg.get("height", 600))
    width, height = str(value).split("x")
    return int(width), int(height)


def pick_monitor(device: str, monitors: list[dict]) -> dict | None:
    """El monitor elegido o, si ya no está conectado, el principal."""
    return next((m for m in monitors if m["device"] == device), monitors[0] if monitors else None)


def layout_for(count: int, cfg: dict, monitor: dict) -> tuple[list[Rect], bool]:
    area = Rect(monitor["x"], monitor["y"], monitor["w"], monitor["h"])
    return compute_layout(count, area, cfg.get("mode", "grid"), parse_size(cfg),
                          int(cfg.get("columns", 0)), int(cfg.get("gap", 0)))


def _place_all(hwnds: list[int], slots: list[Rect], stacked: bool) -> list[tuple[int, int]]:
    """Coloca de la última a la primera: en cascada cada ventana queda bajo la siguiente y se ven los títulos."""
    sizes, above = [], None
    for hwnd, slot in reversed(list(zip(hwnds, slots))):
        size = winapi.place_window(hwnd, slot.x, slot.y, slot.w, slot.h, above if stacked else None)
        if size:
            sizes.append(size)
        above = hwnd
    return sizes


def arrange(hwnds: list[int], cfg: dict) -> ArrangeResult:
    """Coloca las ventanas en orden. Si alguna no acepta el tamaño, reparte de nuevo con el que sí aceptó."""
    monitor = pick_monitor(cfg.get("monitor", ""), winapi.monitors())
    if not hwnds or monitor is None:
        return ArrangeResult()
    stacked = cfg.get("mode") == "cascade"
    slots, overlap = layout_for(len(hwnds), cfg, monitor)
    sizes = _place_all(hwnds, slots, stacked)
    result = ArrangeResult(placed=len(sizes), overlap=overlap)
    if not sizes:
        return result
    width, height = max(s[0] for s in sizes), max(s[1] for s in sizes)
    if width > slots[0].w or height > slots[0].h:
        result.limited = True
        real = {**cfg, "size": SIZE_CUSTOM, "width": max(width, slots[0].w), "height": max(height, slots[0].h)}
        slots, result.overlap = layout_for(len(hwnds), real, monitor)
        _place_all(hwnds, slots, stacked)
    return result


def resize(hwnd: int, width: int, height: int) -> tuple[int, int] | None:
    """Cambia el tamaño de una ventana sin sacarla del monitor en el que está."""
    if winapi.is_minimized(hwnd) or winapi.is_maximized(hwnd):
        winapi.show_no_activate(hwnd)
    rect, monitor = winapi.visible_rect(hwnd), winapi.monitor_of(hwnd)
    if rect is None or monitor is None:
        return None
    width, height = min(width, monitor["w"]), min(height, monitor["h"])
    x = max(min(rect[0], monitor["x"] + monitor["w"] - width), monitor["x"])
    y = max(min(rect[1], monitor["y"] + monitor["h"] - height), monitor["y"])
    return winapi.place_window(hwnd, x, y, width, height)
