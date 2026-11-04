"""Rutas de datos de la aplicación (todo se guarda en %APPDATA%\\RbxFarmManager)."""
import os
import sys
from pathlib import Path

APP_NAME = "RbxFarmManager"


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_dir() / "logs"
    path.mkdir(exist_ok=True)
    return path


def macros_dir() -> Path:
    path = app_dir() / "macros"
    path.mkdir(exist_ok=True)
    return path


def avatars_dir() -> Path:
    path = app_dir() / "avatars"
    path.mkdir(exist_ok=True)
    return path


def vault_path() -> Path:
    return app_dir() / "vault.dat"


def config_path() -> Path:
    return app_dir() / "settings.json"


def resource_path(relative: str) -> Path:
    """Ruta a recursos empaquetados (funciona en desarrollo y con PyInstaller)."""
    base = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
    return Path(base) / relative


def roblox_local_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Roblox"
