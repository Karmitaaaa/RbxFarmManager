"""Vista previa de las ventanas de Roblox.

Copia cada cierto tiempo la imagen de cada ventana con la API pública PrintWindow, como hace una captura
de pantalla: no lee ni modifica la memoria del cliente. Solo trabaja mientras la pestaña Instancias se ve.
"""
import logging
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage

from storage.config import Config
from utils import winapi

log = logging.getLogger("vista-previa")

PREVIEW_WIDTH = 480


class PreviewCapturer(QObject):
    frame = Signal(str, QImage)  # id de instancia, imagen reducida

    def __init__(self, manager, config: Config):
        super().__init__()
        self.manager = manager
        self.cfg = config
        self.active = False     # lo activa la pestaña Instancias mientras está a la vista
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="previews", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._wake.set()

    def set_active(self, active: bool) -> None:
        self.active = active
        if active:
            self._wake.set()  # primera imagen al momento, sin esperar al intervalo

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(max(1, int(self.cfg.get("previews.interval_s", 2))))
            self._wake.clear()
            if self._stop.is_set() or not self.active or not self.cfg.get("previews.enabled", True):
                continue
            for inst in self.manager.snapshot():
                try:
                    self._capture(inst)
                except Exception:
                    log.exception("Fallo al capturar la ventana de %s", inst.account.alias)

    def _capture(self, inst) -> None:
        if not winapi.is_window(inst.hwnd) or winapi.is_minimized(inst.hwnd):
            return
        result = winapi.capture_window(inst.hwnd)
        if result is None:
            return
        data, width, height = result
        image = QImage(data, width, height, width * 4, QImage.Format_RGB32)
        # scaled()/copy() crean una imagen propia: `data` deja de hacer falta
        image = (image.scaledToWidth(PREVIEW_WIDTH, Qt.SmoothTransformation) if width > PREVIEW_WIDTH
                 else image.copy())
        self.frame.emit(inst.id, image)
