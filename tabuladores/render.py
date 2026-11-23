"""
Render de tabuladores a imagen PNG.

Vista: una salida (origen) con sus destinos agrupados en una columna por
tarifa, imitando el diseño de referencia:
  - cabecera azul marino con la marca y el eslogan,
  - cinta carmesí con el título "SALIDAS DESDE <ORIGEN>",
  - tabla con una columna por zona (ZONA 1, ZONA 2, ...) con filas zebra
    y franja de precios.

Solo depende de Pillow.
"""

from __future__ import annotations

import os
import re

from PIL import Image, ImageDraw, ImageFont

from store import Route

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

FONT_DIR_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/ubuntu",
    "/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "C:\\Windows\\Fonts",
]


def _font_path(bold: bool) -> str:
    names = (
        ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Ubuntu-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"]
        if bold
        else ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Ubuntu-Regular.ttf", "arial.ttf", "Arial.ttf"]
    )
    for folder in FONT_DIR_CANDIDATES:
        for name in names:
            candidate = os.path.join(folder, name)
            if os.path.exists(candidate):
                return candidate
    return ""


_FONT_CACHE: dict[tuple[bool, int], ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (bold, size)
    if key not in _FONT_CACHE:
        path = _font_path(bold)
        _FONT_CACHE[key] = ImageFont.truetype(path, size) if path else ImageFont.load_default()
    return _FONT_CACHE[key]


# Tipografía propia para los destinos: Inter SemiBold se lee mejor en tamaño
# pequeño que la fuente del sistema (mayor altura de x y trazos parejos).
DEST_FONT_PATH = os.path.join(ASSETS_DIR, "fonts", "Inter-SemiBold.ttf")
_DEST_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def dest_font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _DEST_FONT_CACHE:
        if os.path.exists(DEST_FONT_PATH):
            _DEST_FONT_CACHE[size] = ImageFont.truetype(DEST_FONT_PATH, size)
        else:
            _DEST_FONT_CACHE[size] = font(size)
    return _DEST_FONT_CACHE[size]


# ---- Paletas ----------------------------------------------------------------
THEMES: dict[str, dict[str, tuple[int, int, int]]] = {
    # Diseño de referencia: azul marino + carmesí.
    "oscuro": {
        "page": (255, 255, 255),
        "header_from": (13, 26, 52),      # #0D1A34
        "header_to": (10, 58, 112),       # #0A3A70
        "header_text": (255, 255, 255),
        "header_soft": (176, 198, 226),
        "header_stripe": (255, 255, 255),
        "header_glow": (196, 34, 62),
        "band": (170, 16, 44),            # carmesí
        "band_dark": (116, 10, 30),
        "band_line": (232, 92, 112),
        "table_head": (10, 38, 74),       # azul marino sólido
        "table_text": (255, 255, 255),
        "table_divider": (56, 88, 130),
        "row_a": (255, 255, 255),
        "row_b": (232, 242, 252),
        "grid": (204, 223, 240),
        "cell_text": (18, 35, 59),
        "footer_bg": (10, 38, 74),
        "footer_text": (255, 255, 255),
        "strip": (8, 10, 26),
    },
    # Variante clara con identidad azul corporativa.
    "claro": {
        "page": (248, 250, 252),
        "header_from": (239, 246, 255),
        "header_to": (219, 234, 254),
        "header_text": (30, 58, 138),
        "header_soft": (100, 116, 139),
        "header_stripe": (37, 99, 235),
        "header_glow": (37, 99, 235),
        "band": (30, 58, 138),            # azul marino
        "band_dark": (15, 23, 42),
        "band_line": (96, 165, 250),
        "table_head": (30, 58, 138),      # azul marino
        "table_text": (255, 255, 255),
        "table_divider": (59, 130, 246),
        "row_a": (255, 255, 255),
        "row_b": (239, 246, 255),
        "grid": (219, 234, 254),
        "cell_text": (15, 23, 42),
        "footer_bg": (30, 58, 138),
        "footer_text": (255, 255, 255),
        "strip": (15, 23, 42),
    },
}

# Cada tarifa de la salida es una columna "ZONA n". Ancho mínimo por columna.
MIN_COL_W = 290
BASE_WIDTH = 2000

_SMALL_WORDS = {"de", "del", "y", "e", "da", "do", "en"}


# ---- Utilidades de texto ----------------------------------------------------


def zone_code(name: str) -> str:
    """'08.1 - Ruta Exterior (Campo Alegre)' -> '08.1'"""
    return name.split(" - ", 1)[0].strip() or name[:6]


def zone_label(name: str) -> str:
    """'08.1 - Ruta Exterior (Campo Alegre)' -> 'Ruta Exterior (Campo Alegre)'"""
    parts = name.split(" - ", 1)
    return parts[1].strip() if len(parts) == 2 else name


def strip_code(name: str) -> str:
    """Quita el código inicial ('13 - ' / '08.1 - ') de un nombre de zona."""
    return re.sub(r"^\d+(?:\.\d+)?\s*-\s*", "", name or "").strip() or (name or "")


def fmt_value(value: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return (value or "").strip()
    if number == int(number):
        return str(int(number))
    return ("%.2f" % number).rstrip("0").rstrip(".")


def fmt_price(value: float) -> str:
    return "$%.2f" % value


def _cap_word(word: str) -> str:
    """Mayúscula en la primera letra, respetando paréntesis y guiones."""
    out = []
    seen = False
    for ch in word:
        if ch.isalpha():
            out.append(ch.upper() if not seen else ch.lower())
            seen = True
        else:
            out.append(ch)
    return "".join(out)


def pretty(text: str) -> str:
    """Title Case conservando siglas (ZIMCA, ZONA...) y palabras cortas."""
    parts = re.split(r"(\s+)", text)
    out = []
    index = 0
    for part in parts:
        if not part.strip():
            out.append(part)
            continue
        core = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", part)
        if core.isupper() and len(core) > 1:
            out.append(part)
            index += 1
            continue
        if index > 0 and core.lower() in _SMALL_WORDS:
            out.append(part.lower())
        else:
            out.append(_cap_word(part))
        index += 1
    return "".join(out)


def group_by_price(route: Route) -> list[tuple[float | None, list[int]]]:
    """Una columna por cada tarifa (precio) distinta de la salida.

    Devuelve pares (precio, índices de destinos) ordenados de menor a mayor.
    Las celdas sin precio válido quedan en una última columna con precio None.
    """
    groups: dict[float, list[int]] = {}
    unknown: list[int] = []
    for idx, raw in enumerate(route.prices):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            unknown.append(idx)
            continue
        groups.setdefault(round(value, 2), []).append(idx)
    ordered = [(value, groups[value]) for value in sorted(groups)]
    if unknown:
        ordered.append((None, unknown))
    return ordered


def price_label(value: float | None) -> str:
    return fmt_price(value) if value is not None else "—"


# ---- Utilidades de dibujo ---------------------------------------------------


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, size: int, bold: bool, min_size: int = 16):
    while size > min_size and draw.textlength(text, font=font(size, bold)) > max_width:
        size -= 2
    return font(size, bold)


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> str:
    if draw.textlength(text, font=fnt) <= max_width:
        return text
    ellipsis = "…"
    while text and draw.textlength(text + ellipsis, font=fnt) > max_width:
        text = text[:-1]
    return text.rstrip() + ellipsis


def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int, max_lines: int = 2) -> list[str]:
    """Reparte el texto en varias líneas; recorta con … si no cabe."""
    words = text.split()
    lines: list[str] = []
    while words and len(lines) < max_lines:
        line = words.pop(0)
        while words and draw.textlength(line + " " + words[0], font=fnt) <= max_width:
            line += " " + words.pop(0)
        lines.append(line)
    if words:
        lines[-1] = lines[-1] + " " + " ".join(words)
    return [_ellipsize(draw, line, fnt, max_width) for line in lines]


