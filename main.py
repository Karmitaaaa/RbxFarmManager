"""RbxFarm Manager — punto de entrada."""
import sys
import threading

import win32event
from PySide6.QtCore import QCoreApplication, QLibraryInfo, Qt, QTranslator
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from storage import crypto
from storage.config import Config
from storage.vault import Vault
from ui import theme, widgets
from ui.context import AppContext
from ui.dialogs import UnlockDialog, WelcomeDialog
from ui.main_window import MainWindow
from utils.logger import setup_logging
from utils.i18n import current_language, set_language, system_language, t


def install_excepthook(log) -> None:
    def handle(exc_type, exc, tb):
        log.critical(t("Error no controlado"), exc_info=(exc_type, exc, tb))
        QMessageBox.critical(None, "RbxFarm Manager", t("Error inesperado:\n{0}\n\nDetalles en el log.", exc))

    sys.excepthook = handle
    threading.excepthook = lambda args: log.critical(t("Error en hilo %s"), args.thread.name,
                                                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def open_vault(vault: Vault) -> bool:
    """El baúl se cifra con tu usuario de Windows (DPAPI) y se abre solo.
    Solo si activaste la contraseña maestra en Ajustes se pide al abrir."""
    if vault.stored_mode() == "password":
        return UnlockDialog(vault).exec() == QDialog.Accepted
    try:
        vault.unlock()
        return True
    except crypto.WrongPassword as exc:
        QMessageBox.critical(None, "RbxFarm Manager", str(exc))
        return False


def install_qt_translator(app: QApplication) -> QTranslator:
    """Traduce lo que dibuja Qt por su cuenta, como los botones Sí/No de los avisos."""
    translator = QTranslator(app)
    if translator.load(f"qtbase_{current_language()}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
    return translator


def main() -> int:
    log = setup_logging()
    # El instalador usa este mutex para pedir que se cierre la app antes de actualizarla o desinstalarla
    app_mutex = win32event.CreateMutex(None, False, "RbxFarmManagerAppMutex")  # noqa: F841 (debe vivir)
    # Necesario para el navegador integrado del inicio de sesión con Roblox
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("RbxFarm Manager")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(theme.app_font())
    app.setWindowIcon(widgets.app_icon())
    install_excepthook(log)

    config = Config()
    set_language(config.get("language") or system_language())
    translator = install_qt_translator(app)
    widgets.current_theme["name"] = config.get("theme", "classic") if config.get("theme") in theme.PALETTES else "classic"
    app.setStyleSheet(theme.stylesheet(widgets.current_theme["name"]))

    vault = Vault()
    first_run = not vault.exists()
    if first_run:
        vault.create("dpapi")
    elif not open_vault(vault):
        return 0

    ctx = AppContext(config, vault)
    if first_run:
        while WelcomeDialog(ctx).exec() == WelcomeDialog.LANGUAGE_CHANGED:
            app.removeTranslator(translator)
            translator = install_qt_translator(app)
    window = MainWindow(ctx)
    ctx.start()
    if config.get("start_minimized") and config.get("minimize_to_tray"):
        window.hide()
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
