"""Genera assets/icon.ico a partir del icono dibujado por la app (se usa al empaquetar)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.widgets import app_icon  # noqa: E402

app = QApplication(sys.argv)
out = ROOT / "assets" / "icon.ico"
out.parent.mkdir(exist_ok=True)
if not app_icon().pixmap(QSize(256, 256)).save(str(out), "ICO"):
    raise SystemExit("No se pudo escribir el icono")
print(f"Icono creado: {out}")
