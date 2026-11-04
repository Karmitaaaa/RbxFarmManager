"""Diálogos: bienvenida, desbloqueo del baúl, edición de cuenta y contraseñas de import/export."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget)

from core import roblox_api
from core.models import LOGIN_COOKIE, LOGIN_CURRENT, LOGIN_METHODS, Account
from storage import crypto
from storage.vault import Vault
from ui.icons import G
from ui.roblox_login import login_with_roblox
from ui.widgets import app_icon, link_button, make_card, muted_label, styled_button
from ui.workers import run_async


def _password_field(placeholder: str = "") -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.Password)
    field.setPlaceholderText(placeholder)
    return field


def _brand_header(title: str, subtitle: str) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(6)
    logo = QLabel()
    logo.setPixmap(app_icon().pixmap(72, 72))
    logo.setAlignment(Qt.AlignCenter)
    lay.addWidget(logo)
    title_label = QLabel(title)
    title_label.setObjectName("Hello")
    title_label.setStyleSheet("font-size: 22pt;")
    title_label.setAlignment(Qt.AlignCenter)
    lay.addWidget(title_label)
    sub = muted_label(subtitle)
    sub.setAlignment(Qt.AlignCenter)
    sub.setStyleSheet("font-size: 11pt;")
    lay.addWidget(sub)
    return lay


class WelcomeDialog(QDialog):
    """Primera vez: un solo botón para entrar con la cuenta principal de Roblox."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Bienvenido a RbxFarm")
        self.setFixedWidth(440)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 22)
        outer.setSpacing(16)
        outer.addLayout(_brand_header("Bienvenido a RbxFarm",
                                      "Inicia sesión con tu cuenta principal de Roblox para empezar."))

        card, lay = make_card(20, 10)
        login = styled_button("Iniciar sesión con Roblox", "secondary", self.login, big=True, icon=G.PERSON)
        login.setDefault(True)
        lay.addWidget(login)
        lay.addWidget(muted_label("Se abre la página oficial de Roblox. Tu contraseña la escribes allí y "
                                  "RbxFarm nunca la ve."))
        self.status = QLabel()
        self.status.setStyleSheet("color: #E2231A;")
        self.status.setWordWrap(True)
        self.status.hide()
        lay.addWidget(self.status)
        outer.addWidget(card)

        outer.addWidget(link_button("Usar la sesión que ya tengo abierta en Roblox", self.use_current),
                        0, Qt.AlignHCenter)
        outer.addWidget(link_button("Ahora no, entrar sin cuenta", self.reject), 0, Qt.AlignHCenter)
        foot = muted_label("Tu sesión se guarda cifrada en este PC y solo se envía a roblox.com.")
        foot.setAlignment(Qt.AlignCenter)
        foot.setStyleSheet("font-size: 8.5pt;")
        outer.addWidget(foot)

    def login(self) -> None:
        try:
            result = login_with_roblox(self)
        except Exception as exc:
            self.status.setText(f"No se pudo abrir la página de Roblox: {exc}")
            self.status.show()
            return
        if not result:
            return
        cookie, info = result
        self._save(Account(alias=info.get("displayName") or info.get("name", "Mi cuenta"),
                           username=info.get("name", ""), user_id=int(info.get("id", 0)),
                           login_method=LOGIN_COOKIE, cookie=cookie))

    def use_current(self) -> None:
        name, ok = QInputDialog.getText(self, "Tu cuenta de Roblox",
                                        "Tu nombre de usuario de Roblox (para mostrar tu nombre y tu foto):")
        if ok:
            name = name.strip()
            self._save(Account(alias=name or "Mi cuenta", username=name, login_method=LOGIN_CURRENT))

    def _save(self, account: Account) -> None:
        self.ctx.vault.upsert(account)
        self.ctx.cfg.set("main_account_id", account.id)
        self.accept()


