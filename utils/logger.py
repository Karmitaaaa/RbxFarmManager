"""Logging a archivo rotativo + puente hacia la UI. Las cookies nunca se escriben en el log."""
import logging
import re
from logging.handlers import RotatingFileHandler

from utils.paths import logs_dir

_COOKIE_RE = re.compile(r"_\|WARNING:-DO-NOT-SHARE-THIS[^\s\"';]*", re.IGNORECASE)
_TICKET_RE = re.compile(r"(gameinfo:)[^+\s]+", re.IGNORECASE)


def redact(text: str) -> str:
    text = _COOKIE_RE.sub("<cookie-oculta>", text)
    return _TICKET_RE.sub(r"\1<ticket-oculto>", text)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg, record.args = redact(message), None
        return True


class UiHandler(logging.Handler):
    """Reenvía los registros a una función (la conecta la ventana principal)."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.sink = None

    def emit(self, record: logging.LogRecord) -> None:
        if self.sink is None:
            return
        try:
            self.sink(record.levelname, self.format(record))
        except Exception:
            pass


ui_handler = UiHandler()


def setup_logging() -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(logs_dir() / "rbxfarm.log", maxBytes=2_000_000,
                                       backupCount=5, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    file_handler.addFilter(RedactFilter())

    ui_handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S"))
    ui_handler.addFilter(RedactFilter())

    root.addHandler(file_handler)
    root.addHandler(ui_handler)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return logging.getLogger("rbxfarm")
