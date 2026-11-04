"""Versión de la app (archivo VERSION, incluido también en el .exe)."""
from utils.paths import resource_path


def _read_version() -> str:
    try:
        return resource_path("VERSION").read_text("utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


APP_VERSION = _read_version()


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Las partes no numéricas cuentan como 0."""
    parts = []
    for piece in text.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(candidate: str, current: str = APP_VERSION) -> bool:
    return parse_version(candidate) > parse_version(current)
