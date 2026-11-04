"""Idiomas de la interfaz.

El texto fuente del código está en español. Cada archivo locales/<código>.json traduce texto → traducción
y lleva su nombre en "@language". Para añadir un idioma basta con copiar en.json, traducirlo y guardarlo con
otro código: aparecerá solo en Ajustes. tools/check_i18n.py avisa de los textos sin traducir.

    t("Hay {0} cuentas", n)     traduce y rellena los huecos
    N_("Abierto")               marca un texto que se traduce después, al mostrarlo con t()
"""
import ctypes
import json
import logging

from utils.paths import resource_path

log = logging.getLogger(__name__)

SOURCE_LANGUAGE = "es"
SOURCE_NAME = "Español"
LANG_SPANISH_PRIMARY_ID = 0x0A

_current = SOURCE_LANGUAGE
_table: dict[str, str] = {}


def N_(text: str) -> str:
    return text


def t(text: str, *args) -> str:
    translated = _table.get(text, text)
    return translated.format(*args) if args else translated


def _load(code: str) -> dict[str, str]:
    return json.loads(resource_path(f"locales/{code}.json").read_text("utf-8"))


def available_languages() -> dict[str, str]:
    """{código: nombre}. Incluye el español (texto fuente) y cada JSON de locales/."""
    languages = {SOURCE_LANGUAGE: SOURCE_NAME}
    for path in sorted(resource_path("locales").glob("*.json")):
        try:
            languages[path.stem] = _load(path.stem).get("@language", path.stem)
        except (OSError, ValueError) as exc:
            log.warning("Idioma %s dañado: %s", path.stem, exc)
    return languages


def system_language() -> str:
    """Español si Windows está en español; si no, inglés."""
    primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    return SOURCE_LANGUAGE if primary == LANG_SPANISH_PRIMARY_ID else "en"


def set_language(code: str) -> None:
    global _current, _table
    table: dict[str, str] = {}
    if code != SOURCE_LANGUAGE:
        try:
            table = _load(code)
        except (OSError, ValueError) as exc:
            log.warning("No se pudo cargar el idioma %s: %s", code, exc)
            code = SOURCE_LANGUAGE
    _current, _table = code, table


def current_language() -> str:
    return _current
