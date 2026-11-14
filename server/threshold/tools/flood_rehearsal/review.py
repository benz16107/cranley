"""Run the three flood tools on real scans and save results and pictures for review (outside the repo).

    uv run python -m threshold.tools.flood_rehearsal.review SID [SID ...] [--depth 0.6]

Writes `$THRESHOLD_DATA_DIR/shots/tools/<tool>/<sid>.json` and `.png`, `floor_height_<sid>.png`, and prints
the floor-height agreement table."""
from __future__ import annotations

import argparse
import io
import json
import math
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from PIL import Image
from shapely.geometry import shape

from ...config import DATA
from ...geometry._plan import polygons
from .. import ToolContext, run_tool

OUT = DATA / "shots" / "tools"
STATUS = {"pass": "#3b7d4f", "warn": "#d08a1e", "fail": "#b3362c", "unknown": "#777777"}


def draw_plan(ax, plan, floor=None, lens=None, vmax=1.0):
    polys = polygons(plan)
    floors = sorted({r["floor"] for r in plan["rooms"]}, key=lambda f: next(
        (x.get("sequence", 0) for x in plan["floors"] if x["id"] == f), 0))
    floor = floor or (floors[0] if floors else None)
    cmap = plt.get_cmap("Blues")
    for r in plan["rooms"]:
        p = polys.get(r["id"])
        if p is None or r["floor"] != floor:
            continue
        v = (lens or {}).get(r["id"], 0)
        ax.add_patch(MplPolygon(list(p.exterior.coords), closed=True, fc=cmap(0.15 + 0.85 * min(v / vmax, 1)) if v > 0
                                else "#f4f1ea", ec="#bbb", lw=0.5))
        c = p.representative_point()
        ax.text(c.x, c.y, (r.get("label") or "?") + (f"\n{v:.2f} m" if v > 0 else ""), ha="center", va="center", fontsize=6)
    for w in plan.get("walls") or []:
        if w["floor"] == floor and w.get("type") != "invisible":
            ax.plot([w["a"][0], w["b"][0]], [w["a"][1], w["b"][1]], color="#333", lw=1.2)
    ax.set_aspect("equal")
    ax.axis("off")
    return floor


def opening_xy(plan, oid):
    o = next((o for o in plan.get("openings") or [] if o["id"] == oid), None)
    return (o["center"], o["floor"]) if o else (None, None)


def render_flood(plan, r, path):
    lens = next((o for o in r.overlays if o.kind == "lens"), None)
    floors = [f["id"] for f in sorted(plan["floors"], key=lambda f: f.get("sequence", 0))]
    fig, axes = plt.subplots(1, len(floors[:2]), figsize=(7 * len(floors[:2]), 6), squeeze=False)
    for ax, fl in zip(axes[0], floors[:2]):
        draw_plan(ax, plan, fl, lens.values if lens else None, max(lens.legend.max, 0.05) if lens else 1)
        for o in r.overlays:
            if o.kind == "rule" and hasattr(o.select, "openings"):
                for oid in o.select.openings:
                    (c, f) = opening_xy(plan, oid)
                    if c and f == fl:
                        ax.plot(*c, "s", color=STATUS.get(o.style, "#000"), ms=6)
            if o.kind == "pins":
                polys = polygons(plan)
                for p in o.pins:
                    rid = getattr(p.anchor, "room", None)
                    poly = polys.get(rid) if rid else None
                    if poly is not None and next(x["floor"] for x in plan["rooms"] if x["id"] == rid) == fl:
                        c = poly.representative_point()
                        ax.annotate(p.label, (c.x, c.y), xytext=(0, 12), textcoords="offset points", ha="center",
                                    fontsize=8, color="white", bbox={"boxstyle": "circle", "fc": STATUS[p.status], "ec": "none"})
        ax.set_title(next(f.get("label") or f["id"] for f in plan["floors"] if f["id"] == fl), fontsize=9)
    fig.suptitle(wrap(r.verdict.text, 120), fontsize=9)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def wrap(t, n):
    words, lines, cur = t.split(), [], ""
    for w in words:
        if len(cur) + len(w) > n:
            lines.append(cur)
            cur = ""
        cur += w + " "
    return "\n".join(lines + [cur])


def render_items(plan, r, path):
    fig, ax = plt.subplots(figsize=(8, 7))
    fl = draw_plan(ax, plan)
    pins = next((o for o in r.overlays if o.kind == "pins"), None)
    for p in pins.pins if pins else []:
        if hasattr(p.anchor, "point") and not p.id.endswith(":pano"):
            x, y, _ = p.anchor.point
            ax.plot(x, y, "o", color=STATUS[p.status], ms=5, mec="white", mew=0.5)
            if p.status == "fail" and p.id.startswith("util"):
                ax.annotate(p.label, (x, y), xytext=(3, 3), textcoords="offset points", fontsize=6)
    ax.set_title(f"{plan['name']}: items (red under water at the middle estimate, amber only at the high end)", fontsize=9)
    fig.suptitle(wrap(r.verdict.text, 110), fontsize=8)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return fl


