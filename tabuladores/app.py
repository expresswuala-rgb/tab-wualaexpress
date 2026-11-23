#!/usr/bin/env python3
"""
Generador de tabuladores por ruta — app web local.

Uso:
    python3 app.py            # http://127.0.0.1:8765
    python3 app.py --port 9000

Sin dependencias externas salvo Pillow (ya instalado).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import threading
import uuid
import webbrowser
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import render
import store
try:
    import drive
except Exception:  # noqa: BLE001
    drive = None  # type: ignore[assignment]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
OUT_DIR = os.path.join(BASE_DIR, "salidas")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")


def load_settings() -> dict:
    if not os.path.isfile(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle) or {}
    except Exception:
        return {}


def save_settings(settings: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".csv": "text/csv; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "tabulador"


def generate(ids: list[str], options: dict) -> list[dict]:
    os.makedirs(OUT_DIR, exist_ok=True)
    theme = options.get("estilo") or "oscuro"
    if theme not in render.THEMES:
        theme = "oscuro"
    results = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for route_id in ids:
        route = store.get_route(route_id)
        if route is None:
            continue
        base = safe_name(f"salida_{route.origin}_{stamp}_{uuid.uuid4().hex[:4]}")
        out = os.path.join(OUT_DIR, base + ".png")
        render.render_route(route, out, theme=theme)
        results.append({
            "id": route.id,
            "name": route.origin,
            "file": os.path.basename(out),
            "url": "/salidas/" + os.path.basename(out),
            "destinations": len(route.destinations),
        })
    return results


def render_preview(route_id: str, theme: str) -> bytes | None:
    route = store.get_route(route_id)
    if route is None:
        return None
    if theme not in render.THEMES:
        theme = "oscuro"
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = os.path.join(OUT_DIR, f".preview_{uuid.uuid4().hex}.png")
    render.render_route(route, tmp, theme=theme)
    with open(tmp, "rb") as handle:
        data = handle.read()
    try:
        os.remove(tmp)
    except OSError:
        pass
    return data


class Handler(BaseHTTPRequestHandler):
    server_version = "Tabuladores/1.0"

    def log_message(self, fmt, *args):  # silencio en consola
        pass

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), MIME[".json"])

    def _file(self, path: str):
        if not os.path.isfile(path):
            self._json(404, {"error": "no encontrado"})
            return
        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as handle:
            body = handle.read()
        self._send(200, body, MIME.get(ext, "application/octet-stream"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path in ("/", "/index.html"):
            self._file(os.path.join(STATIC_DIR, "index.html"))
            return
        if path == "/api/routes":
            tariffs = store.load_tariffs()
            payload = []
            for tariff in tariffs:
                routes = store.routes_of(tariff)
                payload.append({
                    "id": tariff.id,
                    "name": tariff.name,
                    "zones": len(tariff.zones),
                    "source": tariff.source,
                    "routes": [
                        {
                            "id": route.id,
                            "name": route.origin,
                            "destinations": len(route.destinations),
                        }
                        for route in routes
                    ],
                })
            self._json(200, {"tariffs": payload, "dataDir": store.DATA_DIR})
            return
        if path == "/api/zip":
            ids = [v for v in parse_qs(parsed.query).get("ids", [""])[0].split(",") if v]
            style = parse_qs(parsed.query).get("estilo", ["oscuro"])[0]
            files = generate(ids, {"estilo": style})
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in files:
                    archive.write(os.path.join(OUT_DIR, item["file"]), arcname=item["file"])
            self._send(
                200,
                buffer.getvalue(),
                "application/zip",
                {"Content-Disposition": 'attachment; filename="tabuladores.zip"'},
            )
            return
        if path.startswith("/salidas/"):
            self._file(os.path.join(OUT_DIR, os.path.basename(path)))
            return
        if path.startswith("/static/"):
            self._file(os.path.join(STATIC_DIR, os.path.basename(path)))
            return
        if path == "/api/preview":
            route_id = parse_qs(parsed.query).get("id", [""])[0]
            style = parse_qs(parsed.query).get("estilo", ["oscuro"])[0]
            data = render_preview(route_id, style)
            if data is None:
                self._json(404, {"error": "ruta no encontrada"})
                return
            self._send(200, data, "image/png")
            return
        if path == "/api/drive/status":
            if drive is None:
                self._json(200, {"hasCredentials": False, "authenticated": False, "available": False})
                return
            self._json(200, {**drive.status(), "available": True})
            return
        if path == "/api/tariff":
            tariff_id = parse_qs(parsed.query).get("id", [""])[0]
            tariff = store.get_tariff(tariff_id)
            if tariff is None:
                self._json(404, {"error": "tabulador no encontrado"})
                return
            origins = getattr(tariff, "origins", [])
            self._json(200, {
                "id": tariff.id,
                "name": tariff.name,
                "zones": tariff.zones,
                "origins": origins,
                "grid": tariff.grid,
                "source": tariff.source,
            })
            return
        if path == "/api/export-tariff":
            tariff_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                filename, content = store.export_csv(tariff_id)
            except Exception as exc:  # noqa: BLE001
                self._json(400, {"error": str(exc)})
                return
            self._send(
                200,
                content.encode("utf-8"),
                "text/csv; charset=utf-8",
                {"Content-Disposition": f'attachment; filename="{filename}"'},
            )
            return
        if path == "/favicon.ico":
            self._file(os.path.join(STATIC_DIR, "favicon.ico"))
            return
        self._json(404, {"error": "ruta no encontrada"})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "JSON inválido"})
            return

        if parsed.path == "/api/generate":
            ids = payload.get("ids") or []
            options = payload.get("options") or {}
            if not ids:
                self._json(400, {"error": "Selecciona al menos una ruta"})
                return
            try:
                results = generate(ids, options)
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"error": str(exc)})
                return
            self._json(200, {"results": results})
            return

        if parsed.path == "/api/settings":
            settings = load_settings()
            if "dataDir" in payload and payload.get("dataDir"):
                settings["dataDir"] = os.path.abspath(payload["dataDir"])
                store.set_data_dir(settings["dataDir"])
            if "outDir" in payload and payload.get("outDir"):
                settings["outDir"] = os.path.abspath(payload["outDir"])
                global OUT_DIR
                OUT_DIR = settings["outDir"]
                os.makedirs(OUT_DIR, exist_ok=True)
            save_settings(settings)
            self._json(200, {"settings": settings, "dataDir": store.DATA_DIR, "outDir": OUT_DIR})
            return

        if parsed.path == "/api/drive/credentials":
            if drive is None:
                self._json(500, {"error": "Módulo de Drive no disponible"})
                return
            cid = (payload.get("clientId") or "").strip()
            csecret = (payload.get("clientSecret") or "").strip()
            if not cid or not csecret:
                self._json(400, {"error": "Faltan client_id o client_secret"})
                return
            drive.set_credentials(cid, csecret)
            self._json(200, {"ok": True})
            return

        if parsed.path == "/api/drive/connect":
            if drive is None:
                self._json(500, {"error": "Módulo de Drive no disponible"})
                return
            try:
                drive.run_auth_flow(timeout=120)
            except Exception as exc:  # noqa: BLE001
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"ok": True, **drive.status()})
            return

        if parsed.path == "/api/drive/sync":
            if drive is None:
                self._json(500, {"error": "Módulo de Drive no disponible"})
                return
            try:
                result = drive.sync()
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"error": str(exc)})
                return
            # recargar rutas tras sync
            self._json(200, result)
            return

        if parsed.path == "/api/drive/disconnect":
            if drive is not None:
                drive.disconnect()
            self._json(200, {"ok": True})
            return

        if parsed.path == "/api/import-csv":
            name = (payload.get("name") or "tabulador.csv").strip()
            content = payload.get("content") or ""
            if not content.strip():
                self._json(400, {"error": "El CSV está vacío"})
                return
            try:
                tariff = store.import_csv(name, content)
            except Exception as exc:  # noqa: BLE001
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {
                "tariff": {
                    "id": tariff.id,
                    "name": tariff.name,
                    "zones": len(tariff.zones),
                    "source": tariff.source,
                }
            })
            return

        if parsed.path == "/api/save-tariff":
            tariff_id = (payload.get("id") or "").strip()
            zones = payload.get("zones") or []
            origins = payload.get("origins") or []
            grid = payload.get("grid") or []
            if not tariff_id:
                self._json(400, {"error": "Falta el id del tabulador"})
                return
            try:
                tariff = store.save_tariff(tariff_id, zones, origins, grid)
            except Exception as exc:  # noqa: BLE001
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {
                "tariff": {
                    "id": tariff.id,
                    "name": tariff.name,
                    "zones": len(tariff.zones),
                    "origins": len(getattr(tariff, "origins", [])),
                    "source": tariff.source,
                }
            })
            return

        self._json(404, {"error": "ruta no encontrada"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--open", action="store_true", help="abrir el navegador al iniciar")
    parser.add_argument("--data-dir", default=None, help="carpeta de datos (CSV). Por defecto: data/ junto a la app. Usa una carpeta sincronizada (Drive/Dropbox) para compartir entre dispositivos.")
    parser.add_argument("--out-dir", default=None, help="carpeta de salida para los PNG. Por defecto: salidas/ junto a la app.")
    args = parser.parse_args()

    settings = load_settings()
    if args.data_dir:
        store.set_data_dir(args.data_dir)
    elif settings.get("dataDir"):
        store.set_data_dir(settings["dataDir"])
    if args.out_dir:
        global OUT_DIR
        OUT_DIR = os.path.abspath(args.out_dir)
    elif settings.get("outDir"):
        OUT_DIR = os.path.abspath(settings["outDir"])
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(store.DATA_DIR, exist_ok=True)

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print(f"No se pudo abrir el puerto {args.port}: {exc}")
        print(f"Prueba con otro puerto: python3 app.py --port {args.port + 1}")
        return
    print(f"Tabuladores en http://{args.host}:{args.port}")
    print("Ctrl+C para detener.")
    if args.open:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
