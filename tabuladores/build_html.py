#!/usr/bin/env python3
"""
Genera la versión HTML de un solo archivo.

Toma html/app.html, le incrusta el tabulador (data/tabulador-simple.csv),
el logo (assets/logo-mark.png) y escribe dist/Tabuladores-WualaExpress.html.

Uso:
    python3 build_html.py
    python3 build_html.py --csv data/otro.csv --out /ruta/salida.html
"""

from __future__ import annotations

import argparse
import base64
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(BASE_DIR, "html", "app.html")
DEFAULT_CSV = os.path.join(BASE_DIR, "data", "tabulador.csv")
LOGO = os.path.join(BASE_DIR, "assets", "logo-mark.png")
DEFAULT_OUT = os.path.join(os.path.dirname(BASE_DIR), "dist", "Tabuladores-WualaExpress.html")


def js_string(text: str) -> str:
    """Devuelve un literal JS seguro para incrustar dentro de <script>."""
    literal = json.dumps(text, ensure_ascii=False)
    # Evita cerrar el <script> si el CSV contuviera "</script".
    return literal.replace("</", "<\\/")


def build(csv_path: str, logo_path: str, out_path: str) -> str:
    with open(TEMPLATE, "r", encoding="utf-8") as fh:
        html = fh.read()

    with open(csv_path, "r", encoding="utf-8-sig") as fh:
        csv_text = fh.read()

    with open(logo_path, "rb") as fh:
        logo_data = base64.b64encode(fh.read()).decode("ascii")

    if "__CSV_JSON__" not in html:
        raise SystemExit("La plantilla no contiene el marcador __CSV_JSON__")
    if "__LOGO_DATA_URI__" not in html:
        raise SystemExit("La plantilla no contiene el marcador __LOGO_DATA_URI__")

    html = html.replace("__CSV_JSON__", js_string(csv_text), 1)
    html = html.replace("__LOGO_DATA_URI__", f"data:image/png;base64,{logo_data}", 1)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--logo", default=LOGO)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    out = build(args.csv, args.logo, args.out)
    size = os.path.getsize(out)
    print(f"OK: {out} ({size / 1024:.0f} KB)")
    print(f"CSV: {args.csv}")
    print("Ábrelo con doble clic en cualquier navegador; no necesita servidor.")


if __name__ == "__main__":
    main()