def render_plan(plan, r, path):
    from ...aerial import site as aerial
    from ..storm_plan import prep
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 7))
    draw_plan(a1, plan)
    for o in r.overlays:
        if o.kind == "rule" and hasattr(o.select, "openings"):
            for oid in o.select.openings:
                c, _ = opening_xy(plan, oid)
                if c:
                    a1.plot(*c, "s" if o.style == "highlight" else "D", color="#2a5db0" if o.style == "highlight" else "#d08a1e", ms=7)
        if o.kind == "pins":
            for p in o.pins:
                if hasattr(p.anchor, "point") and p.label.isdigit() and int(p.label) <= 15:
                    x, y, _ = p.anchor.point
                    a1.annotate(p.label, (x, y), fontsize=7, color="white", ha="center",
                                bbox={"boxstyle": "circle", "fc": "#b3362c", "ec": "none"})
    a1.set_title("Blue squares: windows to board. Amber diamonds: doors to sandbag. Numbers: carry order", fontsize=8)
    gen = next((f for f in r.findings if f.id.endswith(":generator")), None)
    lat, lon = plan["geo"]["lat"], plan["geo"]["lon"]
    try:
        from ..flood_rehearsal.scenario import _site
        s = _site(lat, lon)
        o = aerial.ortho(s["lat"], s["lon"], size_m=60, px=1024)
        a2.imshow(Image.open(io.BytesIO(o.image)))
        z = prep.generator_zone(s["footprint"], s.get("parcel"), s["lat"], s["lon"])

        def px(geom, **kw):
            for g in getattr(geom, "geoms", [geom]):
                xy = [o.to_px(x, y) for x, y in g.exterior.coords]
                a2.add_patch(MplPolygon(xy, closed=True, **kw))
        px(shape(z["house"]), fc="none", ec="white", lw=1.5)
        px(shape(z["lot"]), fc="none", ec="yellow", lw=1, ls="--")
        if z.get("zone"):
            px(shape(z["zone"]), fc=(0.2, 0.8, 0.3, 0.35), ec="#3b7d4f", lw=1)
            sx, sy = o.to_px(*z["spot"])
            a2.plot(sx, sy, "*", ms=16, color="#ffdd00", mec="black")
        a2.set_title("Green: 20 ft (6.1 m) or more from every wall, inside the lot. Star: nearest spot", fontsize=8)
    except Exception as e:  # noqa: BLE001
        a2.text(0.5, 0.5, f"no aerial: {e}", ha="center", transform=a2.transAxes)
    a2.axis("off")
    fig.suptitle(wrap(r.verdict.text, 150) + ("\n" + wrap(gen.detail[:200], 150) if gen else ""), fontsize=8)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def render_floor_height(plan, flood_result, path):
    """The floor-height reasoning: estimates as ground levels below the floor, with their errors and the range."""
    from .scenario import FloodInputs
    from .scenario import run as flood_run
    fl = flood_run(plan, FloodInputs(scan=plan["sid"], depth_m=0.6), lambda s: None)["floor"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [1.3, 1]})
    a1.axhline(0, color="#333", lw=2)
    a1.text(0.2, 0.02, "finished floor (threshold)", fontsize=8)
    a1.axhspan(-fl["hi_m"], -fl["lo_m"], color="#d08a1e", alpha=0.18, label="ground: range carried through")
    a1.axhline(-fl["value_m"], color="#d08a1e", lw=2, label=f"ground used: {fl['value_m']:.2f} m below the floor")
    xs = []
    for i, e in enumerate(fl["estimates"]):
        x = 1 + i
        xs.append(x)
        a1.errorbar(x, -e["value_m"], yerr=e["err_m"], fmt="o", capsize=5, color=STATUS["pass" if e["confidence"] == "high"
                                                                                      else "warn" if e["confidence"] == "medium" else "unknown"])
        a1.text(x, -e["value_m"] - e["err_m"] - 0.05, f"{e['method']}\n{e['value_m']:.2f} m ({e['confidence']})",
                ha="center", va="top", fontsize=7)
    if fl.get("bound"):
        a1.axhline(-fl["bound"]["value_m"], color="#555", ls=":", lw=1)
        a1.text(len(xs) + 1.2, -fl["bound"]["value_m"], f"door step {fl['bound']['value_m']:.2f} m: the ground is at or below",
                fontsize=7, va="bottom", ha="right")
    a1.set_xlim(0.3, len(xs) + 1.5)
    a1.set_ylim(-max(0.8, fl["hi_m"] + 0.4), 0.15)
    a1.set_ylabel("height relative to the floor (m)")
    a1.set_xticks([])
    a1.legend(loc="lower right", fontsize=7)
    a1.set_title(f"{plan['name']}: floor {fl['value_m']:.2f} m above the ground ({fl['lo_m']:.2f} to {fl['hi_m']:.2f}), "
                 f"from {fl['method']}", fontsize=9)
    # Right: the drone crop with the model's lines, or the Vexcel ground ring
    drone = (fl.get("traces") or {}).get("drone") or {}
    shot = next((t for t in drone.get("tried", []) if t.get("ffh_m") is not None), None)
    if shot:
        from ...sources import hackathon
        im = Image.open(io.BytesIO(hackathon.drone_image(plan["sid"], shot["photo"], 4000)))
        x0, y0, x1, y1 = shot["crop"]
        a2.imshow(im.crop((x0, y0, x1, y1)))
        a2.set_title(f"Drone {shot['photo'][-12:]}: {shot['ffh_m']:.2f} m threshold over ground at "
                     f"{shot['distance_m']:.1f} m (laser check {shot['laser_check_m']:+.2f} m)", fontsize=8)
    elif fl.get("grade"):
        z = [p["z"] for p in fl["grade"]["points"]]
        a2.plot(range(len(z)), [v - min(z) for v in z])
        a2.set_title("Vexcel bare ground 3 m around the house (relative)", fontsize=8)
    a2.axis("off")
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return fl


