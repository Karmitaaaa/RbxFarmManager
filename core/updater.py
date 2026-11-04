"""Actualizaciones desde las Releases de GitHub.

1. check_latest(): pregunta a la API pública de GitHub por la última Release.
2. download(): descarga el instalador mostrando el progreso y comprueba su SHA-256.
3. launch_installer(): lo ejecuta en modo silencioso; el instalador cierra la app, la actualiza y la
   vuelve a abrir (/RELAUNCH=1). Tus cuentas y ajustes de %APPDATA% no se tocan.
"""
import hashlib
import logging
import os
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import requests

from utils.version import APP_VERSION, is_newer
from utils.i18n import t

log = logging.getLogger("actualizaciones")

REPO = "Karmitaaaa/RbxFarmManager"
INSTALLER_ASSET = "RbxFarmManager-Setup.exe"
RELEASES_URL = f"https://github.com/{REPO}/releases"
TIMEOUT = 15


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    version: str
    notes: str
    page_url: str
    asset_url: str
    size: int
    sha256: str


def check_latest(current: str = APP_VERSION) -> UpdateInfo | None:
    """Devuelve la Release más reciente si es más nueva que `current`; si no, None."""
    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=TIMEOUT,
                         headers={"Accept": "application/vnd.github+json", "User-Agent": "RbxFarmManager"})
    except requests.RequestException as exc:
        raise UpdateError(t("No se pudo conectar con GitHub: {0}", exc)) from exc
    if r.status_code == 404:
        return None  # todavía no hay ninguna Release publicada
    if not r.ok:
        raise UpdateError(t("GitHub respondió {0}", r.status_code))
    data = r.json()
    version = str(data.get("tag_name", "")).lstrip("vV")
    if not version or not is_newer(version, current):
        return None
    asset = next((a for a in data.get("assets", []) if a.get("name") == INSTALLER_ASSET), None)
    if asset is None:
        raise UpdateError(t("La versión {0} no incluye {1}", version, INSTALLER_ASSET))
    digest = str(asset.get("digest") or "")
    return UpdateInfo(version=version, notes=data.get("body") or "", page_url=data.get("html_url", RELEASES_URL),
                      asset_url=asset["browser_download_url"], size=int(asset.get("size", 0)),
                      sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "")


def download(info: UpdateInfo, progress=None, cancel: threading.Event | None = None) -> Path:
    """Descarga el instalador a %TEMP% y comprueba que llegó entero. progress(bytes, total)."""
    dest = Path(tempfile.gettempdir()) / f"RbxFarmManager-Setup-{info.version}.exe"
    sha = hashlib.sha256()
    done = 0
    try:
        with requests.get(info.asset_url, stream=True, timeout=TIMEOUT,
                          headers={"User-Agent": "RbxFarmManager"}) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or info.size or 0)
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if cancel is not None and cancel.is_set():
                        raise UpdateError(t("Descarga cancelada"))
                    fh.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except requests.RequestException as exc:
        dest.unlink(missing_ok=True)
        raise UpdateError(t("Falló la descarga: {0}", exc)) from exc
    except UpdateError:
        dest.unlink(missing_ok=True)
        raise
    if info.sha256 and sha.hexdigest() != info.sha256:
        dest.unlink(missing_ok=True)
        raise UpdateError(t("El archivo descargado está dañado (la huella SHA-256 no coincide)"))
    log.info(t("Actualización %s descargada (%.1f MB)"), info.version, done / 1_048_576)
    return dest


def launch_installer(path: Path) -> None:
    """Ejecuta el instalador en modo silencioso y desligado de esta app (que debe cerrarse después)."""
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                      "/RELAUNCH=1"], creationflags=flags, close_fds=True, cwd=os.path.dirname(path))
    log.info(t("Instalador de la actualización lanzado: %s"), path)
