"""Calidad y rendimiento de Roblox.

Roblox lee estos ajustes al abrirse, de dos archivos propios:
  - GlobalBasicSettings_13.xml: lo mismo que el menú de ajustes del juego (FPS máximos, calidad, volumen).
  - ClientAppSettings.json: opciones avanzadas. Roblox ignora las que no están en su lista permitida y lo
    deja escrito en su registro («Denied local configuration»); las de aquí están comprobadas contra ella.

Son archivos de configuración: no se toca el proceso ni la memoria del cliente. Lo que se cambia del
XML se guarda en la configuración para devolverlo tal cual al volver al perfil Normal.
"""
import json
import logging
import os
import re
from pathlib import Path

from core import launcher
from storage.config import Config
from utils.i18n import N_, t
from utils.paths import roblox_local_dir

log = logging.getLogger("rendimiento")

FPS_OPTIONS = (30, 60, 120, 144, 240)
QUALITY_LEVELS = 10
OLD_FPS_FLAG = "DFIntTaskSchedulerTargetFps"    # Roblox ya la rechaza; la usaban versiones anteriores

FLAG_GROUPS = {
    "low_textures": {"DFFlagTextureQualityOverrideEnabled": True, "DFIntTextureQualityOverride": 0},
    "no_grass": {"FIntFRMMaxGrassDistance": 0, "FIntFRMMinGrassDistance": 0, "FIntGrassMovementReducedMotionFactor": 0},
    "no_antialiasing": {"FIntDebugForceMSAASamples": 0},
    "low_detail": {"DFIntCSGLevelOfDetailSwitchingDistance": 0, "DFIntCSGLevelOfDetailSwitchingDistanceL12": 0,
                   "DFIntCSGLevelOfDetailSwitchingDistanceL23": 0, "DFIntCSGLevelOfDetailSwitchingDistanceL34": 0},
    "simple_lighting": {"DFFlagDebugPauseVoxelizer": True},
    "gray_sky": {"FFlagDebugSkyGray": True},
}
QUALITY_FLAG = "DFIntDebugFRMQualityLevelOverride"
MANAGED_FLAGS = {QUALITY_FLAG, OLD_FPS_FLAG, *(flag for group in FLAG_GROUPS.values() for flag in group)}

_OFF = {"fps": 0, "quality": 0, "low_textures": False, "no_grass": False, "no_antialiasing": False,
        "low_detail": False, "simple_lighting": False, "gray_sky": False, "mute": False,
        "low_priority": False, "efficiency": False, "cores": 0}
PRESETS = {
    "normal": _OFF,
    "balanced": {**_OFF, "fps": 60, "quality": 5, "no_antialiasing": True},
    "saver": {**_OFF, "fps": 30, "quality": 3, "low_textures": True, "no_grass": True, "no_antialiasing": True,
              "mute": True, "low_priority": True},
    "max_saver": {**_OFF, "fps": 30, "quality": 1, "low_textures": True, "no_grass": True, "no_antialiasing": True,
                  "low_detail": True, "simple_lighting": True, "gray_sky": True, "mute": True,
                  "low_priority": True, "efficiency": True},
}
PRESET_NAMES = {"normal": N_("Normal"), "balanced": N_("Equilibrado"), "saver": N_("Ahorro"),
                "max_saver": N_("Máximo ahorro"), "custom": N_("Personalizado")}


def current_preset(section: dict) -> str:
    for name, values in PRESETS.items():
        if all(section.get(key) == value for key, value in values.items()):
            return name
    return "custom"


def wanted_settings(section: dict) -> dict:
    """Valores del XML de Roblox que pide la configuración."""
    wanted = {}
    if section.get("fps"):
        wanted["FramerateCap"] = int(section["fps"])
    level = int(section.get("quality") or 0)
    if level:
        wanted["SavedQualityLevel"] = level
        wanted["GraphicsQualityLevel"] = 1 + round((level - 1) * 20 / (QUALITY_LEVELS - 1))
        wanted["GraphicsOptimizationMode"] = 0 if level <= 3 else 1 if level <= 7 else 2
    if section.get("mute"):
        wanted["MasterVolume"] = 0
    return wanted


def wanted_flags(section: dict) -> dict:
    flags = {}
    for name, group in FLAG_GROUPS.items():
        if section.get(name):
            flags.update(group)
    level = int(section.get("quality") or 0)
    if level:
        flags[QUALITY_FLAG] = wanted_settings(section)["GraphicsQualityLevel"]
    return flags


# ------------------------------------------------------------------------- ClientAppSettings.json
def _flag_files() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    files = [d / "ClientSettings" / "ClientAppSettings.json" for d in launcher.player_version_dirs()]
    # Bloxstrap y Fishstrap copian su propia carpeta encima de la versión al abrir Roblox
    for manager in ("Bloxstrap", "Fishstrap"):
        if (local / manager / "Modifications").is_dir():
            files.append(local / manager / "Modifications" / "ClientSettings" / "ClientAppSettings.json")
    return files


def _write_flags(path: Path, flags: dict) -> None:
    data = json.loads(path.read_text("utf-8")) if path.exists() else {}
    merged = {key: value for key, value in data.items() if key not in MANAGED_FLAGS}
    merged.update(flags)
    if merged != data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2), "utf-8")


# ------------------------------------------------------------------------- GlobalBasicSettings_13.xml
def _settings_path() -> Path:
    return roblox_local_dir() / "GlobalBasicSettings_13.xml"


def _pattern(key: str) -> str:
    return rf'(<(?:int|token|float) name="{key}">)([^<]*)(<)'


def _write_settings(section: dict, wanted: dict) -> dict:
    """Aplica `wanted`, devuelve lo que ya no se pide y devuelve los originales que hay que recordar."""
    original = dict(section.get("original") or {})
    path = _settings_path()
    if not path.exists():
        return original if wanted else {}
    text = path.read_bytes().decode("utf-8")   # en bytes, para no cambiar sus saltos de línea
    values = {key: value for key, value in original.items() if key not in wanted}
    for key, value in wanted.items():
        found = re.search(_pattern(key), text)
        if found:
            original.setdefault(key, found.group(2))
            values[key] = value
    changed = text
    for key, value in values.items():
        changed = re.sub(_pattern(key), rf"\g<1>{value}\g<3>", changed)
    if changed != text:
        temporary = path.with_suffix(".rbxfarm.tmp")
        temporary.write_bytes(changed.encode("utf-8"))
        os.replace(temporary, path)
    return {key: value for key, value in original.items() if key in wanted}


def apply(cfg: Config) -> None:
    """Deja los archivos de Roblox como pide la configuración. Vale para las ventanas que se abran después."""
    section = cfg.section("performance")
    flags = wanted_flags(section)
    for path in _flag_files():
        try:
            _write_flags(path, flags)
        except (OSError, ValueError) as exc:
            log.warning(t("No se pudo escribir %s: %s"), path, exc)
    try:
        cfg.set("performance.original", _write_settings(section, wanted_settings(section)))
    except (OSError, ValueError) as exc:
        log.warning(t("No se pudo escribir %s: %s"), _settings_path(), exc)