def _center(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], text: str, fnt, fill) -> None:
    x0, y0, x1, y1 = box
    left, top, right, bottom = draw.textbbox((0, 0), text, font=fnt)
    tw, th = right - left, bottom - top
    draw.text((x0 + (x1 - x0 - tw) / 2 - left, y0 + (y1 - y0 - th) / 2 - top), text, font=fnt, fill=fill)


def _spaced_width(draw: ImageDraw.ImageDraw, text: str, fnt, spacing: int) -> float:
    return sum(draw.textlength(ch, font=fnt) for ch in text) + spacing * max(len(text) - 1, 0)


def _draw_spaced(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    fnt,
    fill,
    spacing: int = 4,
    right: float | None = None,
) -> None:
    x, y = xy
    if right is not None:
        x = right - _spaced_width(draw, text, fnt, spacing)
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + spacing


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    if top == bottom:
        return Image.new("RGB", size, top)
    base = Image.new("RGB", (1, h))
    px = base.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return base.resize((w, h), Image.BILINEAR)


def _draw_moto(draw: ImageDraw.ImageDraw, x: float, y: float, w: float, color) -> None:
    """Icono de reparto: dos ruedas, chasis y caja."""
    r = w * 0.135
    cy = y + w * 0.24
    lw = max(3, int(w * 0.028))
    rear = (x + r, cy)
    front = (x + w - r, cy)
    for cx, cc in ((rear, rear), (front, front)):
        draw.ellipse((cc[0] - r, cc[1] - r, cc[0] + r, cc[1] + r), outline=color, width=lw)
        draw.ellipse((cc[0] - r * 0.32, cc[1] - r * 0.32, cc[0] + r * 0.32, cc[1] + r * 0.32), fill=color)

    frame = [
        (rear[0] + r * 0.4, cy),
        (x + w * 0.44, cy - w * 0.22),
        (front[0], cy),
    ]
    draw.line(frame, fill=color, width=lw, joint="curve")
    draw.line([(x + w * 0.30, cy), (x + w * 0.50, cy - w * 0.22), (x + w * 0.70, cy - w * 0.06)], fill=color, width=lw, joint="curve")
    # manillar / asiento
    draw.line([(x + w * 0.62, cy - w * 0.22), (x + w * 0.70, cy - w * 0.40)], fill=color, width=lw)
    draw.line([(x + w * 0.66, cy - w * 0.40), (x + w * 0.78, cy - w * 0.40)], fill=color, width=lw)
    # caja de reparto
    draw.rounded_rectangle(
        (x + w * 0.10, cy - w * 0.50, x + w * 0.34, cy - w * 0.24),
        radius=max(3, int(w * 0.03)),
        outline=color,
        width=lw,
    )


