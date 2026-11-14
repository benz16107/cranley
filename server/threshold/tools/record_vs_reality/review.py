"""Review pictures for the truth tools: a ToolResult's overlays drawn on the plan, with its evidence crops below.

    uv run python -m threshold.tools.record_vs_reality.review <tool> <sid> [<sid> ...] [--deep] [--inputs JSON]

Writes `<sid>.json` (the ToolResult) and `<sid>.png` under $THRESHOLD_DATA_DIR/shots/tools/<tool>/. Sponsor data:
never in the repo.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw, ImageFont

from ...config import DATA
from .. import ToolContext, run_tool

COLOR = {"pass": (46, 139, 87), "fail": (200, 40, 40), "warn": (230, 150, 20), "unknown": (130, 130, 130),
         "highlight": (240, 200, 40), "dim": (205, 205, 205), "solid": (90, 90, 160), "hide": (255, 255, 255)}
W, PAD, THUMB = 1100, 30, 260


def _font(size: int):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _ramp(t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return int(250 - 60 * t), int(240 - 120 * t), int(200 - 170 * t)


def draw_plan(plan: dict, result: dict) -> Image.Image:
    rooms = [r for r in plan["rooms"] if len(r.get("polygon") or []) >= 3]
    floors = [f["id"] for f in plan["floors"] if any(r["floor"] == f["id"] for r in rooms)] or [None]
    fill: dict[str, tuple] = {}
    for o in result.get("overlays") or []:
        if o["kind"] == "lens" and o["values"]:
            lo, hi = o["legend"]["min"], o["legend"]["max"]
            for rid, v in o["values"].items():
                fill[rid] = _ramp((v - lo) / (hi - lo) if hi > lo else 1)
    for o in result.get("overlays") or []:
        if o["kind"] == "rule" and "rooms" in o["select"]:
            for rid in o["select"]["rooms"]:
                fill[rid] = COLOR[o["style"]]
    pins = [p for o in result.get("overlays") or [] if o["kind"] == "pins" for p in o["pins"]]
    cell = (W - PAD * (len(floors) + 1)) // len(floors)
    tall = 0.2
    for fl in floors:  # the canvas is as tall as the tallest floor drawn at the shared scale
        pts = [p for r in rooms if fl is None or r["floor"] == fl for p in r["polygon"]]
        if pts:
            dx = max(p[0] for p in pts) - min(p[0] for p in pts)
            dy = max(p[1] for p in pts) - min(p[1] for p in pts)
            tall = max(tall, dy / max(dx, dy, 1e-6))
    img = Image.new("RGB", (W, int(cell * tall) + 2 * PAD + 30), "white")
    d = ImageDraw.Draw(img)
    f_small = _font(13)
    for i, fl in enumerate(floors):
        rs = [r for r in rooms if fl is None or r["floor"] == fl]
        if not rs:
            continue
        xs = [p[0] for r in rs for p in r["polygon"]]
        ys = [p[1] for r in rs for p in r["polygon"]]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        s = cell / span
        ox = PAD + i * (cell + PAD)

        def tx(p, s=s, ox=ox, xs=xs, ys=ys):
            return ox + (p[0] - min(xs)) * s, PAD + 30 + (max(ys) - p[1]) * s  # north (+y) up

        for r in rs:
            pts = [tx(p) for p in r["polygon"]]
            d.polygon(pts, fill=fill.get(r["id"], (245, 245, 245)), outline=(60, 60, 60))
        for o in plan.get("openings") or []:
            if o.get("floor") == (fl or o.get("floor")) and o["type"] == "window":
                x, y = tx(o["center"])
                d.rectangle([x - 4, y - 4, x + 4, y + 4], fill=(40, 120, 220))
        for r in rs:
            c = r.get("center") or [sum(p[0] for p in r["polygon"]) / len(r["polygon"]),
                                    sum(p[1] for p in r["polygon"]) / len(r["polygon"])]
            x, y = tx(c)
            d.text((x, y), (r.get("label") or "")[:12], fill=(20, 20, 20), font=f_small, anchor="mm")
        for p in pins:
            a = p["anchor"]
            r = next((r for r in rs if r["id"] == a.get("room")), None)
            if r is not None:
                c = r.get("center") or r["polygon"][0]
                x, y = tx(c)
                d.ellipse([x - 9, y + 8, x + 9, y + 26], fill=COLOR.get(p["status"], (0, 0, 0)), outline="white")
        d.text((ox, PAD), next((f["label"] for f in plan["floors"] if f["id"] == fl), "") or "", fill=(0, 0, 0), font=_font(15))
    return img


def _crop(m: dict) -> Image.Image | None:
    """The evidence image of one media item, with its box drawn."""
    try:
        if m["kind"] == "pano":
            from ...sources import matterport as mp
            sid, pano, face = m["ref"].split("/")
            im = Image.open(io.BytesIO(mp.pano_face(sid, pano, int(face), "2k"))).convert("RGB")
        elif m["kind"] == "ortho":
            from ...aerial import site
            q = {k: v[0] for k, v in parse_qs(urlparse(m["ref"]).query).items()}
            o = site.ortho(float(q["lat"]), float(q["lon"]), float(q["size_m"]), int(q["px"]))
            im = Image.open(io.BytesIO(o.image)).convert("RGB")
        else:
            return None
    except Exception:  # noqa: BLE001 - a missing crop must not stop the review
        return None
    if m.get("box"):
        x0, y0, x1, y1 = m["box"]
        ImageDraw.Draw(im).rectangle([x0 * im.width, y0 * im.height, x1 * im.width, y1 * im.height], outline=(255, 40, 40),
                                     width=max(3, im.width // 200))
    im.thumbnail((THUMB, THUMB))
    return im


def render(plan: dict, result: dict) -> Image.Image:
    top = draw_plan(plan, result)
    items = [(f, m) for f in result["findings"] for m in f.get("media") or []]
    seen, uniq = set(), []
    for f, m in items:
        k = (m["ref"], tuple(m.get("box") or ()))
        if k not in seen:
            seen.add(k)
            uniq.append((f, m))
    thumbs = [(f, im) for f, m in uniq[:8] if (im := _crop(m)) is not None]
    lines = [result["verdict"]["text"]] + [f"[{f['status']}] {f['title']}" for f in result["findings"][:22]]
    f_txt = _font(15)
    text_h = 22 * len(lines) + PAD
    rows = (len(thumbs) + 3) // 4
    img = Image.new("RGB", (W, top.height + text_h + rows * (THUMB + 40) + PAD), "white")
    img.paste(top, (0, 0))
    d = ImageDraw.Draw(img)
    y = top.height
    for i, ln in enumerate(lines):
        d.text((PAD, y + 22 * i), ln[:150], fill=(0, 0, 0) if i else (0, 0, 120), font=f_txt)
    y += text_h
    for i, (f, im) in enumerate(thumbs):
        x, yy = PAD + (i % 4) * (THUMB + 10), y + (i // 4) * (THUMB + 40)
        img.paste(im, (x, yy))
        d.text((x, yy + im.height + 4), f["title"][:34], fill=COLOR.get(f["status"], (0, 0, 0)), font=_font(13))
    return img


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tool")
    ap.add_argument("sids", nargs="+")
    ap.add_argument("--deep", action="store_true")
    ap.add_argument("--inputs", default="{}")
    a = ap.parse_args(argv)
    out = DATA / "shots" / "tools" / a.tool
    out.mkdir(parents=True, exist_ok=True)
    ctx = ToolContext()
    for sid in a.sids:
        inputs = {"scan": sid, **json.loads(a.inputs)}
        if a.deep:
            inputs["deep" if a.tool != "derived_fields" else "vision"] = True
        try:
            r = run_tool(a.tool, inputs, ctx)
        except Exception as e:  # noqa: BLE001 - report and carry on with the next scan
            print(f"{sid}: {e}", file=sys.stderr)
            continue
        js = json.loads(r.model_dump_json())
        (out / f"{sid}.json").write_text(json.dumps(js, indent=1))
        render(ctx.plan(sid), js).save(out / f"{sid}.png")
        print(f"{sid}: {r.verdict.status}: {r.verdict.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
