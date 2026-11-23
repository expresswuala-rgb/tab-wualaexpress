"""Carga de tabuladores desde archivos locales (CSV).

Un archivo CSV = un tabulador completo:
  - La primera columna es el ORIGEN (columna A).
  - La primera fila, desde la columna B, son los DESTINOS (fila 1).
  - El cruce origen x destino es el costo del viaje.

Cada fila de origen es, por tanto, una "ruta" (salida) con sus precios.
"""

from __future__ import annotations

import csv
import io
import os
import re
import unicodedata
from dataclasses import dataclass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("TABULADORES_DATA_DIR") or os.path.join(BASE_DIR, "data")


def set_data_dir(path: str) -> None:
    global DATA_DIR
    DATA_DIR = os.path.abspath(path)
    os.makedirs(DATA_DIR, exist_ok=True)


@dataclass
class Tariff:
    id: str
    name: str
    zones: list[str]          # destinos (fila 1, desde la columna B)
    grid: list[list[str]]     # grid[origen][destino]
    source: str = ""


@dataclass
class Route:
    """Una ruta = un origen del tabulador, con sus precios a cada destino."""

    id: str
    tariff_id: str
    tariff_name: str
    index: int
    origin: str
    destinations: list[str]
    prices: list[str]
    source: str = ""


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "tabulador"


def _parse_csv_text(text: str) -> tuple[dict[str, str], list[list[str]]]:
    rows = [row for row in csv.reader(io.StringIO(text))]
    meta: dict[str, str] = {}
    data: list[list[str]] = []
    for row in rows:
        if not row or all(not (cell or "").strip() for cell in row):
            continue
        first = (row[0] or "").strip()
        if first.startswith("#"):
            body = first.lstrip("#").strip()
            if ":" in body:
                key, value = body.split(":", 1)
                meta[key.strip().lower()] = value.strip()
            elif "nombre" not in meta:
                meta["nombre"] = body
            continue
        data.append([(cell or "").strip() for cell in row])
    return meta, data


