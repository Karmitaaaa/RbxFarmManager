"""Pestaña Registro / Ajustes."""
import html
import os
import time

from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QMessageBox, QPlainTextEdit, QVBoxLayout

from storage import crypto
from ui import bind
from ui.context import AppContext
from ui.dialogs import PasswordDialog
from ui.icons import G
from ui.widgets import Page, SectionHeader, make_card, muted_label, styled_button
from utils.paths import app_dir, logs_dir
from utils.version import APP_VERSION
from utils.i18n import N_, available_languages, current_language, t

LEVEL_COLORS = {"ERROR": "#E2231A", "CRITICAL": "#E2231A", "WARNING": "#F68802"}
FILTERS = {"all": N_("Todo"), "warn": N_("Avisos y errores"), "error": N_("Solo errores")}


class LogTab(Page):
    def __init__(self, ctx: AppContext):
        super().__init__(max_width=1200)
        self.ctx = ctx
        self.lines: list[tuple[str, str]] = []
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # ---------------- registro
        left = QVBoxLayout()
        header = SectionHeader(t("Registro de eventos"))
        header.add_link(t("Abrir carpeta de logs"), lambda: os.startfile(logs_dir()))
        header.add_link(t("Limpiar vista"), self.clear)
        left.addWidget(header)
        card, lay = make_card(12, 8)
        top = QHBoxLayout()
        top.addWidget(muted_label(t("Mostrar:")))
        self.filter = QComboBox()
        for key, label in FILTERS.items():
            self.filter.addItem(t(label), key)
        self.filter.currentIndexChanged.connect(self.rerender)
        top.addWidget(self.filter)
        top.addStretch(1)
        lay.addLayout(top)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(5000)
        self.view.setMinimumHeight(480)
        self.view.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace; font-size: 9.5pt;")
        lay.addWidget(self.view)
        left.addWidget(card)

        # ---------------- ajustes
        right = QVBoxLayout()
        right.addWidget(SectionHeader(t("Ajustes")))
        card, lay = make_card(16, 8)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        cfg = ctx.cfg
        form.addRow(t("Tema"), bind.combo(cfg, "theme", {"classic": t("Clásico (claro)"), "dark": t("Clásico oscuro")},
                                       ctx.theme_changed.emit))
        self.language = QComboBox()
        for code, name in available_languages().items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(current_language())))
        self.language.currentIndexChanged.connect(self._language_changed)
        form.addRow(t("Idioma"), self.language)
        form.addRow("", bind.check(cfg, "minimize_to_tray", t("Al cerrar, seguir en la bandeja del sistema")))
        form.addRow("", bind.check(cfg, "start_minimized", t("Iniciar minimizado en la bandeja")))
        form.addRow("", bind.check(cfg, "download_avatars", t("Mostrar fotos de avatar (se descargan de roblox.com)"),
                                   lambda _on: ctx.accounts_changed.emit()))
        lay.addLayout(form)
        lay.addWidget(muted_label(t("La configuración se guarda automáticamente.")))
        right.addWidget(card)

        right.addWidget(SectionHeader(t("Seguridad de las cuentas")))
        card, lay = make_card(16, 8)
        self.mode_label = muted_label("")
        lay.addWidget(self.mode_label)
        self.password_btn = styled_button(t("Pedir una contraseña al abrir"), "secondary", self.set_password)
        lay.addWidget(self.password_btn)
        self.dpapi_btn = styled_button(t("Quitar la contraseña (abrir solo con mi usuario de Windows)"), "",
                                       self.use_dpapi)
        lay.addWidget(self.dpapi_btn)
        lay.addWidget(muted_label(t("Las cuentas solo se guardan cifradas en este equipo y nunca se envían a otros "
                                  "servidores. La sesión únicamente viaja a roblox.com al lanzar.")))
        lay.addWidget(styled_button(t("Abrir carpeta de datos"), "", lambda: os.startfile(app_dir())))
        right.addWidget(card)

        right.addWidget(SectionHeader(t("Actualizaciones")))
        card, lay = make_card(16, 8)
        lay.addWidget(muted_label(t("Versión instalada: {0}", APP_VERSION)))
        lay.addWidget(bind.check(cfg, "check_updates", t("Avisarme cuando haya una versión nueva")))
        row = QHBoxLayout()
        self.check_btn = styled_button(t("Buscar actualizaciones ahora"), "secondary", self.check_updates, icon=G.SYNC)
        row.addWidget(self.check_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.update_status = muted_label("")
        lay.addWidget(self.update_status)
        right.addWidget(card)
        right.addStretch(1)
        ctx.updates.finished.connect(self._update_checked)

        columns.addLayout(left, 3)
        columns.addLayout(right, 2)
        self.body.addLayout(columns)
        self._update_mode()

    def _language_changed(self) -> None:
        self.ctx.cfg.set("language", self.language.currentData())
        self.ctx.cfg.save_if_dirty()
        text = t("El idioma cambiará al reiniciar la app. ¿Reiniciar ahora?")
        if any(i.pid for i in self.ctx.manager.snapshot()):
            text += "\n\n" + t("Las ventanas de Roblox seguirán abiertas, pero la app dejará de vigilarlas.")
        if QMessageBox.question(self, t("Idioma"), text) == QMessageBox.Yes:
            self.ctx.navigate.emit("restart")

    def check_updates(self) -> None:
        self.check_btn.setEnabled(False)
        self.update_status.setText(t("Buscando en GitHub…"))
        self._manual_check = True
        self.ctx.updates.check(manual=True)

    def _update_checked(self, info, error: str) -> None:
        manual = getattr(self, "_manual_check", False)
        self._manual_check = False
        self.check_btn.setEnabled(True)
        stamp = time.strftime("%H:%M")
        if error:
            self.update_status.setText(t("No se pudo comprobar ({0}): {1}", stamp, error))
        elif info:
            self.update_status.setText(t("Versión {0} disponible ({1}).", info.version, stamp))
            if manual:
                self.ctx.navigate.emit("update")
        else:
            self.update_status.setText(t("Tienes la última versión ({0}).", stamp))

    def append(self, level: str, text: str) -> None:
        self.lines.append((level, text))
        if len(self.lines) > 5000:
            self.lines = self.lines[-4000:]
        if self._passes(level):
            self._write(level, text)

    def _passes(self, level: str) -> bool:
        mode = self.filter.currentData()
        if mode == "error":
            return level in ("ERROR", "CRITICAL")
        if mode == "warn":
            return level in ("WARNING", "ERROR", "CRITICAL")
        return True

    def _write(self, level: str, text: str) -> None:
        color = LEVEL_COLORS.get(level)
        safe = html.escape(text)
        self.view.appendHtml(f'<span style="color:{color}">{safe}</span>' if color else safe)

    def rerender(self) -> None:
        self.view.clear()
        for level, text in self.lines:
            if self._passes(level):
                self._write(level, text)

    def clear(self) -> None:
        self.lines = []
        self.view.clear()

    def _update_mode(self) -> None:
        protected = self.ctx.vault.mode == "password"
        self.mode_label.setText(
            t("Ahora: se pide tu contraseña maestra al abrir (Fernet + scrypt).") if protected else
            t("Ahora: las cuentas se cifran con tu usuario de Windows y la app se abre sin pedir nada. "
            "Si compartes el PC, puedes añadir una contraseña."))
        self.password_btn.setText(t("Cambiar la contraseña") if protected else t("Pedir una contraseña al abrir"))
        self.dpapi_btn.setVisible(protected)

    def set_password(self) -> None:
        if self.ctx.vault.mode == "password":
            current = PasswordDialog.ask(self, t("Contraseña actual"), t("Escribe la contraseña maestra actual."))
            if current is None:
                return
            try:
                crypto.unseal(self.ctx.vault.path.read_bytes(), current)
            except crypto.WrongPassword:
                QMessageBox.warning(self, t("Contraseña"), t("La contraseña actual no es correcta."))
                return
        new = PasswordDialog.ask(self, t("Nueva contraseña maestra"), t("Elige la nueva contraseña maestra."), confirm=True)
        if new is None:
            return
        self.ctx.vault.change_protection("password", new)
        self._update_mode()
        QMessageBox.information(self, t("Contraseña"), t("Contraseña maestra actualizada."))

    def use_dpapi(self) -> None:
        if QMessageBox.question(self, "DPAPI", t("El baúl se abrirá automáticamente con tu sesión de Windows y ya no "
                                "pedirá contraseña. Solo podrá abrirse con este usuario en este equipo. ¿Continuar?")
                                ) != QMessageBox.Yes:
            return
        self.ctx.vault.change_protection("dpapi")
        self._update_mode()
