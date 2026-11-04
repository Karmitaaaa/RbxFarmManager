"""Aviso de actualizaciones: comprobación periódica, banner y ventana de actualización."""
import logging
import threading

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser,
                               QVBoxLayout)

from core import updater
from storage.config import Config
from ui.icons import G, GlyphLabel
from ui.widgets import link_button, make_card, muted_label, styled_button
from ui.workers import run_async
from utils.version import APP_VERSION
from utils.i18n import t

log = logging.getLogger("actualizaciones")

CHECK_EVERY_MS = 6 * 3600 * 1000
FIRST_CHECK_MS = 5000


class UpdateChecker(QObject):
    """Comprueba GitHub al abrir la app y cada 6 horas (si está activado en Ajustes)."""

    available = Signal(object)          # UpdateInfo
    finished = Signal(object, str)      # UpdateInfo | None, error ("" si fue bien)

    def __init__(self, config: Config):
        super().__init__()
        self.cfg = config
        self.latest: updater.UpdateInfo | None = None
        self._busy = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self.check(manual=False))

    def start(self) -> None:
        self._timer.start(CHECK_EVERY_MS)
        QTimer.singleShot(FIRST_CHECK_MS, lambda: self.check(manual=False))

    def check(self, manual: bool = True) -> None:
        if self._busy or (not manual and not self.cfg.get("check_updates", True)):
            return
        self._busy = True

        def done(info):
            self._busy = False
            self.latest = info
            self.finished.emit(info, "")
            if info and (manual or info.version != self.cfg.get("skipped_version")):
                log.info(t("Hay una versión nueva: %s (tienes %s)"), info.version, APP_VERSION)
                self.available.emit(info)

        def fail(exc):
            self._busy = False
            log.debug("No se pudo comprobar actualizaciones: %s", exc)
            self.finished.emit(None, str(exc))

        run_async(updater.check_latest, on_done=done, on_error=fail)


class UpdateBanner(QFrame):
    """Franja bajo la barra azul: «Hay una nueva versión… [Actualizar ahora]»."""

    update_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("UpdateBanner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 12, 6)
        lay.setSpacing(10)
        lay.addWidget(GlyphLabel(G.DOWNLOAD, 16))
        self.text = QLabel()
        self.text.setStyleSheet("font-weight: 600; background: transparent;")
        lay.addWidget(self.text, 1)
        btn = styled_button(t("Actualizar ahora"), "primary", self.update_clicked.emit, icon=G.DOWNLOAD)
        lay.addWidget(btn)
        lay.addWidget(link_button(t("Más tarde"), self.hide))
        self.hide()

    def show_for(self, info: updater.UpdateInfo) -> None:
        self.text.setText(t("Hay una versión nueva de RbxFarm Manager: {0} (tienes {1}). Se actualiza con un clic y tus "
                            "cuentas se conservan.", info.version, APP_VERSION))
        self.show()


class _Progress(QObject):
    changed = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)


class UpdateDialog(QDialog):
    """Novedades + descarga con progreso + instalación. on_ready(path) lanza el instalador y cierra la app."""

    def __init__(self, info: updater.UpdateInfo, cfg: Config, on_ready, parent=None):
        super().__init__(parent)
        self.info, self.cfg, self.on_ready = info, cfg, on_ready
        self._cancel = threading.Event()
        self._signals = _Progress()
        self._signals.changed.connect(self._on_progress)
        self._signals.done.connect(self._on_downloaded)
        self._signals.failed.connect(self._on_failed)
        self.setWindowTitle(t("Actualización disponible"))
        self.setMinimumSize(560, 520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(12)
        title = QLabel(f"RbxFarm Manager {info.version}")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        outer.addWidget(muted_label(t("Tienes la versión {0}. La app descargará la nueva ({1:.0f} MB), se cerrará un momento y volverá "
                                      "a abrirse ya actualizada. Tus cuentas, juegos y macros se conservan.", APP_VERSION, info.size / 1_048_576)))

        card, lay = make_card(12, 6)
        head = QHBoxLayout()
        notes_title = QLabel(t("Novedades"))
        notes_title.setObjectName("CardTitle")
        head.addWidget(notes_title)
        head.addStretch(1)
        head.addWidget(link_button(t("Ver en GitHub"), lambda: QDesktopServices.openUrl(QUrl(info.page_url))))
        lay.addLayout(head)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(info.notes or t("Sin notas para esta versión."))
        notes.setStyleSheet("border: none; background: transparent;")
        lay.addWidget(notes)
        outer.addWidget(card, 1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        outer.addWidget(self.progress)
        self.status = muted_label("")
        outer.addWidget(self.status)

        row = QHBoxLayout()
        self.skip_btn = link_button(t("Saltar esta versión"), self._skip)
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        self.later_btn = styled_button(t("Más tarde"), "", self.reject)
        row.addWidget(self.later_btn)
        self.update_btn = styled_button(t("Actualizar ahora"), "primary", self._start, icon=G.DOWNLOAD)
        self.update_btn.setDefault(True)
        row.addWidget(self.update_btn)
        outer.addLayout(row)

    def _skip(self) -> None:
        self.cfg.set("skipped_version", self.info.version)
        self.reject()

    def _start(self) -> None:
        self.update_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.later_btn.setText(t("Cancelar"))
        self.later_btn.clicked.disconnect()
        self.later_btn.clicked.connect(self._cancel_download)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText(t("Descargando la actualización desde GitHub…"))
        threading.Thread(target=self._download, name="update-download", daemon=True).start()

    def _download(self) -> None:
        try:
            path = updater.download(self.info, lambda done, total: self._signals.changed.emit(done, total),
                                    self._cancel)
        except Exception as exc:
            self._signals.failed.emit(str(exc))
        else:
            self._signals.done.emit(path)

    def _cancel_download(self) -> None:
        self._cancel.set()
        self.reject()

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.progress.setValue(int(done * 100 / total))
            self.progress.setFormat(f"{done / 1_048_576:.0f} / {total / 1_048_576:.0f} MB  (%p%)")

    def _on_failed(self, error: str) -> None:
        if self._cancel.is_set():
            return
        self.status.setText(f"✖ {error}")
        self.status.setStyleSheet("color: #E2231A;")
        self.update_btn.setEnabled(True)
        self.update_btn.setText(t("Reintentar"))

    def _on_downloaded(self, path) -> None:
        self.progress.setValue(100)
        self.status.setText(t("Instalando… la app se cerrará y se volverá a abrir sola."))
        QTimer.singleShot(600, lambda: self.on_ready(path))

    def closeEvent(self, event):
        self._cancel.set()
        super().closeEvent(event)
