"""Panel «Calidad y rendimiento» de la pestaña Instancias."""
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core import performance
from core.performance import FPS_OPTIONS, PRESET_NAMES, PRESETS, QUALITY_LEVELS
from ui import bind
from ui.context import AppContext
from ui.widgets import make_card, muted_label, styled_button
from utils.i18n import N_, t

ROBLOX_CHECKS = (("low_textures", N_("Texturas en calidad baja")), ("no_grass", N_("Quitar la hierba")),
                 ("no_antialiasing", N_("Quitar el suavizado de bordes")), ("low_detail", N_("Menos detalle en los modelos")),
                 ("simple_lighting", N_("Iluminación simple")), ("gray_sky", N_("Cielo gris sin texturas")),
                 ("mute", N_("Silenciar Roblox")))


class PerformancePanel(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        cfg = ctx.cfg
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card, lay = make_card(16, 10)
        outer.addWidget(card)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for column in (1, 3, 5):
            grid.setColumnStretch(column, 1)
        self.preset = bind.combo(cfg, "performance.preset", PRESET_NAMES, self._preset_chosen)
        fps = {0: t("Sin cambios"), **{value: f"{value} FPS" for value in FPS_OPTIONS}}
        self.fps = bind.combo(cfg, "performance.fps", fps, self._changed)
        quality = {0: t("Sin cambios"), 1: t("1 (mínima)"), QUALITY_LEVELS: t("10 (máxima)")}
        quality.update({level: str(level) for level in range(2, QUALITY_LEVELS)})
        self.quality = bind.combo(cfg, "performance.quality", dict(sorted(quality.items())), self._changed)
        for column, (label, box) in enumerate(((t("Perfil"), self.preset), (t("Límite de FPS"), self.fps),
                                               (t("Calidad gráfica"), self.quality))):
            grid.addWidget(QLabel(label), 0, column * 2)
            grid.addWidget(box, 0, column * 2 + 1)
        lay.addLayout(grid)

        lay.addWidget(self._title(t("Gráficos de Roblox")))
        self.controls = [self.fps, self.quality]
        checks = QGridLayout()
        checks.setVerticalSpacing(6)
        checks.setColumnStretch(0, 1)
        checks.setColumnStretch(1, 1)
        for index, (key, text) in enumerate(ROBLOX_CHECKS):
            box = bind.check(cfg, f"performance.{key}", t(text), self._changed)
            self.controls.append(box)
            checks.addWidget(box, index // 2, index % 2)
        lay.addLayout(checks)
        lay.addWidget(muted_label(t("Se aplican a las ventanas que abras desde ahora: reinicia las que ya estén "
                                    "abiertas para notarlo.")))

        lay.addWidget(self._title(t("Procesador")))
        cpu = QGridLayout()
        cpu.setVerticalSpacing(6)
        cpu.setColumnStretch(0, 1)
        cpu.setColumnStretch(1, 1)
        low = bind.check(cfg, "performance.low_priority", t("Prioridad de CPU baja"), self._changed)
        efficiency = bind.check(cfg, "performance.efficiency", t("Modo de eficiencia de Windows"), self._changed)
        cpu.addWidget(low, 0, 0)
        cpu.addWidget(efficiency, 0, 1)
        cores = QHBoxLayout()
        self.cores = bind.spin(cfg, "performance.cores", 0, 64)
        self.cores.setSpecialValueText(t("Todos"))
        self.cores.valueChanged.connect(self._changed)
        cores.addWidget(QLabel(t("Núcleos por ventana")))
        cores.addWidget(self.cores)
        cores.addStretch(1)
        cpu.addLayout(cores, 1, 0)
        self.controls += [low, efficiency, self.cores]
        lay.addLayout(cpu)

        buttons = QHBoxLayout()
        buttons.addWidget(styled_button(t("Aplicar ahora"), "primary", ctx.manager.apply_performance))
        buttons.addStretch(1)
        lay.addLayout(buttons)
        lay.addWidget(muted_label(t("El perfil Normal devuelve tus ajustes de Roblox. Los gráficos cambian los "
                                    "mismos ajustes que usas al jugar sin esta app.")))

    @staticmethod
    def _title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("CardTitle")
        return label

    def _preset_chosen(self, name: str) -> None:
        if name not in PRESETS:
            return
        for key, value in PRESETS[name].items():
            self.ctx.cfg.set(f"performance.{key}", value)
        for control in self.controls:
            control.blockSignals(True)
            control.reload()
            control.blockSignals(False)

    def _changed(self, *_) -> None:
        name = performance.current_preset(self.ctx.cfg.section("performance"))
        self.ctx.cfg.set("performance.preset", name)
        self.preset.blockSignals(True)
        self.preset.reload()
        self.preset.blockSignals(False)