def _read_csv(path: str) -> tuple[dict[str, str], list[list[str]]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return _parse_csv_text(handle.read())


# Un solo tabulador: archivo canónico.
CANONICAL_CSV = "tabulador.csv"


def _single_csv_path() -> str | None:
    """Devuelve la ruta del único CSV a usar (canónico o el primero disponible)."""
    if not os.path.isdir(DATA_DIR):
        return None
    canonical = os.path.join(DATA_DIR, CANONICAL_CSV)
    if os.path.exists(canonical):
        return canonical
    others = sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv"))
    if not others:
        return None
    return os.path.join(DATA_DIR, others[0])


def load_tariffs() -> list[Tariff]:
    tariffs: list[Tariff] = []
    path = _single_csv_path()
    if path is None:
        return tariffs
    filename = os.path.basename(path)
    try:
        meta, data = _read_csv(path)
    except Exception:
        return tariffs
    if len(data) < 2:
        return tariffs
    header = data[0]
    zones = [zone for zone in header[1:] if zone]
    if not zones:
        return tariffs
    n = len(zones)
    grid: list[list[str]] = []
    origins: list[str] = []
    for row in data[1:]:
        origin = (row[0] if row else "").strip()
        if not origin:
            continue
        values = [(cell or "").strip() for cell in row[1:]]
        values = (values + [""] * n)[:n]
        origins.append(origin)
        grid.append(values)
    if not grid:
        return tariffs
    name = meta.get("nombre") or meta.get("tabulador") or os.path.splitext(filename)[0]
    tariff_id = meta.get("id") or _slug(os.path.splitext(filename)[0])
    tariff = Tariff(id=tariff_id, name=name, zones=zones, grid=grid, source=filename)
    tariff.origins = origins  # type: ignore[attr-defined]
    tariffs.append(tariff)
    return tariffs


def routes_of(tariff: Tariff) -> list[Route]:
    origins: list[str] = getattr(tariff, "origins", [])
    routes: list[Route] = []
    for index, origin in enumerate(origins):
        routes.append(
            Route(
                id=f"{tariff.id}::{index}",
                tariff_id=tariff.id,
                tariff_name=tariff.name,
                index=index,
                origin=origin,
                destinations=tariff.zones,
                prices=tariff.grid[index],
                source=tariff.source,
            )
        )
    return routes


def load_routes() -> list[Route]:
    routes: list[Route] = []
    for tariff in load_tariffs():
        routes.extend(routes_of(tariff))
    return routes


def import_csv(filename: str, content: str) -> Tariff:
    """Valida un CSV, lo guarda en data/ y devuelve el Tariff creado."""
    meta, data = _parse_csv_text(content)
    if len(data) < 2:
        raise ValueError("El CSV debe tener al menos un origen y un destino")
    header = data[0]
    zones = [zone for zone in header[1:] if zone]
    if not zones:
        raise ValueError("Falta la fila de destinos (fila 1, desde la columna B)")
    n = len(zones)
    origins: list[str] = []
    grid: list[list[str]] = []
    for row in data[1:]:
        origin = (row[0] if row else "").strip()
        if not origin:
            continue
        values = [(cell or "").strip() for cell in row[1:]]
        values = (values + [""] * n)[:n]
        origins.append(origin)
        grid.append(values)
    if not grid:
        raise ValueError("No hay filas de origen")
    name = meta.get("nombre") or meta.get("tabulador") or os.path.splitext(filename)[0]
    tariff_id = meta.get("id") or _slug(os.path.splitext(filename)[0])
    # evitar sobrescribir: si el id ya existe, sufijar
    existing = {t.id for t in load_tariffs()}
    if tariff_id in existing:
        tariff_id = f"{tariff_id}-{len(existing) + 1}"
    # Un solo tabulador: se sobrescribe el archivo canónico y se eliminan los demás.
    os.makedirs(DATA_DIR, exist_ok=True)
    for old in os.listdir(DATA_DIR):
        if old.lower().endswith(".csv") and old != CANONICAL_CSV:
            try:
                os.remove(os.path.join(DATA_DIR, old))
            except OSError:
                pass
    target = os.path.join(DATA_DIR, CANONICAL_CSV)
    with open(target, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    tariff = Tariff(id=tariff_id, name=name, zones=zones, grid=grid, source=CANONICAL_CSV)
    tariff.origins = origins  # type: ignore[attr-defined]
    return tariff


def get_tariff(tariff_id: str) -> Tariff | None:
    for tariff in load_tariffs():
        if tariff.id == tariff_id:
            return tariff
    return None


def export_csv(tariff_id: str) -> tuple[str, str]:
    tariff = get_tariff(tariff_id)
    if tariff is None:
        raise ValueError("Tabulador no encontrado")
    origins = getattr(tariff, "origins", [])
    # leer meta originales si existen
    meta_lines: list[str] = []
    if tariff.source:
        path = os.path.join(DATA_DIR, tariff.source)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as handle:
                for line in handle:
                    if line.strip().startswith("#"):
                        meta_lines.append(line.rstrip("\r\n"))
    if not any("nombre" in m.lower().split(":")[0] if ":" in m else False for m in meta_lines):
        meta_lines.insert(0, f"# nombre: {tariff.name}")
    if not any("id" in (m.lower().split(":")[0] if ":" in m else "") for m in meta_lines):
        meta_lines.append(f"# id: {tariff.id}")
    buf = io.StringIO()
    for m in meta_lines:
        buf.write(m + "\n")
    writer = csv.writer(buf)
    writer.writerow(["De\\A"] + tariff.zones)
    for origin, row in zip(origins, tariff.grid):
        writer.writerow([origin] + [("" if v is None else str(v).strip()) for v in row])
    filename = tariff.source or (tariff.id + ".csv")
    return filename, buf.getvalue()


def save_tariff(tariff_id: str, zones: list[str], origins: list[str], grid: list[list[str]]) -> Tariff:
    zones = [str(z).strip() for z in zones]
    origins = [str(o).strip() for o in origins]
    if not zones:
        raise ValueError("Debe haber al menos una zona")
    if len(origins) != len(grid):
        raise ValueError("Número de orígenes y filas no coincide")
    n = len(zones)
    for row in grid:
        if len(row) != n:
            raise ValueError("La matriz debe ser cuadrada (origen x destino)")
    # validar precios
    for row in grid:
        for cell in row:
            if (cell or "").strip() == "":
                continue
            try:
                float(cell)
            except ValueError:
                raise ValueError(f"Precio inválido: {cell!r}")

    existing = get_tariff(tariff_id)
    name = existing.name if existing else tariff_id
    source = existing.source if existing else None

    # leer meta originales
    meta_lines: list[str] = []
    if source:
        path = os.path.join(DATA_DIR, source)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as handle:
                for line in handle:
                    if line.strip().startswith("#"):
                        meta_lines.append(line.rstrip("\r\n"))
    if not any("nombre" in m.lower().split(":")[0] if ":" in m else False for m in meta_lines):
        meta_lines.insert(0, f"# nombre: {name}")
    if not any("id" in (m.lower().split(":")[0] if ":" in m else "") for m in meta_lines):
        meta_lines.append(f"# id: {tariff_id}")

    # Un solo archivo: se migra al canónico y se eliminan los demás.
    os.makedirs(DATA_DIR, exist_ok=True)
    if source and source != CANONICAL_CSV:
        try:
            os.remove(os.path.join(DATA_DIR, source))
        except OSError:
            pass
    for old in os.listdir(DATA_DIR):
        if old.lower().endswith(".csv") and old != CANONICAL_CSV:
            try:
                os.remove(os.path.join(DATA_DIR, old))
            except OSError:
                pass
    target = os.path.join(DATA_DIR, CANONICAL_CSV)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as handle:
        for m in meta_lines:
            handle.write(m + "\n")
        writer = csv.writer(handle)
        writer.writerow(["De\\A"] + zones)
        for origin, row in zip(origins, grid):
            writer.writerow([origin] + [("" if v is None else str(v).strip()) for v in row])

    tariff = Tariff(id=tariff_id, name=name, zones=zones, grid=grid, source=os.path.basename(target))
    tariff.origins = origins  # type: ignore[attr-defined]
    return tariff


def get_route(route_id: str) -> Route | None:
    for route in load_routes():
        if route.id == route_id:
            return route
    return None
