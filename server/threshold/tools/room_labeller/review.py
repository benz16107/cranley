"""Review artifacts for the office tools: one example ToolResult per tool as JSON and a picture of its overlays on
the plan. Written under $THRESHOLD_DATA_DIR/shots/tools/<id>/ (derived from sponsor data, never in git).

    uv run python -m threshold.tools.room_labeller.review
"""
from __future__ import annotations

import json

from PIL import Image, ImageDraw, ImageFont

from ...config import DATA
from ...sources import matterport
from ..registry import ToolContext, run_tool
from . import store

OUT = DATA / "shots" / "tools"
# [[tool id, inputs]]; the scans and properties are sponsor data, so the list lives in the data folder
EXAMPLES = [tuple(e) for e in json.loads((DATA / "fixtures" / "office_review_examples.json").read_text())]
STATUS = {"pass": (46, 139, 87), "warn": (230, 159, 0), "fail": (200, 40, 40), "unknown": (120, 120, 120)}


def ramp(t: float) -> tuple[int, int, int]:
    """Light to dark teal."""
    t = max(0.0, min(1.0, t))
    a, b = (225, 240, 236), (16, 96, 104)
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw(plan: dict, overlays: list[dict], title: str, px: int = 1400) -> Image.Image:
    rooms = [r for r in plan["rooms"] if r.get("label") != "Void"]
    pts = [p for r in rooms for p in r.get("polygon") or []] or [r["center"] for r in rooms if r.get("center")]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1)
    s = (px - 120) / span
    W, H = round((max(xs) - min(xs)) * s) + 120, round((max(ys) - min(ys)) * s) + 160
    tx = lambda p: (60 + (p[0] - min(xs)) * s, H - 60 - (p[1] - min(ys)) * s)  # noqa: E731
    im = Image.new("RGB", (W, H), (250, 250, 248))
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=14)
    lens = next((o for o in overlays if o["kind"] == "lens"), None)
    rule = {rid: o["style"] for o in overlays if o["kind"] == "rule" and "rooms" in o["select"] for rid in o["select"]["rooms"]}
    for r in sorted(rooms, key=lambda r: -(r.get("area") or 0)):
        poly = [tx(p) for p in r.get("polygon") or []]
        if len(poly) < 3:
            continue
        fill = (238, 238, 236)
        if lens and r["id"] in lens["values"]:
            lo, hi = lens["legend"]["min"], lens["legend"]["max"]
            fill = ramp((lens["values"][r["id"]] - lo) / ((hi - lo) or 1))
        if rule.get(r["id"]) == "dim":
            fill = (245, 245, 245)
        d.polygon(poly, fill=fill, outline=STATUS["warn"] if rule.get(r["id"]) == "warn" else (90, 90, 90),
                  width=4 if rule.get(r["id"]) in ("warn", "highlight") else 1)
    by_id = {r["id"]: r for r in plan["rooms"]}
    for o in overlays:
        if o["kind"] != "pins":
            continue
        for p in o["pins"]:
            room = by_id.get(p["anchor"].get("room")) if p["anchor"].get("sid") == plan["sid"] else None
            c = room and (room.get("center") or (room.get("polygon") or [None])[0])
            if not c:
                continue
            x, y = tx(c)
            d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=STATUS[p["status"]])
            d.text((x + 7, y - 7), p["label"][:28], fill=(30, 30, 30), font=font)
    d.text((20, 15), title, fill=(20, 20, 20), font=ImageFont.load_default(size=20))
    if lens:
        lg = lens["legend"]
        for i in range(200):
            d.line([(20 + i, 50), (20 + i, 64)], fill=ramp(i / 199))
        d.text((230, 48), f"{lg['title']}: {lg['min']:g} to {lg['max']:g} {lg['unit']}", fill=(40, 40, 40), font=font)
    return im


def main() -> None:
    for tool_id, inputs in EXAMPLES:
        r = run_tool(tool_id, inputs, ToolContext()).model_dump()
        d = OUT / tool_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "example_result.json").write_text(json.dumps({"inputs": inputs, "result": r}, indent=1))
        sids = [inputs["scan"]] if inputs.get("scan") else r["scope"].get("sids", [])
        for sid in sids[:3]:
            plan = store.apply(matterport.plan(sid))  # the fixture copies predate room centres
            if not any(x.get("polygon") for x in plan["rooms"]):
                continue
            mine = [o for o in r["overlays"] if o["kind"] != "pins" or any(p["anchor"].get("sid") == sid for p in o["pins"])]
            draw(plan, mine, f"{tool_id}: {plan['name'][:60]}").save(d / f"overlays_{sid}.png")
        print(tool_id, r["verdict"]["status"], r["verdict"]["text"][:120])


if __name__ == "__main__":
    main()
