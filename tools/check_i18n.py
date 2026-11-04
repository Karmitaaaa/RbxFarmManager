"""Comprueba las traducciones: textos sin traducir, sobrantes y huecos ({0}, %s) que no coinciden.

    python tools/check_i18n.py            revisa todos los idiomas de locales/
    python tools/check_i18n.py --keys     lista los textos a traducir (para empezar un idioma nuevo)
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLE = re.compile(r"\{\d+[^}]*\}|%[sd]|%\.\d+f")


def source_texts() -> dict[str, str]:
    """{texto: dónde aparece} de cada t("…") y N_("…") del código."""
    texts: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*.py")):
        if {".venv", "tools", "build", "dist"} & set(path.relative_to(ROOT).parts):
            continue
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("t", "N_")
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                texts.setdefault(node.args[0].value, f"{path.relative_to(ROOT)}:{node.lineno}")
    return texts


def main() -> int:
    texts = source_texts()
    if "--keys" in sys.argv:
        print(json.dumps(sorted(texts), ensure_ascii=False, indent=0))
        return 0
    problems = 0
    for locale in sorted((ROOT / "locales").glob("*.json")):
        table = json.loads(locale.read_text("utf-8"))
        table.pop("@language", None)
        for text, where in texts.items():
            if text not in table:
                print(f"{locale.name}: falta {text!r} ({where})")
                problems += 1
            elif sorted(HOLE.findall(text)) != sorted(HOLE.findall(table[text])):
                print(f"{locale.name}: huecos distintos en {text!r}")
                problems += 1
        for extra in set(table) - set(texts):
            print(f"{locale.name}: sobra {extra!r}")
            problems += 1
    print(f"{len(texts)} textos, {problems} problemas")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
