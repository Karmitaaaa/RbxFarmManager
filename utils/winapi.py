"""Utilidades de Windows: ventanas, foco y entrada sintética (SendInput).

Todo es automatización externa: solo se usan APIs públicas de Windows para ventanas,
teclado y ratón. No se inyecta código ni se lee/escribe memoria de otros procesos.
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

import win32api
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


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.GetDC.argtypes = (wintypes.HWND,)
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
user32.PrintWindow.restype = wintypes.BOOL
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (wintypes.HDC,)

PW_CLIENTONLY, PW_RENDERFULLCONTENT = 1, 2


def capture_window(hwnd: int) -> tuple[bytes, int, int] | None:
    """Copia el contenido de una ventana (píxeles BGRA de arriba abajo) con la API pública PrintWindow.

    Funciona aunque esté tapada por otras ventanas, pero no si está minimizada: Windows no la dibuja.
    Devuelve None si no se pudo capturar o si la imagen salió completamente negra.
    """
    try:
        _, _, width, height = win32gui.GetClientRect(hwnd)
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=width, biHeight=-height,
                              biPlanes=1, biBitCount=32)
    bits = ctypes.c_void_p()
    window_dc = user32.GetDC(hwnd)
    if not window_dc:
        return None
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateDIBSection(memory_dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    data = None
    try:
        if bitmap:
            previous = gdi32.SelectObject(memory_dc, bitmap)
            if user32.PrintWindow(hwnd, memory_dc, PW_CLIENTONLY | PW_RENDERFULLCONTENT):
                data = ctypes.string_at(bits, width * height * 4)
            gdi32.SelectObject(memory_dc, previous)
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
    if data is None or max(max(data[i::4092]) for i in range(3)) < 6:
        return None
    return data, width, height


def post_key(hwnd: int, vk: int, hold: float = 0.06) -> None:
    """Envía una tecla por mensajes de ventana (sin robar foco). Roblox puede ignorarlo."""
    scan = user32.MapVirtualKeyW(vk, 0)
    lparam_down = 1 | (scan << 16)
    lparam_up = lparam_down | (1 << 30) | (1 << 31)
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, lparam_down)
    time.sleep(hold)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, lparam_up)


# --------------------------------------------------------------------------- Posición y tamaño
dwmapi = ctypes.WinDLL("dwmapi")
dwmapi.DwmGetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

DWMWA_EXTENDED_FRAME_BOUNDS = 9
SWP_NOSENDCHANGING = 0x0400     # sin esto Roblox impone su mínimo de 800 × 600 al cambiar de tamaño
MONITORINFOF_PRIMARY = 1
MONITOR_DEFAULTTONEAREST = 2


def _monitor_dict(handle) -> dict:
    info = win32api.GetMonitorInfo(handle)
    left, top, right, bottom = info["Monitor"]
    work = info["Work"]
    return {"device": info["Device"], "width": right - left, "height": bottom - top,
            "primary": bool(info["Flags"] & MONITORINFOF_PRIMARY),
            "x": work[0], "y": work[1], "w": work[2] - work[0], "h": work[3] - work[1]}


def monitors() -> list[dict]:
    """Monitores con el principal primero. x, y, w, h son el área útil (sin la barra de tareas), en píxeles reales."""
    found = []
    try:
        found = [_monitor_dict(entry[0]) for entry in win32api.EnumDisplayMonitors()]
    except Exception as exc:
        log.debug("No se pudieron listar los monitores: %s", exc)
    return sorted(found, key=lambda m: (not m["primary"], m["device"]))


def monitor_of(hwnd: int) -> dict | None:
    try:
        return _monitor_dict(win32api.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST))
    except Exception:
        return None


def is_maximized(hwnd: int) -> bool:
    try:
        return win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED
    except Exception:
        return False


def show_no_activate(hwnd: int) -> None:
    """Saca la ventana de minimizada o maximizada sin quitarle el foco a nadie."""
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
    except Exception as exc:
        log.debug("No se pudo mostrar %s: %s", hwnd, exc)


def maximize(hwnd: int) -> None:
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    except Exception as exc:
        log.debug("No se pudo maximizar %s: %s", hwnd, exc)


def _frame_margins(hwnd: int) -> tuple[int, int, int, int]:
    """Borde invisible que Windows añade alrededor de la ventana (izquierda, arriba, derecha, abajo)."""
    outer = win32gui.GetWindowRect(hwnd)
    rect = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)):
        return 0, 0, 0, 0
    return rect.left - outer[0], rect.top - outer[1], outer[2] - rect.right, outer[3] - rect.bottom


class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]


kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.SetProcessInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
kernel32.SetProcessInformation.restype = wintypes.BOOL

PROCESS_SET_INFORMATION = 0x0200
PROCESS_POWER_THROTTLING = 4        # ProcessPowerThrottling
THROTTLE_EXECUTION_SPEED = 1


def set_efficiency_mode(pid: int, enabled: bool) -> bool:
    """Activa o quita el modo de eficiencia de Windows (EcoQoS) de un proceso."""
    handle = kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
    if not handle:
        return False
    # Con control 0 Windows vuelve a decidir solo, en vez de prohibir el ahorro
    mask = THROTTLE_EXECUTION_SPEED if enabled else 0
    state = PROCESS_POWER_THROTTLING_STATE(1, mask, mask)
    try:
        return bool(kernel32.SetProcessInformation(handle, PROCESS_POWER_THROTTLING, ctypes.byref(state),
                                                   ctypes.sizeof(state)))
    finally:
        kernel32.CloseHandle(handle)


def visible_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Lo que se ve de la ventana (x, y, ancho, alto), sin el borde invisible."""
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        m_left, m_top, m_right, m_bottom = _frame_margins(hwnd)
    except Exception:
        return None
    return left + m_left, top + m_top, right - left - m_left - m_right, bottom - top - m_top - m_bottom


def place_window(hwnd: int, x: int, y: int, width: int, height: int, after: int | None = None) -> tuple[int, int] | None:
    """Coloca la ventana sin darle el foco y devuelve el tamaño que acabó teniendo.

    x, y, width y height se refieren a la parte visible, para que las ventanas queden juntas de verdad.
    Con `after` la deja justo debajo de esa otra ventana; sin él no cambia cuál está delante.
    Devuelve None si no se pudo.
    """
    try:
        if is_minimized(hwnd) or is_maximized(hwnd):
            show_no_activate(hwnd)
        left, top, right, bottom = _frame_margins(hwnd)
        target = (x - left, y - top, width + left + right, height + top + bottom)
        now = win32gui.GetWindowRect(hwnd)
        current = (now[0], now[1], now[2] - now[0], now[3] - now[1])
        flags = win32con.SWP_NOACTIVATE | win32con.SWP_NOOWNERZORDER | SWP_NOSENDCHANGING
        if after is None:
            flags |= win32con.SWP_NOZORDER
        if current != target or after is not None:
            win32gui.SetWindowPos(hwnd, after or 0, *target, flags)
    except Exception as exc:
        log.debug("No se pudo colocar %s: %s", hwnd, exc)
        return None
    rect = visible_rect(hwnd)
    return (rect[2], rect[3]) if rect else None
