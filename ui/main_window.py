"""Ventana principal: barra azul superior, menú lateral con secciones, páginas, bandeja y hotkeys."""
import logging

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from core.models import ACTIVE_STATES, ST_INGAME
from ui import theme, widgets
from ui.context import AppContext
from ui.icons import G, GlyphLabel, glyph_icon, icon_font
from ui.tabs.accounts_tab import AccountsTab
from ui.tabs.afk_tab import AfkTab
from ui.tabs.clicker_tab import ClickerTab
from ui.tabs.games_tab import GamesTab
from ui.tabs.instances_tab import InstancesTab
from ui.tabs.log_tab import LogTab
from ui.tabs.macros_tab import MacrosTab
from utils.logger import ui_handler

log = logging.getLogger("ui")

# clave, nombre corto, icono, título de la cabecera, explicación (None = sin cabecera)
PAGES = [
    ("accounts", "Inicio", G.HOME, None, None),
    ("games", "Juegos", G.GAME, "Juegos",
     "Un perfil por juego: a qué servidor entrar, con qué cuentas y qué macro usar. Después solo pulsa «Jugar»."),
    ("instances", "Instancias", G.MONITOR, "Instancias abiertas",
     "Todas las ventanas de Roblox que gestiona la app: estado, consumo y botones para verlas, reiniciarlas o cerrarlas."),
    ("afk", "Anti-AFK", G.TIMER, "Anti-AFK y reconexión",
     "Evita que Roblox te expulse por inactividad y vuelve a entrar solo si se cae el juego o internet."),
    ("clicker", "Autoclicker", G.MOUSE, "Autoclicker",
     "Clics automáticos con intervalo, posición y hotkey global. Guarda presets para usarlos en tus juegos."),
    ("macros", "Macros", G.RECORD, "Macros",
     "Graba lo que haces con el teclado y el ratón y repítelo. Cada macro puede guardarse dentro de su juego."),
    ("log", "Registro", G.DOC, "Registro y ajustes",
     "Todo lo que ocurre, con fecha y hora, y las opciones de la aplicación."),
]
SIDEBAR_SECTIONS = [("", ["accounts", "games", "instances"]),
                    ("AUTOMATIZACIÓN", ["afk", "clicker", "macros"]),
                    ("SISTEMA", ["log"])]
TOP_NAV = ["accounts", "games", "instances", "macros"]


class LogBridge(QObject):
    record = Signal(str, str)


