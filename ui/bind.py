"""Controles enlazados a la configuración: cada cambio se guarda solo (autosave)."""
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox

from storage.config import Config
from utils.i18n import t


def spin(cfg: Config, key: str, lo: int, hi: int, suffix: str = "", step: int = 1) -> QSpinBox:
    w = QSpinBox()
    w.setMaximumWidth(190)
    w.setRange(lo, hi)
    w.setSingleStep(step)
    if suffix:
        w.setSuffix(suffix)
    w.reload = lambda: w.setValue(int(cfg.get(key, lo)))
    w.reload()
    w.valueChanged.connect(lambda v: cfg.set(key, int(v)))
    return w


def dspin(cfg: Config, key: str, lo: float, hi: float, step: float = 0.1, suffix: str = "") -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setMaximumWidth(190)
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setDecimals(2)
    if suffix:
        w.setSuffix(suffix)
    w.reload = lambda: w.setValue(float(cfg.get(key, lo)))
    w.reload()
    w.valueChanged.connect(lambda v: cfg.set(key, float(v)))
    return w


def check(cfg: Config, key: str, text: str, on_change=None) -> QCheckBox:
    w = QCheckBox(text)
    w.reload = lambda: w.setChecked(bool(cfg.get(key, False)))
    w.reload()

    def _changed(on):
        cfg.set(key, bool(on))
        if on_change:
            on_change(bool(on))

    w.toggled.connect(_changed)
    return w


def combo(cfg: Config, key: str, items: dict, on_change=None) -> QComboBox:
    w = QComboBox()
    for value, label in items.items():
        w.addItem(t(label), value)
    w.reload = lambda: w.setCurrentIndex(max(0, w.findData(cfg.get(key))))
    w.reload()

    def _changed(_):
        cfg.set(key, w.currentData())
        if on_change:
            on_change(w.currentData())

    w.currentIndexChanged.connect(_changed)
    return w
