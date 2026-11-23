"""Integración con Google Drive (REST API) para sincronizar el tabulador.

Sin dependencias externas: usa urllib. Requiere un client_id/client_secret de
Google Cloud (OAuth "Desktop app"). El usuario los introduce una sola vez; se
guardan en settings.json (junto a la app).
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "drive_token.json")
DRIVE_API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
OAUTH_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive.file"
FILE_NAME = "tabulador.csv"


def _settings() -> dict:
    path = os.path.join(BASE_DIR, "settings.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_settings(s: dict) -> None:
    path = os.path.join(BASE_DIR, "settings.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_credentials() -> tuple[str, str] | None:
    s = _settings()
    cid = s.get("driveClientId") or os.environ.get("GOOGLE_CLIENT_ID")
    csecret = s.get("driveClientSecret") or os.environ.get("GOOGLE_CLIENT_SECRET")
    # client_secret.json de Google
    cs_path = os.path.join(BASE_DIR, "client_secret.json")
    if (not cid or not csecret) and os.path.isfile(cs_path):
        try:
            with open(cs_path, encoding="utf-8") as f:
                data = json.load(f)
            installed = data.get("installed") or data.get("web") or {}
            cid = cid or installed.get("client_id")
            csecret = csecret or installed.get("client_secret")
        except Exception:
            pass
    if cid and csecret:
        return cid, csecret
    return None


def set_credentials(client_id: str, client_secret: str) -> None:
    s = _settings()
    s["driveClientId"] = client_id.strip()
    s["driveClientSecret"] = client_secret.strip()
    _save_settings(s)


def _load_token() -> dict | None:
    if not os.path.isfile(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_token(tok: dict) -> None:
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(tok, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def disconnect() -> None:
    try:
        os.remove(TOKEN_FILE)
    except FileNotFoundError:
        pass


def is_authenticated() -> bool:
    tok = _load_token()
    return bool(tok and tok.get("refresh_token"))


def _refresh_access_token() -> str | None:
    tok = _load_token()
    if not tok:
        return None
    creds = get_credentials()
    if not creds:
        return None
    cid, csecret = creds
    # si aún válido, reusar
    if tok.get("access_token") and tok.get("expires_at", 0) > time.time() + 60:
        return tok["access_token"]
    if not tok.get("refresh_token"):
        return None
    data = urllib.parse.urlencode({
        "client_id": cid,
        "client_secret": csecret,
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(OAUTH_TOKEN, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            new = json.loads(resp.read())
    except Exception:
        return None
    tok["access_token"] = new["access_token"]
    tok["expires_at"] = time.time() + new.get("expires_in", 3600) - 60
    _save_token(tok)
    return tok["access_token"]


def _authed_request(method: str, url: str, data: bytes | None = None, headers: dict | None = None) -> Any:
    token = _refresh_access_token()
    if not token:
        raise RuntimeError("No autenticado con Google Drive")
    h = {"Authorization": f"Bearer {token}"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            if not raw:
                return None
            try:
                return json.loads(raw)
            except Exception:
                return raw
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Drive API {exc.code}: {body}")


def auth_url(redirect_port: int) -> str:
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Faltan credenciales de Google (client_id/client_secret)")
    cid, _ = creds
    params = {
        "client_id": cid,
        "redirect_uri": f"http://localhost:{redirect_port}",
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    return OAUTH_AUTH + "?" + urllib.parse.urlencode(params)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        err = qs.get("error", [None])[0]
        self.server.result = {"code": code, "error": err}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if err:
            self.wfile.write(b"<h1>Error de autorizacion</h1><p>Puedes cerrar esta ventana.</p>")
        else:
            self.wfile.write(b"<h1>Autorizado</h1><p>Puedes cerrar esta ventana y volver a la app.</p>")
    def log_message(self, *args):
        pass


def run_auth_flow(timeout: int = 300) -> str:
    """Abre el navegador, espera el codigo de autorizacion y devuelve el code."""
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Faltan credenciales de Google")
    # puerto libre
    port = 8766
    for candidate in range(8766, 8780):
        try:
            httpd = http.server.HTTPServer(("127.0.0.1", candidate), _CallbackHandler)
            port = candidate
            break
        except OSError:
            continue
    else:
        raise RuntimeError("No se pudo abrir un puerto para la autorizacion")
    httpd.result = None
    url = auth_url(port)
    # abrir navegador
    import webbrowser
    webbrowser.open(url)
    # esperar codigo
    deadline = time.time() + timeout
    while time.time() < deadline:
        httpd.handle_request()
        if httpd.result is not None:
            break
    else:
        httpd.server_close()
        raise RuntimeError("Tiempo de espera agotado para la autorizacion")
    result = httpd.result
    httpd.server_close()
    if result.get("error"):
        raise RuntimeError(f"Error de autorizacion: {result['error']}")
    code = result.get("code")
    if not code:
        raise RuntimeError("No se recibio codigo de autorizacion")
    redirect_uri = f"http://localhost:{port}"
    _exchange_code(code, redirect_uri)
    return code


def _exchange_code(code: str, redirect_uri: str) -> None:
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Faltan credenciales de Google")
    cid, csecret = creds
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": cid,
        "client_secret": csecret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(OAUTH_TOKEN, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        tok = json.loads(resp.read())
    token = {
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        "expires_at": time.time() + tok.get("expires_in", 3600) - 60,
    }
    if not token["refresh_token"]:
        # reusar el anterior si no vino uno nuevo
        old = _load_token()
        if old and old.get("refresh_token"):
            token["refresh_token"] = old["refresh_token"]
    _save_token(token)


def _find_file(name: str) -> str | None:
    q = f"name = '{name}' and trashed = false"
    url = f"{DRIVE_API}/files?q={urllib.parse.quote(q)}&fields=files(id,name,modifiedTime,md5Checksum)&spaces=drive"
    res = _authed_request("GET", url)
    files = (res or {}).get("files", [])
    if not files:
        return None
    return files[0]["id"]


def download_tabulador() -> str | None:
    """Descarga el tabulador de Drive y devuelve su contenido (str) o None si no existe."""
    fid = _find_file(FILE_NAME)
    if not fid:
        return None
    url = f"{DRIVE_API}/files/{fid}?alt=media"
    token = _refresh_access_token()
    if not token:
        raise RuntimeError("No autenticado")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def upload_tabulador(content: str, file_id: str | None = None) -> str:
    """Sube/actualiza el tabulador en Drive. Devuelve el file_id."""
    creds_boundary = "----tabuladorboundary"
    metadata = {"name": FILE_NAME, "mimeType": "text/csv"}
    body = []
    body.append(f"--{creds_boundary}")
    body.append("Content-Type: application/json; charset=UTF-8")
    body.append("")
    body.append(json.dumps(metadata))
    body.append(f"--{creds_boundary}")
    body.append("Content-Type: text/csv; charset=UTF-8")
    body.append("")
    body.append(content)
    body.append(f"--{creds_boundary}--")
    body_str = "\r\n".join(body)
    data = body_str.encode("utf-8")

    if file_id:
        url = f"{UPLOAD_API}/files/{file_id}?uploadType=multipart"
        method = "PATCH"
    else:
        url = f"{UPLOAD_API}/files?uploadType=multipart"
        method = "POST"
    res = _authed_request(method, url, data=data, headers={"Content-Type": f"multipart/related; boundary={creds_boundary}"})
    return (res or {}).get("id") or file_id


def sync() -> dict:
    """Sincroniza: si Drive tiene el archivo, descarga; si no, sube el local."""
    import store
    local_path = os.path.join(store.DATA_DIR, "tabulador.csv")
    # leer local si existe
    local_content = None
    if os.path.exists(local_path):
        with open(local_path, encoding="utf-8-sig") as f:
            local_content = f.read()
    remote_id = _find_file(FILE_NAME)
    if remote_id:
        remote_content = download_tabulador()
        # comparar; si difiere, sobrescribir local con remoto
        if remote_content != local_content:
            os.makedirs(store.DATA_DIR, exist_ok=True)
            with open(local_path, "w", encoding="utf-8", newline="") as f:
                f.write(remote_content)
            return {"action": "downloaded", "message": "Tabulador descargado de Drive"}
        return {"action": "none", "message": "Ya está sincronizado"}
    else:
        if local_content is None:
            return {"action": "none", "message": "No hay tabulador local para subir"}
        fid = upload_tabulador(local_content)
        return {"action": "uploaded", "message": "Tabulador subido a Drive"}


def status() -> dict:
    creds = get_credentials()
    return {
        "hasCredentials": creds is not None,
        "authenticated": is_authenticated(),
    }