"""Review pictures: a tool result's overlays drawn on the scan's plan, and the example JSON beside them.

    save_example(tool_id, plan, result)  ->  $THRESHOLD_DATA_DIR/shots/tools/<id>/<sid>.json and .png

Pillow only (already a dependency). Not used by the tools themselves; the web draws overlays for people.
"""
from __future__ import annotations

import json
import math

from PIL import Image, ImageDraw, ImageFont

from ...config import DATA
from ...geometry._plan import polygons

COL = {"pass": (46, 139, 87), "warn": (222, 150, 20), "fail": (200, 40, 40), "unknown": (120, 120, 120)}
W = 1400
PAD = 60


def _font(size: int):
    for f in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _floor_of(plan: dict, result: dict) -> str | None:
    for o in result.get("overlays") or []:
        if o.get("kind") == "route":
            return o["floor"]
    floors = plan.get("floors") or []
    return floors[0]["id"] if floors else None


def render(plan: dict, result: dict, floor: str | None = None) -> Image.Image:
    floor = floor or _floor_of(plan, result)
    polys = polygons(plan)
    rooms = [r for r in plan.get("rooms") or [] if r["floor"] == floor]
    walls = [w for w in plan.get("walls") or [] if w["floor"] == floor]
    pts = [p for w in walls for p in (w["a"], w["b"])] + \
          [c for r in rooms if polys.get(r["id"]) is not None for c in polys[r["id"]].exterior.coords]
    if not pts:
        pts = [p["position"][:2] for p in plan.get("panos") or [] if p.get("floor") == floor] or [(0, 0), (1, 1)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = (W - 2 * PAD) / max(x1 - x0, y1 - y0, 1)
    H = int((y1 - y0) * s + 2 * PAD + 120)
    img = Image.new("RGB", (W, H), (250, 248, 244))
    d = ImageDraw.Draw(img)

    def P(x, y):
        return (PAD + (x - x0) * s, H - 120 - PAD - (y - y0) * s + 0)

    lens = next((o for o in result.get("overlays") or [] if o.get("kind") == "lens"), None)
    rule_room = {}
    for o in result.get("overlays") or []:
        if o.get("kind") == "rule" and "rooms" in o.get("select", {}):
            for r in o["select"]["rooms"]:
                rule_room[r] = o["style"]
    for r in rooms:
        poly = polys.get(r["id"])
        if poly is None:
            continue
        fill = (236, 233, 226)
        if lens and r["id"] in lens["values"]:
            v, lg = lens["values"][r["id"]], lens["legend"]
            if lens["ramp"] == "status":
                fill = {1: (198, 230, 205), 0.5: (250, 225, 170), 0: (245, 195, 195)}.get(v, fill)
            else:
                t = (v - lg["min"]) / ((lg["max"] - lg["min"]) or 1)
                fill = (int(240 - 120 * t), int(240 - 60 * t), int(235 - 20 * t))
        if r["id"] in rule_room:
            fill = {"pass": (198, 230, 205), "warn": (250, 225, 170), "fail": (245, 195, 195),
                    "highlight": (210, 220, 245)}.get(rule_room[r["id"]], fill)
        d.polygon([P(*c) for c in poly.exterior.coords], fill=fill, outline=(200, 196, 188))
        c = poly.representative_point()
        d.text(P(c.x, c.y), (r.get("label") or "?")[:14], fill=(90, 90, 90), font=_font(15), anchor="mm")
    for w in walls:
        if w.get("type") != "invisible":
            d.line([P(*w["a"]), P(*w["b"])], fill=(40, 40, 40), width=max(2, int((w.get("thickness") or 0.1) * s * 0.6)))
    for o in plan.get("openings") or []:
        if o["floor"] != floor:
            continue
        wall = next((w for w in walls if w["id"] == o["wall"]), None)
        if not wall:
            continue
        (ax, ay), (bx, by) = wall["a"], wall["b"]
        L = math.hypot(bx - ax, by - ay) or 1
        ux, uy = (bx - ax) / L, (by - ay) / L
        h = (o.get("width") or 0) / 2
        cx, cy = o["center"]
        col = (120, 170, 230) if o["type"] == "window" else (250, 248, 244)
        d.line([P(cx - ux * h, cy - uy * h), P(cx + ux * h, cy + uy * h)], fill=col, width=6)
    for o in result.get("overlays") or []:
        if o.get("kind") == "route" and o["floor"] == floor:
            d.line([P(*p[:2]) for p in o["points"]], fill=(40, 90, 200), width=5)
            for c in o.get("chokes") or []:
                x, y = P(*c["point"][:2])
                d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=COL[c["status"]], outline=(255, 255, 255), width=2)
        if o.get("kind") == "box":
            cx, cy = o["center"][:2]
            w_, dp = o["size"][0] / 2, o["size"][1] / 2
            a = math.radians(o.get("yaw_deg") or 0)
            cs = [(cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a))
                  for px, py in ((-w_, -dp), (w_, -dp), (w_, dp), (-w_, dp))]
            d.polygon([P(*c) for c in cs], outline=COL[o["status"]], width=4)
            d.text(P(cx, cy), o["label"][:30], fill=COL[o["status"]], font=_font(14), anchor="mm")
        if o.get("kind") == "pins":
            for pin in o["pins"]:
                xy = _anchor_xy(plan, pin["anchor"], floor)
                if xy is None:
                    continue
                x, y = P(*xy)
                d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=COL[pin["status"]])
                d.text((x + 10, y - 8), pin["label"][:28], fill=(30, 30, 30), font=_font(13))
    v = result.get("verdict") or {}
    d.rectangle([0, H - 110, W, H], fill=(255, 255, 255))
    d.text((PAD, H - 98), f"{result.get('tool')}  ·  {plan.get('name', '')[:50]}  ·  {plan['sid']}", fill=(60, 60, 60),
           font=_font(18))
    d.text((PAD, H - 66), f"[{v.get('status')}] {v.get('text', '')}"[:150], fill=COL.get(v.get("status"), (0, 0, 0)),
           font=_font(18))
    return img


def _anchor_xy(plan: dict, a: dict, floor: str):
    if "point" in a:
        return a["point"][:2]
    if "opening" in a:
        o = next((o for o in plan.get("openings") or [] if o["id"] == a["opening"]), None)
        return o["center"] if o and o["floor"] == floor else None
    if "room" in a:
        p = polygons(plan).get(a["room"])
        r = next((r for r in plan["rooms"] if r["id"] == a["room"]), None)
        if p is not None and r and r["floor"] == floor:
            c = p.representative_point()
            return (c.x, c.y)
    return None


def save_example(tool_id: str, plan: dict, result, name: str | None = None) -> str:
    out = DATA / "shots" / "tools" / tool_id
    out.mkdir(parents=True, exist_ok=True)
    r = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    stem = name or plan["sid"]
    (out / f"{stem}.json").write_text(json.dumps(r, indent=1))
    render(plan, r).save(out / f"{stem}.png")
    return str(out / f"{stem}.png")