def _round_top(draw: ImageDraw.ImageDraw, box, radius: int, fill) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill)
    draw.rectangle((x0, y0 + radius, x1, y1), fill=fill)


def _round_bottom(draw: ImageDraw.ImageDraw, box, radius: int, fill) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill)
    draw.rectangle((x0, y0, x1, y1 - radius), fill=fill)


# ---- Render -----------------------------------------------------------------


def render_route(
    route: Route,
    out_path: str,
    *,
    include_summary: bool = False,  # compatibilidad con versiones anteriores
    theme: str = "oscuro",
    width: int | None = None,
) -> str:
    pal = THEMES.get(theme, THEMES["oscuro"])

    margin = 70
    header_h = 176
    band_h = 92
    gap_band_table = 30
    head_h = 56
    foot_h = 62
    bottom_pad = 30
    strip_h = 14
    radius = 16

    groups = group_by_price(route)
    if not groups:
        groups = [(None, [])]
    cols = len(groups)

    # Ancho: una columna por tarifa; si hay muchas, la imagen se ensancha.
    if width is None:
        width = max(BASE_WIDTH, 2 * margin + cols * MIN_COL_W)
    width = int(width)
    col_w = (width - 2 * margin) / cols

    # Destinos: Inter SemiBold. Subido un paso más (a petición del usuario).
    dest_size = 24 if col_w < 310 else (26 if col_w < 360 else 28)
    row_h = max(56, 2 * (dest_size + 6))

    rows = max(8, max((len(indexes) for _, indexes in groups), default=0))

    table_h = head_h + rows * row_h + foot_h
    height = header_h + band_h + gap_band_table + table_h + bottom_pad + strip_h

    img = Image.new("RGB", (width, height), pal["page"])
    draw = ImageDraw.Draw(img)
    right = width - margin
    inner = right - margin

    # ---- Cabecera de marca -------------------------------------------------
    header = _gradient((width, header_h), pal["header_from"], pal["header_to"]).convert("RGBA")
    overlay = Image.new("RGBA", header.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(-260, width + 320, 300):
        od.polygon(
            [(x, header_h), (x + 110, header_h), (x + 110 + header_h * 0.75, 0), (x + header_h * 0.75, 0)],
            fill=pal["header_stripe"] + (12,),
        )
    od.ellipse((-160, -150, 300, 260), fill=pal["header_glow"] + (38,))
    od.ellipse((width - 520, header_h - 90, width + 120, header_h + 190), fill=pal["header_glow"] + (26,))
    for i in range(14):
        cx = width * 0.52 + i * 26
        cy = 26 + (i % 4) * 14
        od.ellipse((cx, cy, cx + 4, cy + 4), fill=(255, 255, 255, 46))
    header = Image.alpha_composite(header, overlay).convert("RGB")
    img.paste(header, (0, 0))

    # logo circular
    logo_path = os.path.join(ASSETS_DIR, "logo-mark.png")
    badge = 104
    badge_x = margin + 4
    badge_y = 24
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((badge, badge), Image.LANCZOS)
        img.paste(logo, (badge_x, badge_y), logo)
    else:
        cx, cy, r = badge_x + badge // 2, badge_y + badge // 2, badge // 2 - 4
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=pal["header_text"], width=4)
        draw.arc((cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8), start=205, end=335, fill=(209, 7, 17), width=9)
        _center(draw, (cx - r, cy - r, cx + r, cy + r), "W", font(64, True), pal["header_text"])

    # Nombre de la empresa: el logo es un ícono, así que el texto lo completa.
    brand_cx = badge_x + badge // 2
    brand_font_top = font(20, True)
    brand_font_bot = font(14, True)
    top_w = _spaced_width(draw, "WUALA", brand_font_top, 4)
    _draw_spaced(
        draw,
        (brand_cx - top_w / 2, badge_y + badge + 4),
        "WUALA",
        brand_font_top,
        pal["header_text"],
        spacing=4,
    )
    bot_w = _spaced_width(draw, "EXPRESS", brand_font_bot, 5)
    _draw_spaced(
        draw,
        (brand_cx - bot_w / 2, badge_y + badge + 4 + 20 + 2),
        "EXPRESS",
        brand_font_bot,
        pal["header_text"],
        spacing=5,
    )

    # eslogan + moto a la derecha
    slogan_font = font(27, True)
    slogan = "TU PEDIDO, NUESTRA RUTA"
    moto_w = 118
    moto_x = right - moto_w
    moto_y = (header_h - moto_w * 0.62) / 2 - 10
    _draw_moto(draw, moto_x, moto_y, moto_w, pal["header_text"])
    _draw_spaced(
        draw,
        (0, header_h / 2 - 20),
        slogan,
        slogan_font,
        pal["header_text"],
        spacing=3,
        right=moto_x - 40,
    )

    # ---- Cinta carmesí con el título --------------------------------------
    band_top = header_h
    band_bottom = header_h + band_h
    band = Image.new("RGBA", (width, band_h), pal["band"] + (255,))
    bd = ImageDraw.Draw(band)
    bd.rectangle((0, 0, width, 4), fill=pal["band_dark"] + (255,))
    bd.rectangle((0, band_h - 4, width, band_h), fill=pal["band_dark"] + (255,))
    # remates en ángulo a ambos lados
    bd.polygon([(0, 4), (92, 4), (30, band_h - 4), (0, band_h - 4)], fill=pal["band_dark"] + (255,))
    bd.polygon([(width, 4), (width - 92, 4), (width - 30, band_h - 4), (width, band_h - 4)], fill=pal["band_dark"] + (255,))
    for i in range(4):
        offset = 10 + i * 22
        color = (pal["band_line"] if i % 2 else pal["band_dark"]) + (110,)
        bd.line([(offset, band_h - 6), (offset + 66, 6)], fill=color, width=3)
        bd.line([(width - offset, band_h - 6), (width - offset - 66, 6)], fill=color, width=3)
    img.paste(band.convert("RGB"), (0, band_top))

    title = f"SALIDAS DESDE {strip_code(route.origin).upper()}"
    title_font = _fit_font(draw, title, inner - 140, 52, True, 26)
    _center(draw, (margin, band_top, right, band_bottom), title, title_font, pal["header_text"])

    # ---- Tabla -------------------------------------------------------------
    table_top = band_bottom + gap_band_table
    table_bottom = table_top + table_h
    body_top = table_top + head_h
    body_bottom = table_bottom - foot_h
    col_w = inner / cols

    draw.rounded_rectangle(
        (margin, table_top, right, table_bottom),
        radius=radius,
        fill=pal["row_a"],
        outline=pal["table_head"],
        width=2,
    )

    # filas zebra
    for r in range(rows):
        ry0 = body_top + r * row_h
        fill = pal["row_b"] if r % 2 else pal["row_a"]
        draw.rectangle((margin + 2, ry0, right - 2, ry0 + row_h), fill=fill)
        if r:
            draw.line([(margin + 2, ry0), (right - 2, ry0)], fill=pal["grid"], width=1)

    # cabecera de la tabla
    _round_top(draw, (margin, table_top, right, body_top), radius, pal["table_head"])
    head_font = font(dest_size + 2, True)
    for c in range(cols):
        cx0 = margin + c * col_w
        cx1 = cx0 + col_w
        _center(draw, (cx0, table_top, cx1 - 18, body_top), f"ZONA {c + 1}", head_font, pal["table_text"])
        # flecha desplegable
        ax = cx1 - 34
        ay = table_top + head_h / 2 - 4
        draw.polygon([(ax, ay), (ax + 16, ay), (ax + 8, ay + 9)], fill=pal["table_text"])
        if c:
            draw.line([(cx0, table_top + 2), (cx0, body_top)], fill=pal["table_divider"], width=1)

    # destinos
    dest_type = dest_font(dest_size)
    text_pad = 14 if col_w >= 310 else 10
    for c, (_value, indexes) in enumerate(groups):
        cx0 = margin + c * col_w
        cx1 = cx0 + col_w
        if c:
            draw.line([(cx0, body_top), (cx0, body_bottom)], fill=pal["grid"], width=1)
        for r, idx in enumerate(indexes):
            if r >= rows:
                break
            ry0 = body_top + r * row_h
            label = pretty(zone_label(route.destinations[idx]))
            lines = _wrap_lines(draw, label, dest_type, int(col_w - 2 * text_pad))
            line_h = dest_size + 6
            top_y = ry0 + (row_h - len(lines) * line_h) / 2
            for j, line in enumerate(lines):
                _center(
                    draw,
                    (cx0 + text_pad, top_y + j * line_h, cx1 - text_pad, top_y + (j + 1) * line_h),
                    line,
                    dest_type,
                    pal["cell_text"],
                )

    # franja de precios
    _round_bottom(draw, (margin, body_bottom, right, table_bottom), radius, pal["footer_bg"])
    for c, (value, _indexes) in enumerate(groups):
        cx0 = margin + c * col_w
        cx1 = cx0 + col_w
        text = price_label(value)
        size = 32
        fnt = font(size, True)
        while size > 20 and draw.textlength(text, font=fnt) > col_w - 28:
            size -= 2
            fnt = font(size, True)
        _center(draw, (cx0, body_bottom, cx1, table_bottom), text, fnt, pal["footer_text"])
        if c:
            draw.line([(cx0, body_bottom + 2), (cx0, table_bottom - 2)], fill=pal["table_divider"], width=1)

    # contorno exterior
    draw.rounded_rectangle((margin, table_top, right, table_bottom), radius=radius, outline=pal["table_head"], width=2)

    # ---- Pie ---------------------------------------------------------------
    draw.rectangle((0, height - strip_h, width, height), fill=pal["strip"])
    draw.line([(0, height - strip_h), (width, height - strip_h)], fill=pal["table_head"], width=1)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path
