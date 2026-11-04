"""Inicio de sesión con la página oficial de Roblox dentro de la app (navegador integrado).

Tú escribes el usuario, la contraseña, el captcha y la verificación directamente en roblox.com: la app
nunca ve la contraseña. Cuando Roblox crea la cookie de sesión (.ROBLOSECURITY) en el navegador integrado,
la app la lee, comprueba con roblox.com a qué cuenta pertenece y la guarda cifrada.
Cada ventana usa un perfil de navegador temporal y limpio, así se pueden añadir varias cuentas seguidas.
"""
import logging

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from core import roblox_api
from ui.icons import G, GlyphLabel
from ui.workers import run_async
from utils.i18n import N_, current_language, t

log = logging.getLogger("login")

LOGIN_URL = "https://www.roblox.com/login"
WAITING = N_("Inicia sesión con tu cuenta de Roblox. La ventana se cerrará sola al entrar.")


class RobloxLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Import diferido: el navegador integrado solo se carga si se usa esta ventana
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self.cookie = ""
        self.user: dict = {}
        self._seen: set[str] = set()
        self.setWindowTitle(t("Iniciar sesión con Roblox"))
        self.resize(540, 800)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(44)
        b = QHBoxLayout(bar)
        b.setContentsMargins(14, 0, 14, 0)
        b.addWidget(GlyphLabel(G.LOCK, 15, "#FFFFFF"))
        self.host = QLabel("roblox.com")
        self.host.setStyleSheet("color: #FFFFFF; font-weight: 700; background: transparent;")
        b.addWidget(self.host)
        b.addStretch(1)
        note = QLabel(t("Página oficial de Roblox · tu contraseña no pasa por RbxFarm"))
        note.setStyleSheet("color: #FFFFFF; font-size: 9pt; background: transparent;")
        b.addWidget(note)
        lay.addWidget(bar)

        # Perfil sin nombre = temporal (no guarda nada en disco y empieza sin sesión)
        self.profile = QWebEngineProfile(self)
        self.profile.setHttpUserAgent(roblox_api.USER_AGENT)
        self.profile.setHttpAcceptLanguage(f"{current_language()},en;q=0.5")
        class SingleWindowPage(QWebEnginePage):
            def createWindow(self, _type):
                return self  # las ventanas emergentes (Google, Apple…) se abren aquí mismo

        self.view = QWebEngineView(self)
        self.page = SingleWindowPage(self.profile, self.view)
        self.view.setPage(self.page)
        self.view.urlChanged.connect(lambda url: self.host.setText(url.host() or "roblox.com"))
        self.profile.cookieStore().cookieAdded.connect(self._cookie_added)
        lay.addWidget(self.view, 1)

        self.status = QLabel(t(WAITING))
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        self.status.setContentsMargins(14, 8, 14, 8)
        lay.addWidget(self.status)
        self.view.load(QUrl(LOGIN_URL))

    def _cookie_added(self, cookie) -> None:
        if cookie.name().data() != b".ROBLOSECURITY" or not cookie.domain().endswith("roblox.com"):
            return
        value = cookie.value().data().decode("utf-8", errors="ignore")
        if not value or value in self._seen or self.cookie:
            return
        self._seen.add(value)
        self.status.setText(t("Comprobando la sesión con Roblox…"))
        run_async(roblox_api.get_authenticated_user, value,
                  on_done=lambda info, v=value: self._logged_in(v, info),
                  on_error=lambda _exc: self.status.setText(t(WAITING)))

    def _logged_in(self, cookie: str, info: dict) -> None:
        if self.cookie:
            return
        self.cookie, self.user = cookie, info
        log.info(t("Sesión iniciada con Roblox: %s"), info.get("name"))
        self.accept()

    def done(self, result: int) -> None:
        # La página debe liberarse antes que su perfil
        self.profile.cookieStore().cookieAdded.disconnect(self._cookie_added)
        self.page.deleteLater()
        self.profile.deleteLater()
        super().done(result)


def login_with_roblox(parent=None) -> tuple[str, dict] | None:
    """Abre la ventana y devuelve (cookie, {"id", "name", "displayName"}) o None si se cancela."""
    dlg = RobloxLoginDialog(parent)
    return (dlg.cookie, dlg.user) if dlg.exec() == QDialog.Accepted else None