class UnlockDialog(QDialog):
    """Solo si activaste la contraseña maestra en Ajustes: pide la contraseña al abrir."""

    def __init__(self, vault: Vault, parent=None):
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("RbxFarm Manager")
        self.setFixedWidth(420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)
        outer.addLayout(_brand_header("Hola de nuevo", "Escribe tu contraseña maestra para abrir tus cuentas."))
        card, lay = make_card(20, 10)
        self.pw = _password_field("Contraseña maestra")
        lay.addWidget(self.pw)
        self.error = QLabel()
        self.error.setStyleSheet("color: #E2231A;")
        self.error.hide()
        lay.addWidget(self.error)
        btn = styled_button("Entrar", "secondary", self._accept, big=True)
        btn.setDefault(True)
        lay.addWidget(btn)
        outer.addWidget(card)
        self.pw.returnPressed.connect(self._accept)

    def _accept(self) -> None:
        try:
            self.vault.unlock(self.pw.text())
        except crypto.WrongPassword as exc:
            self.pw.selectAll()
            self.error.setText(str(exc))
            self.error.show()
            return
        except Exception as exc:
            self.error.setText(f"Error: {exc}")
            self.error.show()
            return
        self.accept()


class PasswordDialog(QDialog):
    def __init__(self, title: str, text: str, confirm: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.addWidget(muted_label(text))
        self.pw = _password_field("Contraseña")
        lay.addWidget(self.pw)
        self.pw2 = _password_field("Repite la contraseña") if confirm else None
        if self.pw2:
            lay.addWidget(self.pw2)
        self.error = QLabel()
        self.error.setStyleSheet("color: #E2231A;")
        lay.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(styled_button("Cancelar", "", self.reject))
        ok = styled_button("Aceptar", "secondary", self._ok)
        ok.setDefault(True)
        row.addWidget(ok)
        lay.addLayout(row)

    def _ok(self):
        if len(self.pw.text()) < 6:
            self.error.setText("Usa al menos 6 caracteres.")
            return
        if self.pw2 and self.pw.text() != self.pw2.text():
            self.error.setText("Las contraseñas no coinciden.")
            return
        self.accept()

    @classmethod
    def ask(cls, parent, title: str, text: str, confirm: bool = False) -> str | None:
        dlg = cls(title, text, confirm, parent)
        return dlg.pw.text() if dlg.exec() == QDialog.Accepted else None


class AccountDialog(QDialog):
    def __init__(self, account: Account | None, macro_profiles: list[str], clicker_presets: list[str], parent=None):
        super().__init__(parent)
        self.account = Account.from_dict(account.to_dict()) if account else Account(alias="")
        self._id_username = self.account.username  # usuario al que corresponde account.user_id
        self.setWindowTitle("Editar cuenta" if account else "Agregar cuenta")
        self.setMinimumWidth(500)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        card, lay = make_card(18, 10)
        outer.addWidget(card)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        lay.addLayout(form)

        a = self.account
        self.alias = QLineEdit(a.alias)
        self.alias.setPlaceholderText("Nombre para reconocerla, p. ej. «Farm 1»")
        self.username = QLineEdit(a.username)
        self.username.setPlaceholderText("Usuario de Roblox (opcional)")
        self.method = QComboBox()
        for key, label in LOGIN_METHODS.items():
            self.method.addItem(label, key)
        self.method.setCurrentIndex(max(0, self.method.findData(a.login_method)))

        cookie_row = QWidget()
        cr = QHBoxLayout(cookie_row)
        cr.setContentsMargins(0, 0, 0, 0)
        self.cookie = _password_field("_|WARNING:-DO-NOT-SHARE-THIS…")
        self.cookie.setText(a.cookie)
        show = QCheckBox("Ver")
        show.toggled.connect(lambda on: self.cookie.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        self.verify_btn = styled_button("Verificar", "", self._verify)
        cr.addWidget(self.cookie, 1)
        cr.addWidget(show)
        cr.addWidget(self.verify_btn)
        self.cookie_hint = muted_label("La cookie solo se envía a roblox.com para obtener el ticket de entrada. "
                                       "Se guarda cifrada en tu equipo.")

        self.tags = QLineEdit(", ".join(a.tags))
        self.tags.setPlaceholderText("farm, principal, alt…")
        self.notes = QPlainTextEdit(a.notes)
        self.notes.setFixedHeight(70)

        self.macro = QComboBox()
        self.macro.addItem("(ninguno)", "")
        for name in macro_profiles:
            self.macro.addItem(name, name)
        self.macro.setCurrentIndex(max(0, self.macro.findData(a.macro_profile)))
        self.auto_macro = QCheckBox("Al entrar en juego, iniciar su macro (o, si no tiene, su autoclicker)")
        self.auto_macro.setChecked(a.auto_macro)
        self.clicker = QComboBox()
        self.clicker.addItem("(ninguno)", "")
        for name in clicker_presets:
            self.clicker.addItem(name, name)
        self.clicker.setCurrentIndex(max(0, self.clicker.findData(a.clicker_preset)))
        self.anti_afk = QCheckBox("Anti-AFK activado en sus instancias")
        self.anti_afk.setChecked(a.anti_afk)

        login_row = QWidget()
        lr = QHBoxLayout(login_row)
        lr.setContentsMargins(0, 0, 0, 0)
        self.login_btn = styled_button("Iniciar sesión con Roblox", "secondary", self._login, icon=G.PERSON)
        lr.addWidget(self.login_btn)
        lr.addWidget(muted_label("Lo más fácil: rellena la cuenta sola."), 1)

        form.addRow("Inicio de sesión", self.method)
        form.addRow("Roblox", login_row)
        form.addRow("Alias *", self.alias)
        form.addRow("Usuario", self.username)
        form.addRow("Cookie (manual)", cookie_row)
        form.addRow("", self.cookie_hint)
        form.addRow("Etiquetas", self.tags)
        form.addRow("Notas", self.notes)
        form.addRow("Macro", self.macro)
        form.addRow("", self.auto_macro)
        form.addRow("Autoclicker", self.clicker)
        form.addRow("", self.anti_afk)
        self._cookie_widgets = [cookie_row, self.cookie_hint, form.labelForField(cookie_row),
                                login_row, form.labelForField(login_row)]
        self.method.currentIndexChanged.connect(self._method_changed)
        self._method_changed()

        self.status = QLabel()
        lay.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(styled_button("Cancelar", "", self.reject))
        save = styled_button("Guardar", "secondary", self._save)
        save.setDefault(True)
        row.addWidget(save)
        outer.addLayout(row)

    def _method_changed(self) -> None:
        is_cookie = self.method.currentData() == LOGIN_COOKIE
        for w in self._cookie_widgets:
            if w:
                w.setVisible(is_cookie)

    def _verify(self) -> None:
        cookie = self.cookie.text().strip()
        if not cookie:
            self.status.setText("Pega primero la cookie.")
            return
        self.verify_btn.setEnabled(False)
        self.status.setText("Comprobando con Roblox…")

        def done(info):
            self.verify_btn.setEnabled(True)
            self._apply_info(info)

        def fail(exc):
            self.verify_btn.setEnabled(True)
            self.status.setStyleSheet("color: #E2231A;")
            self.status.setText(f"✖ {exc}")

        run_async(roblox_api.get_authenticated_user, cookie, on_done=done, on_error=fail)

    def _login(self) -> None:
        try:
            result = login_with_roblox(self)
        except Exception as exc:
            self.status.setStyleSheet("color: #E2231A;")
            self.status.setText(f"✖ No se pudo abrir la página de Roblox: {exc}")
            return
        if result:
            cookie, info = result
            self.cookie.setText(cookie)
            self._apply_info(info)

    def _apply_info(self, info: dict) -> None:
        self.username.setText(info.get("name", ""))
        self.account.user_id = int(info.get("id", 0))
        self._id_username = info.get("name", "")
        if not self.alias.text().strip():
            self.alias.setText(info.get("displayName") or info.get("name", ""))
        self.status.setStyleSheet("color: #02B757;")
        self.status.setText(f"✔ Sesión válida: {info.get('name')} (ID {info.get('id')})")

    def _save(self) -> None:
        alias = self.alias.text().strip()
        if not alias:
            QMessageBox.warning(self, "Falta el alias", "Ponle un alias a la cuenta.")
            return
        a = self.account
        a.alias = alias
        a.username = self.username.text().strip()
        if a.username.lower() != self._id_username.lower():
            a.user_id = 0  # otro usuario: su ID (y su foto) se buscarán de nuevo
        a.login_method = self.method.currentData()
        a.cookie = self.cookie.text().strip() if a.login_method == LOGIN_COOKIE else ""
        a.tags = [t.strip() for t in self.tags.text().split(",") if t.strip()]
        a.notes = self.notes.toPlainText().strip()
        a.macro_profile = self.macro.currentData()
        a.auto_macro = self.auto_macro.isChecked()
        a.clicker_preset = self.clicker.currentData()
        a.anti_afk = self.anti_afk.isChecked()
        self.accept()