class SideItem(QPushButton):
    """Elemento del menú lateral: icono + texto + contador opcional."""

    def __init__(self, glyph: str, text: str):
        super().__init__()
        self.setObjectName("SideButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 12, 0)
        lay.setSpacing(10)
        self.icon_label = GlyphLabel(glyph, 16)
        self.text_label = QLabel(text)
        self.badge = QLabel()
        self.badge.setObjectName("SideBadge")
        self.badge.setFixedHeight(18)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.hide()
        for w in (self.icon_label, self.text_label, self.badge):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.icon_label)
        lay.addWidget(self.text_label, 1)
        lay.addWidget(self.badge)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        color = theme.ACCENTS["blue"] if active else ""
        for w in (self.icon_label, self.text_label):
            w.setStyleSheet(f"color: {color}; background: transparent;" if color else "background: transparent;")
        font = self.text_label.font()
        font.setBold(active)
        self.text_label.setFont(font)

    def set_count(self, n: int) -> None:
        self.badge.setText(str(n))
        self.badge.setVisible(n > 0)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self._quitting = False
        self._tray_hint_shown = False
        self.setWindowTitle("RbxFarm Manager")
        self.setWindowIcon(widgets.app_icon())
        self.resize(1320, 840)
        self.setMinimumSize(1000, 640)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = self._build_sidebar()
        body.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.setCentralWidget(central)

        self.pages = {
            "accounts": AccountsTab(ctx),
            "games": GamesTab(ctx),
            "instances": InstancesTab(ctx),
            "afk": AfkTab(ctx),
            "clicker": ClickerTab(ctx),
            "macros": MacrosTab(ctx),
            "log": LogTab(ctx),
        }
        for key, _label, glyph, title, subtitle in PAGES:
            page = self.pages[key]
            if title:
                header = widgets.PageHeader(glyph, title, subtitle)
                page.body.insertWidget(0, header)
                if key == "games":
                    header.add_action(widgets.styled_button("Nuevo perfil de juego", "secondary",
                                                            lambda: page.actions.new(), icon=G.ADD))
                elif key == "instances":
                    header.add_action(widgets.styled_button("Minimizar todas", "", ctx.manager.minimize_all,
                                                            icon=G.DOWNLOAD))
            self.stack.addWidget(page)

        self.dock = widgets.NotificationsDock(central)
        self._build_tray()

        # Registro en la UI (los hilos emiten; Qt lo entrega en el hilo principal)
        self.log_bridge = LogBridge()
        self.log_bridge.record.connect(self.pages["log"].append)
        ui_handler.sink = self.log_bridge.record.emit

        ctx.navigate.connect(self.navigate)
        ctx.notify.connect(self.on_notify)
        ctx.theme_changed.connect(self.apply_theme)
        ctx.hotkeys.triggered.connect(self.on_hotkey)
        ctx.manager.joined.connect(self.on_joined)
        ctx.manager.changed.connect(self.update_counters)
        ctx.games_changed.connect(self.update_play_button)
        ctx.clicker.state_changed.connect(self._tray_state)

        self.autosave = QTimer(self)
        self.autosave.timeout.connect(ctx.cfg.save_if_dirty)
        self.autosave.start(2000)

        self.navigate("accounts")
        self.update_counters()
        self.update_play_button()
        log.info("RbxFarm Manager listo")

    # ------------------------------------------------------------------ construcción
    def _icon_button(self, glyph: str, tip: str, slot) -> QPushButton:
        btn = QPushButton(glyph)
        btn.setObjectName("IconButton")
        btn.setFont(icon_font(17))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setFixedWidth(42)
        btn.clicked.connect(slot)
        return btn

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(46)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 0, 10, 0)
        lay.setSpacing(0)

        lay.addWidget(self._icon_button(G.MENU, "Mostrar u ocultar el menú", self.toggle_sidebar))
        brand = QLabel("RbxFarm")
        brand.setObjectName("Brand")
        lay.addWidget(brand)

        self.nav_buttons = {}
        labels = {key: label for key, label, *_ in PAGES}
        for key in TOP_NAV:
            btn = QPushButton(labels[key])
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            lay.addWidget(btn)
            self.nav_buttons[key] = btn

        lay.addSpacing(14)
        self.search = QLineEdit()
        self.search.setObjectName("TopSearch")
        self.search.setPlaceholderText("Buscar cuentas…")
        self.search.addAction(glyph_icon(G.SEARCH, "#757575", 14), QLineEdit.TrailingPosition)
        self.search.setMaximumWidth(300)
        self.search.setMinimumWidth(170)
        self.search.textChanged.connect(self._search)
        lay.addWidget(self.search, 1)
        lay.addStretch(1)

        self.top_stat = QLabel()
        self.top_stat.setObjectName("TopStat")
        lay.addWidget(self.top_stat)
        lay.addWidget(self._icon_button(G.BELL, "Notificaciones", lambda: self.dock.toggle()))
        self.badge = QLabel()
        self.badge.setObjectName("Badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.hide()
        lay.addWidget(self.badge)
        lay.addWidget(self._icon_button(G.SETTINGS, "Registro y ajustes", lambda: self.navigate("log")))
        return bar

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(216)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 10, 0, 14)
        lay.setSpacing(0)
        meta = {key: (label, glyph, subtitle) for key, label, glyph, _t, subtitle in PAGES}
        self.side_items: dict[str, SideItem] = {}
        for section, keys in SIDEBAR_SECTIONS:
            if section:
                title = QLabel(section)
                title.setObjectName("SideSection")
                lay.addWidget(title)
            for key in keys:
                label, glyph, subtitle = meta[key]
                item = SideItem(glyph, label)
                item.setToolTip(subtitle or "Saludo, primeros pasos, tus juegos y tus cuentas")
                item.clicked.connect(lambda _=False, k=key: self.navigate(k))
                lay.addWidget(item)
                self.side_items[key] = item
        lay.addStretch(1)

        self.side_play = widgets.styled_button("Jugar", "primary", self._play_last, icon=G.PLAY)
        self.side_play.setMinimumHeight(38)
        wrap = QVBoxLayout()
        wrap.setContentsMargins(14, 0, 14, 0)
        wrap.setSpacing(6)
        self.side_play_hint = QLabel()
        self.side_play_hint.setObjectName("Muted")
        self.side_play_hint.setWordWrap(True)
        self.side_play_hint.setAlignment(Qt.AlignCenter)
        self.side_play_hint.setStyleSheet("font-size: 8.5pt;")
        wrap.addWidget(self.side_play_hint)
        wrap.addWidget(self.side_play)
        lay.addLayout(wrap)
        side.setVisible(bool(self.ctx.cfg.get("sidebar_visible", True)))
        return side

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(widgets.app_icon(), self)
        self.tray.setToolTip("RbxFarm Manager")
        menu = QMenu()
        menu.addAction("Mostrar", self.show_window)
        menu.addAction("Jugar el último juego", self._play_last)
        self.tray_clicker = QAction("Iniciar autoclicker", self)
        self.tray_clicker.triggered.connect(lambda: self.pages["clicker"].toggle())
        menu.addAction(self.tray_clicker)
        menu.addAction("Detener macro", self.ctx.player.stop)
        menu.addAction("Minimizar instancias", self.ctx.manager.minimize_all)
        menu.addSeparator()
        menu.addAction("Salir", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window()
                                    if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger) else None)
        self.tray.show()

    # ------------------------------------------------------------------ navegación
    def toggle_sidebar(self) -> None:
        visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(visible)
        self.ctx.cfg.set("sidebar_visible", visible)

    def navigate(self, target: str) -> None:
        if target.startswith("run:"):
            self._run_menu(target[4:])
            return
        if target.startswith("macros:"):
            self.pages["macros"].set_game_filter(target[7:])
            target = "macros"
        if target not in self.pages:
            return
        self.stack.setCurrentWidget(self.pages[target])
        for key, btn in self.nav_buttons.items():
            btn.setProperty("active", key == target)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        for key, item in self.side_items.items():
            item.set_active(key == target)

    def _search(self, text: str) -> None:
        self.pages["accounts"].set_filter(text)
        if text:
            self.navigate("accounts")

    def _last_game(self):
        games = self.ctx.games.all()
        return games[0] if games else None

    def _play_last(self) -> None:
        game = self._last_game()
        if game is None:
            self.navigate("games")
            return
        self.pages["games"].actions.play(game.id)

    def update_play_button(self) -> None:
        game = self._last_game()
        if game:
            self.side_play.setText("Jugar")
            self.side_play_hint.setText(f"Último juego: {game.name}")
            self.side_play.setToolTip(f"Abrir «{game.name}» con sus cuentas")
        else:
            self.side_play.setText("Crear un juego")
            self.side_play_hint.setText("Aún no tienes perfiles de juego")
            self.side_play.setToolTip("Ir a Juegos para crear tu primer perfil")

    def _run_menu(self, inst_id: str) -> None:
        inst = self.ctx.manager.get(inst_id)
        if not inst:
            return
        macro_name, preset = self.ctx.macro_for(inst)
        menu = QMenu(self)
        macro = menu.addAction(glyph_icon(G.PLAY, theme.ACCENTS["green"]),
                               f"Reproducir macro «{macro_name}»" if macro_name else "Reproducir macro (no tiene)")
        macro.setEnabled(bool(macro_name))
        macro.triggered.connect(lambda: self.pages["macros"].play(macro_name, inst))
        menu.addAction(glyph_icon(G.LIST), "Elegir otra macro…",
                       lambda: (self.pages["macros"].select_target(inst_id), self.navigate("macros")))
        menu.addSeparator()
        clicker = menu.addAction(glyph_icon(G.MOUSE), f"Iniciar autoclicker «{preset}»" if preset
                                 else "Iniciar autoclicker (ajustes actuales)")
        clicker.triggered.connect(lambda: self.pages["clicker"].start_for_instance(inst_id, preset))
        menu.addAction(glyph_icon(G.STOP, theme.ACCENTS["red"]), "Detener macro y autoclicker",
                       lambda: (self.ctx.player.stop(), self.ctx.clicker.stop()))
        menu.exec(QCursor.pos())

    # ------------------------------------------------------------------ eventos
    def on_hotkey(self, name: str, pressed: bool) -> None:
        macros = self.pages["macros"]
        if name == "clicker":
            self.ctx.clicker.on_hotkey(pressed, self.pages["clicker"].settings())
        elif not pressed:
            return
        elif name == "macro_record":
            macros.toggle_record()
        elif name == "macro_stop":
            macros.stop_all()
        elif name == "macro_play":
            macros.play_selected()

    def on_joined(self, inst_id: str) -> None:
        inst = self.ctx.manager.get(inst_id)
        plan = self.ctx.auto_run_for(inst) if inst else None
        if not plan:
            return
        macro_name, preset = plan
        if macro_name:
            QTimer.singleShot(3000, lambda: self.pages["macros"].play(macro_name, inst))
        elif preset:
            QTimer.singleShot(3000, lambda: self.pages["clicker"].start_for_instance(inst_id, preset))

    def on_notify(self, level: str, text: str) -> None:
        self.dock.add(level, text)
        self.update_counters()
        if level == "error" or (level == "warning" and not self.isVisible()):
            icon = QSystemTrayIcon.Critical if level == "error" else QSystemTrayIcon.Warning
            self.tray.showMessage("RbxFarm Manager", text, icon, 5000)

    def update_counters(self) -> None:
        instances = self.ctx.manager.snapshot()
        in_game = sum(1 for i in instances if i.status == ST_INGAME)
        active = sum(1 for i in instances if i.status in ACTIVE_STATES)
        self.top_stat.setText(f"● {in_game}/{len(instances)} en juego")
        self.tray.setToolTip(f"RbxFarm Manager — {in_game}/{len(instances)} en juego")
        self.side_items["instances"].set_count(active)
        unread = self.dock.unread
        self.badge.setText(str(unread))
        self.badge.setVisible(unread > 0)

    def _tray_state(self, running: bool) -> None:
        self.tray_clicker.setText("Detener autoclicker" if running else "Iniciar autoclicker")

    def apply_theme(self, name: str) -> None:
        widgets.current_theme["name"] = name if name in theme.PALETTES else "classic"
        QApplication.instance().setStyleSheet(theme.stylesheet(widgets.current_theme["name"]))
        for page in self.pages.values():
            page.update()
        self.pages["accounts"].refresh()
        self.pages["accounts"].refresh_games()
        self.pages["games"].refresh()

    # ------------------------------------------------------------------ ventana / salida
    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if not self._quitting and self.ctx.cfg.get("minimize_to_tray"):
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self.tray.showMessage("RbxFarm Manager", "Sigo funcionando en la bandeja. Clic derecho para salir.",
                                      QSystemTrayIcon.Information, 3000)
                self._tray_hint_shown = True
            return
        if not self._confirm_quit():
            event.ignore()
            return
        event.accept()

    def _confirm_quit(self) -> bool:
        active = [i for i in self.ctx.manager.snapshot() if i.pid]
        if active:
            answer = QMessageBox.question(
                self, "Salir", f"Hay {len(active)} instancia(s) de Roblox abiertas.\n"
                "¿Cerrarlas también? (No = dejarlas abiertas sin vigilancia)",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if answer == QMessageBox.Cancel:
                self._quitting = False
                return False
            if answer == QMessageBox.Yes:
                self.ctx.manager.close_all()
        self.ctx.shutdown()
        self.tray.hide()
        ui_handler.sink = None
        QApplication.instance().quit()
        return True

    def quit_app(self) -> None:
        self._quitting = True
        self.show_window()
        self.close()
