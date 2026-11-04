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

LEVEL_COLORS = {"ERROR": "#E2231A", "CRITICAL": "#E2231A", "WARNING": "#F68802"}
FILTERS = {"all": "Todo", "warn": "Avisos y errores", "error": "Solo errores"}


class LogTab(Page):
    def __init__(self, ctx: AppContext):
        super().__init__(max_width=1200)
        self.ctx = ctx
        self.lines: list[tuple[str, str]] = []
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # ---------------- registro
        left = QVBoxLayout()
        header = SectionHeader("Registro de eventos")
        header.add_link("Abrir carpeta de logs", lambda: os.startfile(logs_dir()))
        header.add_link("Limpiar vista", self.clear)
        left.addWidget(header)
        card, lay = make_card(12, 8)
        top = QHBoxLayout()
        top.addWidget(muted_label("Mostrar:"))
        self.filter = QComboBox()
        for key, label in FILTERS.items():
            self.filter.addItem(label, key)
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
        right.addWidget(SectionHeader("Ajustes"))
        card, lay = make_card(16, 8)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        cfg = ctx.cfg
        form.addRow("Tema", bind.combo(cfg, "theme", {"classic": "Clásico (claro)", "dark": "Clásico oscuro"},
                                       ctx.theme_changed.emit))
        form.addRow("", bind.check(cfg, "minimize_to_tray", "Al cerrar, seguir en la bandeja del sistema"))
        form.addRow("", bind.check(cfg, "start_minimized", "Iniciar minimizado en la bandeja"))
        form.addRow("", bind.check(cfg, "download_avatars", "Mostrar fotos de avatar (se descargan de roblox.com)",
                                   lambda _on: ctx.accounts_changed.emit()))
        lay.addLayout(form)
        lay.addWidget(muted_label("La configuración se guarda automáticamente."))
        right.addWidget(card)

        right.addWidget(SectionHeader("Seguridad de las cuentas"))
        card, lay = make_card(16, 8)
        self.mode_label = muted_label("")
        lay.addWidget(self.mode_label)
        self.password_btn = styled_button("Pedir una contraseña al abrir", "secondary", self.set_password)
        lay.addWidget(self.password_btn)
        self.dpapi_btn = styled_button("Quitar la contraseña (abrir solo con mi usuario de Windows)", "",
                                       self.use_dpapi)
        lay.addWidget(self.dpapi_btn)
        lay.addWidget(muted_label("Las cuentas solo se guardan cifradas en este equipo y nunca se envían a otros "
                                  "servidores. La sesión únicamente viaja a roblox.com al lanzar."))
        lay.addWidget(styled_button("Abrir carpeta de datos", "", lambda: os.startfile(app_dir())))
        right.addWidget(card)

        right.addWidget(SectionHeader("Actualizaciones"))
        card, lay = make_card(16, 8)
        lay.addWidget(muted_label(f"Versión instalada: {APP_VERSION}"))
        lay.addWidget(bind.check(cfg, "check_updates", "Avisarme cuando haya una versión nueva"))
        row = QHBoxLayout()
        self.check_btn = styled_button("Buscar actualizaciones ahora", "secondary", self.check_updates, icon=G.SYNC)
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

    def check_updates(self) -> None:
        self.check_btn.setEnabled(False)
        self.update_status.setText("Buscando en GitHub…")
        self._manual_check = True
        self.ctx.updates.check(manual=True)

    def _update_checked(self, info, error: str) -> None:
        manual = getattr(self, "_manual_check", False)
        self._manual_check = False
        self.check_btn.setEnabled(True)
        stamp = time.strftime("%H:%M")
        if error:
            self.update_status.setText(f"No se pudo comprobar ({stamp}): {error}")
        elif info:
            self.update_status.setText(f"Versión {info.version} disponible ({stamp}).")
            if manual:
                self.ctx.navigate.emit("update")
        else:
            self.update_status.setText(f"Tienes la última versión ({stamp}).")

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
            "Ahora: se pide tu contraseña maestra al abrir (Fernet + scrypt)." if protected else
            "Ahora: las cuentas se cifran con tu usuario de Windows y la app se abre sin pedir nada. "
            "Si compartes el PC, puedes añadir una contraseña.")
        self.password_btn.setText("Cambiar la contraseña" if protected else "Pedir una contraseña al abrir")
        self.dpapi_btn.setVisible(protected)

    def set_password(self) -> None:
        if self.ctx.vault.mode == "password":
            current = PasswordDialog.ask(self, "Contraseña actual", "Escribe la contraseña maestra actual.")
            if current is None:
                return
            try:
                crypto.unseal(self.ctx.vault.path.read_bytes(), current)
            except crypto.WrongPassword:
                QMessageBox.warning(self, "Contraseña", "La contraseña actual no es correcta.")
                return
        new = PasswordDialog.ask(self, "Nueva contraseña maestra", "Elige la nueva contraseña maestra.", confirm=True)
        if new is None:
            return
        self.ctx.vault.change_protection("password", new)
        self._update_mode()
        QMessageBox.information(self, "Contraseña", "Contraseña maestra actualizada.")

    def use_dpapi(self) -> None:
        if QMessageBox.question(self, "DPAPI", "El baúl se abrirá automáticamente con tu sesión de Windows y ya no "
                                "pedirá contraseña. Solo podrá abrirse con este usuario en este equipo. ¿Continuar?"
                                ) != QMessageBox.Yes:
            return
        self.ctx.vault.change_protection("dpapi")
        self._update_mode()
