"""Review pictures for the site tools: run a tool, save its ToolResult as JSON and the orthophoto with the result's map
overlays drawn on it, under $THRESHOLD_DATA_DIR/shots/tools/<tool>/ (sponsor imagery: never the repo).

    cd server && uv run python -m threshold.tools._site.shots roof_facts '{"lat": 29.8, "lon": -95.4}' [name]
"""
from __future__ import annotations

import io
import json
import math
import sys

from PIL import Image, ImageDraw, ImageFont
from shapely import wkt as shapely_wkt
from shapely.geometry import shape

from ...aerial import site as aerial
from ...config import DATA
from .. import run_tool

COLORS = {"pass": (46, 160, 67), "warn": (230, 160, 20), "fail": (215, 45, 45), "unknown": (120, 140, 160)}


def _font(px: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", px)
    except OSError:
        return ImageFont.load_default()


def render(result: dict, lat: float, lon: float, size_m: float, extra: dict | None = None, px: int = 1400) -> bytes:
    """The orthophoto around (lat, lon) with the result's geo pins and geo routes, plus `extra` shapes
    ({"footprint": wkt, "parcel": geojson, "polygons": [(lonlat ring, status)], "lines": [(lonlat pts, status)]})."""
    o = aerial.ortho(lat, lon, size_m, min(px, 2048))
    im = Image.open(io.BytesIO(o.image)).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    f = _font(max(14, im.width // 70))
    P = lambda lo, la: o.to_px(lo, la)
    extra = extra or {}
    if extra.get("parcel"):
        g = shape(extra["parcel"])
        for poly in getattr(g, "geoms", [g]):
            d.line([P(*c) for c in poly.exterior.coords], fill=(255, 255, 255, 200), width=2)
    if extra.get("footprint"):
        g = shapely_wkt.loads(extra["footprint"])
        for poly in getattr(g, "geoms", [g]):
            d.line([P(*c) for c in poly.exterior.coords], fill=(80, 200, 255, 230), width=3)
    for ring, st in extra.get("polygons") or []:
        d.polygon([P(*c) for c in ring], outline=COLORS[st] + (255,), fill=COLORS[st] + (50,))
    for pts, st in extra.get("lines") or []:
        d.line([P(*c) for c in pts], fill=COLORS[st] + (220,), width=3)
    for ov in result.get("overlays") or []:
        if ov["kind"] == "route" and ov["floor"] == "geo":
            pts = [P(x, y) for x, y, _ in ov["points"]]
            d.line(pts, fill=(255, 255, 255, 255), width=9, joint="curve")
            d.line(pts, fill=(30, 110, 255, 255), width=5, joint="curve")
            if len(pts) > 1:
                (x0, y0), (x1, y1) = pts[-2], pts[-1]
                a = math.atan2(y1 - y0, x1 - x0)
                d.polygon([(x1, y1), (x1 - 22 * math.cos(a - 0.45), y1 - 22 * math.sin(a - 0.45)),
                           (x1 - 22 * math.cos(a + 0.45), y1 - 22 * math.sin(a + 0.45))], fill=(30, 110, 255, 255))
            for ch in ov.get("chokes") or []:
                x, y = P(ch["point"][0], ch["point"][1])
                d.ellipse([x - 12, y - 12, x + 12, y + 12], outline=COLORS[ch["status"]] + (255,), width=4)
        if ov["kind"] == "pins":
            for p in ov["pins"]:
                g = (p.get("anchor") or {}).get("geo")
                if not g:
                    continue
                x, y = P(*g)
                c = COLORS.get(p["status"], COLORS["unknown"])
                d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=c + (255,), outline=(255, 255, 255, 255), width=2)
                if p.get("label"):
                    d.text((x + 10, y - 8), p["label"], fill=(255, 255, 255, 255), font=f, stroke_width=3,
                           stroke_fill=(0, 0, 0, 255))
    v = result.get("verdict") or {}
    head = f"{result.get('tool')}: {v.get('status', '').upper()}"
    d.rectangle([0, 0, im.width, 34 + 0], fill=(0, 0, 0, 170))
    d.text((10, 7), head + "  " + (v.get("text") or "")[:150], fill=(255, 255, 255, 255), font=_font(max(13, im.width // 95)))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def shoot(tool_id: str, inputs: dict, name: str, size_m: float | None = None, extra_fn=None) -> tuple[dict, str]:
    from ..registry import ToolContext
    from . import Where, facts, locate
    r = run_tool(tool_id, inputs).model_dump(mode="json", exclude_none=True)
    s = locate(ToolContext(), Where(**{k: inputs.get(k) for k in ("scan", "property_id", "lat", "lon")}))
    fx = facts(s)
    fp = fx.get("footprint")
    c = shapely_wkt.loads(fp).centroid if fp else None
    lat, lon = (c.y, c.x) if c else (s.lat, s.lon)
    if size_m is None:
        geos = [p["anchor"]["geo"] for ov in r.get("overlays") or [] if ov["kind"] == "pins" for p in ov["pins"]
                if "geo" in p["anchor"]]
        geos += [(x, y) for ov in r.get("overlays") or [] if ov["kind"] == "route" and ov["floor"] == "geo" for x, y, _ in ov["points"]]
        span = max([abs(g[0] - lon) * 111320 * math.cos(math.radians(lat)) for g in geos] +
                   [abs(g[1] - lat) * 110574 for g in geos] + [40])
        size_m = min(500, 2 * span + 30)
    extra = {"footprint": fp, "parcel": fx.get("parcel")}
    if extra_fn:
        extra.update(extra_fn(s) or {})
    out = DATA / "shots" / "tools" / tool_id
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(r, indent=1))
    png = out / f"{name}.png"
    png.write_bytes(render(r, lat, lon, size_m, extra))
    return r, str(png)


if __name__ == "__main__":
    r, p = shoot(sys.argv[1], json.loads(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "example")
    print(r["verdict"])
    print(p)
