"""Utilidades de Windows: ventanas, foco y entrada sintética (SendInput).

Todo es automatización externa: solo se usan APIs públicas de Windows para ventanas,
teclado y ratón. No se inyecta código ni se lee/escribe memoria de otros procesos.
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

import win32con
import win32gui
import win32process

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ROBLOX_EXE = "RobloxPlayerBeta.exe"
ROBLOX_WINDOW_CLASS = "WINDOWSCLIENT"
DIALOG_CLASS = "#32770"

# Un único candado global: anti-AFK, macros y autoclicker comparten teclado/ratón reales,
# así que nunca deben enviar entradas a la vez.
INPUT_LOCK = threading.RLock()

# --------------------------------------------------------------------------- SendInput
ULONG_PTR = ctypes.c_size_t
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

# Teclas que necesitan el bit "extended" al enviarse por scancode
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
                0xA3, 0xA5, 0x5B, 0x5C, 0x5D, 0x6F, 0x90}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT

_last_injection = 0.0


def _send(*inputs: INPUT) -> None:
    global _last_injection
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    _last_injection = time.monotonic()
    if sent != len(inputs):
        log.debug("SendInput envió %s/%s eventos (error %s)", sent, len(inputs), ctypes.get_last_error())


def key_event(vk: int, down: bool, scan: int | None = None, extended: bool | None = None) -> None:
    if scan is None or scan == 0:
        scan = user32.MapVirtualKeyW(vk, 0)
    if extended is None:
        extended = vk in EXTENDED_VKS
    flags = KEYEVENTF_SCANCODE
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if not down:
        flags |= KEYEVENTF_KEYUP
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    _send(inp)


def tap_key(vk: int, hold: float = 0.06) -> None:
    key_event(vk, True)
    time.sleep(hold)
    key_event(vk, False)


def _virtual_screen() -> tuple[int, int, int, int]:
    return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
            max(user32.GetSystemMetrics(78), 1), max(user32.GetSystemMetrics(79), 1))


def mouse_move_abs(x: int, y: int) -> None:
    vx, vy, vw, vh = _virtual_screen()
    nx = int((x - vx) * 65535 / max(vw - 1, 1))
    ny = int((y - vy) * 65535 / max(vh - 1, 1))
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(nx, ny, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, 0, 0)
    _send(inp)


def mouse_move_rel(dx: int, dy: int) -> None:
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, 0)
    _send(inp)


def mouse_button(button: str, down: bool) -> None:
    flag_down, flag_up = BUTTON_FLAGS[button]
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(0, 0, 0, flag_down if down else flag_up, 0, 0)
    _send(inp)


def mouse_click(button: str = "left", hold: float = 0.01) -> None:
    mouse_button(button, True)
    if hold > 0:
        time.sleep(hold)
    mouse_button(button, False)


def mouse_wheel(delta: int, horizontal: bool = False) -> None:
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(0, 0, ctypes.c_uint32(delta).value,
                        MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL, 0, 0)
    _send(inp)


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def seconds_since_user_input() -> float:
    """Segundos desde la última entrada *del usuario* (descarta la que enviamos nosotros)."""
    info = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 9999.0
    idle = (kernel32.GetTickCount() - info.dwTime) / 1000.0
    since_ours = time.monotonic() - _last_injection
    if abs(idle - since_ours) < 0.5:
        # La última entrada registrada fue nuestra: el usuario lleva al menos ese tiempo inactivo
        return 9999.0
    return idle


# --------------------------------------------------------------------------- Ventanas
def windows_for_pid(pid: int) -> list[dict]:
    result = []

    def _cb(hwnd, _):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid == pid:
                result.append({
                    "hwnd": hwnd,
                    "title": win32gui.GetWindowText(hwnd),
                    "class": win32gui.GetClassName(hwnd),
                    "visible": bool(win32gui.IsWindowVisible(hwnd)),
                })
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return result


def main_window_for_pid(pid: int) -> int | None:
    wins = windows_for_pid(pid)
    for w in wins:
        if w["class"] == ROBLOX_WINDOW_CLASS:
            return w["hwnd"]
    for w in wins:
        if w["visible"] and w["title"].startswith("Roblox") and w["class"] != DIALOG_CLASS:
            return w["hwnd"]
    return None


def error_dialogs_for_pid(pid: int) -> list[dict]:
    """Diálogos Win32 nativos (crash/errores del cliente). Los avisos dentro del juego no son ventanas."""
    found = []
    for w in windows_for_pid(pid):
        if not w["visible"]:
            continue
        title = w["title"].lower()
        if w["class"] == DIALOG_CLASS or "crash" in title or "error" in title:
            found.append(w)
    return found


def is_window(hwnd: int | None) -> bool:
    return bool(hwnd) and bool(win32gui.IsWindow(hwnd))


def minimize(hwnd: int) -> None:
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWMINNOACTIVE)
    except Exception as exc:
        log.debug("No se pudo minimizar %s: %s", hwnd, exc)


def restore(hwnd: int) -> None:
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception as exc:
        log.debug("No se pudo restaurar %s: %s", hwnd, exc)


def is_minimized(hwnd: int) -> bool:
    try:
        return bool(win32gui.IsIconic(hwnd))
    except Exception:
        return False


def set_title(hwnd: int, title: str) -> None:
    try:
        win32gui.SetWindowText(hwnd, title)
    except Exception:
        pass


def foreground_window() -> int:
    return user32.GetForegroundWindow()


def focus_window(hwnd: int) -> bool:
    """Pone la ventana en primer plano sorteando la protección antirrobo de foco de Windows."""
    if not is_window(hwnd):
        return False
    if is_minimized(hwnd):
        restore(hwnd)
        time.sleep(0.15)
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    cur_tid = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    try:
        if fg_tid and fg_tid != cur_tid:
            attached = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur_tid, fg_tid, False)
    if user32.GetForegroundWindow() != hwnd:
        # Plan B: una pulsación de ALT desbloquea SetForegroundWindow
        key_event(0x12, True)
        key_event(0x12, False)
        user32.SetForegroundWindow(hwnd)
    time.sleep(0.05)
    return user32.GetForegroundWindow() == hwnd


def client_rect_on_screen(hwnd: int) -> tuple[int, int, int, int] | None:
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        sx, sy = win32gui.ClientToScreen(hwnd, (left, top))
        return sx, sy, right - left, bottom - top
    except Exception:
        return None


def post_key(hwnd: int, vk: int, hold: float = 0.06) -> None:
    """Envía una tecla por mensajes de ventana (sin robar foco). Roblox puede ignorarlo."""
    scan = user32.MapVirtualKeyW(vk, 0)
    lparam_down = 1 | (scan << 16)
    lparam_up = lparam_down | (1 << 30) | (1 << 31)
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, lparam_down)
    time.sleep(hold)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, lparam_up)