def dump(r, path):
    path.write_text(json.dumps(r.model_dump(), indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("sids", nargs="+")
    ap.add_argument("--depth", type=float, default=0.6)
    ap.add_argument("--tools", default="flood_rehearsal,valuables_height,storm_plan")
    a = ap.parse_args(argv)
    from ...sources import matterport as mp
    tools = a.tools.split(",")
    for t in tools:
        (OUT / t).mkdir(parents=True, exist_ok=True)
    table = []
    for sid in a.sids:
        plan = mp.plan(sid)
        print(f"== {sid} {plan['name']}", flush=True)
        ctx = ToolContext(plans=mp.plan, on_step=lambda s: print("   ", s, flush=True))
        base = {"scan": sid, "depth_m": a.depth}
        if "flood_rehearsal" in tools:
            r = run_tool("flood_rehearsal", base, ctx)
            dump(r, OUT / "flood_rehearsal" / f"{sid}.json")
            render_flood(plan, r, OUT / "flood_rehearsal" / f"{sid}.png")
            print("  ", r.verdict.status, r.verdict.text, flush=True)
            if plan.get("walls"):
                fl = render_floor_height(plan, r, OUT / "flood_rehearsal" / f"floor_height_{sid}.png")
                table.append({"sid": sid, "name": plan["name"], **{e["method"]: e["value_m"] for e in fl["estimates"]},
                              "bound": (fl.get("bound") or {}).get("value_m"), "used": fl["method"],
                              "range": (fl["lo_m"], fl["hi_m"])})
        if "valuables_height" in tools and plan.get("panos"):
            r = run_tool("valuables_height", base, ctx)
            dump(r, OUT / "valuables_height" / f"{sid}.json")
            render_items(plan, r, OUT / "valuables_height" / f"{sid}.png")
            print("  ", r.verdict.status, r.verdict.text, flush=True)
        if "storm_plan" in tools:
            r = run_tool("storm_plan", {**base, "hours_left": 72, "adults": 2}, ctx)
            dump(r, OUT / "storm_plan" / f"{sid}.json")
            render_plan(plan, r, OUT / "storm_plan" / f"{sid}.png")
            print("  ", r.verdict.status, r.verdict.text, flush=True)
            r2 = run_tool("storm_plan", {**base, "depth_m": a.depth + 0.4, "hours_left": 6, "adults": 1}, ctx)
            dump(r2, OUT / "storm_plan" / f"{sid}_changed.json")
            print("   changed:", r2.verdict.text, flush=True)
    if table:
        (OUT / "flood_rehearsal" / "floor_height_agreement.json").write_text(json.dumps(table, indent=1))
        print(agreement(table))


def agreement(table):
    pairs = [("drone_pixels", "scan_outdoor"), ("drone_pixels", "drone_laser_ground"), ("drone_pixels", "vexcel_eave"),
             ("scan_outdoor", "vexcel_eave")]
    lines = ["sid          " + "  ".join(f"{m[:12]:>12}" for m in ("drone_pixels", "drone_laser_ground", "scan_outdoor",
                                                                     "vexcel_eave", "bound"))]
    for t in table:
        lines.append(f"{t['sid']}  " + "  ".join(f"{t.get(m) if t.get(m) is not None else '-':>12}" for m in
                                                ("drone_pixels", "drone_laser_ground", "scan_outdoor", "vexcel_eave", "bound")))
    for a, b in pairs:
        d = [t[a] - t[b] for t in table if t.get(a) is not None and t.get(b) is not None]
        if d:
            lines.append(f"{a} - {b}: n={len(d)}, mean {statistics.fmean(d):+.3f} m, mean |diff| "
                         f"{statistics.fmean(abs(x) for x in d):.3f} m, max |diff| {max(abs(x) for x in d):.3f} m, "
                         f"rms {math.sqrt(statistics.fmean(x * x for x in d)):.3f} m")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
