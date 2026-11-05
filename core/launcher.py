"""Construcción de enlaces de lanzamiento, multi-instancia (mutex) y límite de FPS."""
import logging
import os
import random
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import psutil

from core.models import LaunchTarget
from utils.paths import roblox_local_dir
from utils.winapi import ROBLOX_EXE, main_window_for_pid
from utils.i18n import t

log = logging.getLogger(__name__)

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


# --------------------------------------------------------------------------- destino
def parse_target(link: str, job_id: str = "", private_code: str = "") -> LaunchTarget:
    """Acepta un PlaceId, un enlace de juego, de servidor privado o de 'share'."""
    link = (link or "").strip()
    target = LaunchTarget(raw=link, job_id=(job_id or "").strip(), private_link_code=(private_code or "").strip())
    if not link:
        raise ValueError(t("Escribe un PlaceId o pega el enlace del juego"))
    if link.isdigit():
        target.place_id = int(link)
        return target

    url = urlparse(link if "://" in link else "https://" + link)
    query = {k.lower(): v[0] for k, v in parse_qs(url.query).items()}

    if "/share" in url.path and query.get("code"):
        target.share_code = query["code"]
        return target

    m = re.search(r"/games/(\d+)", url.path)
    if m:
        target.place_id = int(m.group(1))
    elif query.get("placeid", "").isdigit():
        target.place_id = int(query["placeid"])
    else:
        raise ValueError(t("No se encontró el PlaceId en el enlace"))

    target.private_link_code = target.private_link_code or query.get("privateserverlinkcode", "")
    job = query.get("gameinstanceid") or query.get("jobid") or ""
    if not target.job_id and UUID_RE.fullmatch(job or ""):
        target.job_id = job
    return target


def build_player_uri(ticket: str, target: LaunchTarget) -> str:
    """URI roblox-player: con ticket de autenticación (inicio de sesión por cookie)."""
    tracker = str(random.randint(100_000_000_000, 999_999_999_999))
    base = "https://www.roblox.com/Game/PlaceLauncher.ashx"
    if target.private_link_code:
        req = (f"{base}?request=RequestPrivateGame&placeId={target.place_id}"
               f"&linkCode={target.private_link_code}")
    elif target.job_id:
        req = (f"{base}?request=RequestGameJob&browserTrackerId={tracker}&placeId={target.place_id}"
               f"&gameId={target.job_id}&isPlayTogetherGame=false")
    else:
        req = (f"{base}?request=RequestGame&browserTrackerId={tracker}&placeId={target.place_id}"
               f"&isPlayTogetherGame=false")
    launch_time = int(time.time() * 1000)
    return ("roblox-player:1+launchmode:play"
            f"+gameinfo:{ticket}+launchtime:{launch_time}"
            f"+placelauncherurl:{quote(req, safe='')}"
            f"+browsertrackerid:{tracker}+robloxLocale:es_es+gameLocale:es_es+channel:+LaunchExp:InApp")


def build_deeplink(target: LaunchTarget) -> str:
    """Enlace roblox:// que usa la sesión ya iniciada en la app de Roblox."""
    uri = f"roblox://experiences/start?placeId={target.place_id}"
    if target.private_link_code:
        uri += f"&linkCode={target.private_link_code}"
    elif target.job_id:
        uri += f"&gameInstanceId={target.job_id}"
    return uri


def open_uri(uri: str) -> None:
    os.startfile(uri)  # ShellExecute: respeta el manejador registrado (Roblox, Bloxstrap, ...)


def roblox_pids() -> set[int]:
    pids = set()
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").lower() == ROBLOX_EXE.lower():
                pids.add(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


TRAY_ARGUMENT = "--launch-to-tray"


def close_tray_agents(keep: set[int]) -> bool:
    """Cierra el proceso oculto que Roblox deja en la bandeja al cerrar su ventana.

    Mientras exista, los clientes nuevos le pasan el enlace y se cierran, así que no se abren varios.
    Solo se cierra si no tiene ventana a la vista ni pertenece a una instancia (`keep`).
    """
    closed = False
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if (proc.info["name"] == ROBLOX_EXE and proc.pid not in keep and TRAY_ARGUMENT in proc.cmdline()
                    and not main_window_for_pid(proc.pid)):
                proc.kill()
                proc.wait(5)
                closed = True
                log.info(t("Cerrado el proceso de Roblox en la bandeja (%s)"), proc.pid)
        except (psutil.Error, psutil.TimeoutExpired):
            continue
    return closed


# --------------------------------------------------------------------------- multi-instancia
class MultiInstanceMutex:
    """Roblox comprueba un objeto con nombre para permitir un solo cliente. Si lo creamos
    nosotros primero y lo mantenemos abierto, cada cliente nuevo se abre sin cerrar los demás.
    Es la técnica estándar: no toca al proceso de Roblox."""

    NAMES = ("ROBLOX_singletonMutex", "ROBLOX_singletonEvent")

    def __init__(self):
        self._handles = []

    @property
    def active(self) -> bool:
        return bool(self._handles)

    def acquire(self) -> bool:
        if self._handles:
            return True
        import win32api
        import win32event
        import winerror
        for name in self.NAMES:
            try:
                handle = win32event.CreateMutex(None, True, name)
                if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                    log.warning(t("El mutex %s ya existía: cierra Roblox y vuelve a abrir las instancias "
                                "si no se abren varias a la vez"), name)
                self._handles.append(handle)
            except Exception as exc:
                log.debug("No se pudo crear %s: %s", name, exc)
        if self._handles:
            log.info(t("Multi-instancia activa"))
        return bool(self._handles)

    def release(self) -> None:
        import win32api
        for handle in self._handles:
            try:
                win32api.CloseHandle(handle)
            except Exception:
                pass
        self._handles = []


# --------------------------------------------------------------------------- instalaciones
def player_version_dirs() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roots = [roblox_local_dir() / "Versions", local / "Bloxstrap" / "Versions", local / "Fishstrap" / "Versions"]
    dirs = []
    for root in roots:
        if root.is_dir():
            dirs += [p for p in root.iterdir() if (p / ROBLOX_EXE).exists()]
    return dirs


# --------------------------------------------------------------------------- logs del cliente
def roblox_log_dir() -> Path:
    return roblox_local_dir() / "logs"


def find_log_for_process(create_time: float, claimed: set[str]) -> str | None:
    """Empareja un proceso con su archivo de log por la hora de creación (el log es un archivo
    de texto en disco que escribe el propio cliente; no se lee memoria)."""
    folder = roblox_log_dir()
    if not folder.is_dir():
        return None
    best, best_gap = None, 60.0
    for path in folder.glob("*Player*.log"):
        key = str(path)
        if key in claimed:
            continue
        try:
            gap = path.stat().st_ctime - create_time
        except OSError:
            continue
        if -5.0 <= gap < best_gap:
            best, best_gap = key, gap
    return best
