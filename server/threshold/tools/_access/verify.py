"""Run every access tool on real scans and save review material. Needs the data folder and network for scans,
panoramas and the aerial photo the first time; everything is cached after that.

    uv run python -m threshold.tools._access.verify

Writes $THRESHOLD_DATA_DIR/shots/tools/<id>/<sid>.json and .png (one example per tool, plus the rest of the run)
and shots/tools/verify.md, a table of every tool on every scan.
"""
from __future__ import annotations

import io
import json
import time

from PIL import Image, ImageDraw

from ...config import DATA
from ...sources.index import rows
from .. import ToolContext, run_tool
from .draw import COL, _font, save_example

# Which real scans to run, and why, is sponsor data: it lives in the data folder, never in git.
# {"scans": {sid: why}, "vision": [sid], "examples": {tool id: sid}}
_PICK = json.loads((DATA / "fixtures" / "verify_access.json").read_text())
SCANS: dict[str, str] = _PICK["scans"]
VISION = set(_PICK["vision"])
EXTRA = {"furniture_fit": {"object": "refrigerator"}}
TOOLS = {t: (EXTRA.get(t, {}), sid) for t, sid in _PICK["examples"].items()}  # id: (extra inputs, the example scan)
PANO_TOOLS = {"step_free_route", "bathroom_clearance", "stairs_count", "aging_in_place", "curb_to_door"}
SEARCHES = {
    "wheelchair_one_floor": [{"measure": "bath_route_door", "op": ">=", "value": 0.81},
                             {"measure": "bed_wall", "op": ">=", "value": 2.2}, {"measure": "floors", "op": "==", "value": 1}],
    "wheelchair_bathroom": [{"measure": "wheelchair_bath", "op": "==", "value": 1},
                            {"measure": "bath_turn", "op": ">=", "value": 1.525}],
    "piano_and_tall_ceiling": [{"measure": "living_wall", "op": ">=", "value": 3.0},
                               {"measure": "ceiling_median", "op": ">=", "value": 2.9},
                               {"measure": "entrance_width", "op": ">=", "value": 0.85}],
}
OUT = DATA / "shots" / "tools"


def curb_picture(result, sid: str) -> None:
    """The aerial photo with the curb_to_door pins on it."""
    from ...aerial import site
    from ...tools.registry import default_plan
    g = default_plan(sid)["geo"]
    o = site.ortho(g["lat"], g["lon"], 80, 1024)
    im = Image.open(io.BytesIO(o.image)).convert("RGB")
    d = ImageDraw.Draw(im)
    for ov in result.overlays:
        for p in getattr(ov, "pins", []):
            if hasattr(p.anchor, "geo"):
                x, y = o.to_px(*p.anchor.geo)
                d.ellipse([x - 9, y - 9, x + 9, y + 9], outline=COL[p.status], width=4)
                d.text((x + 12, y - 8), p.label, fill=(255, 255, 255), font=_font(16))
    d.text((12, 12), result.verdict.text[:110], fill=(255, 255, 255), font=_font(16))
    im.save(OUT / "curb_to_door" / f"{sid}_aerial.jpg", quality=85)


def search_picture(result, name: str) -> None:
    """Every scan in the table as a dot, the matches in colour (Houston and Los Angeles side by side)."""
    from ..measure_search import table
    pts = [(r["lon"], r["lat"]) for r in table.connect().execute("SELECT lon, lat FROM measures WHERE lat IS NOT NULL")]
    hit = {(f.anchor.geo[0], f.anchor.geo[1]) for f in result.findings if f.anchor}
    im = Image.new("RGB", (1400, 720), (250, 248, 244))
    d = ImageDraw.Draw(im)
    for i, (city, (lo0, lo1, la0, la1)) in enumerate({"Houston": (-95.9, -95.0, 29.5, 30.2),
                                                       "Los Angeles": (-118.7, -117.9, 33.7, 34.35)}.items()):
        ox = 20 + i * 700
        d.text((ox, 10), city, fill=(40, 40, 40), font=_font(20))
        for lo, la in pts:
            if lo0 <= lo <= lo1 and la0 <= la <= la1:
                x, y = ox + (lo - lo0) / (lo1 - lo0) * 660, 40 + (la1 - la) / (la1 - la0) * 640
                big = (lo, la) in hit
                r = 6 if big else 2
                d.ellipse([x - r, y - r, x + r, y + r], fill=COL["pass"] if big else (190, 186, 178))
    d.text((20, 690), result.verdict.text[:150], fill=(40, 40, 40), font=_font(16))
    im.save(OUT / "measure_search" / f"{name}.png")


def main() -> None:
    lines = ["| tool | scan | what | verdict | checks | findings | seconds |", "|---|---|---|---|---|---|---|"]
    for tid, (extra, example) in TOOLS.items():
        for sid, why in SCANS.items():
            inputs = {"scan": sid, **extra}
            if tid in PANO_TOOLS:
                inputs["read_panoramas"] = sid in VISION
            t0 = time.time()
            try:
                r = run_tool(tid, inputs, ToolContext())
            except Exception as e:
                lines.append(f"| {tid} | {sid} | {why} | ERROR {type(e).__name__}: {e} | | | |")
                continue
            secs = time.time() - t0
            from ...tools.registry import default_plan
            save_example(tid, default_plan(sid), r)
            if tid == "curb_to_door" and sid == example:
                curb_picture(r, sid)
            lines.append(f"| {tid} | {sid} | {why} | {r.verdict.status}: {r.verdict.text[:90]} | {len(r.checks)} | "
                         f"{len(r.findings)} | {secs:.1f} |")
        print(tid, "done", flush=True)
    fleet = run_tool("robot_fit", {}, ToolContext())
    (OUT / "robot_fit" / "fleet.json").write_text(json.dumps(fleet.model_dump(mode="json"), indent=1))
    lines.append(f"| robot_fit | {len(fleet.scope.sids)} scans | measures table | {fleet.verdict.text} | | | |")
    (OUT / "measure_search").mkdir(parents=True, exist_ok=True)
    for name, crit in SEARCHES.items():
        r = run_tool("measure_search", {"criteria": crit, "limit": 20}, ToolContext())
        (OUT / "measure_search" / f"{name}.json").write_text(json.dumps(r.model_dump(mode="json"), indent=1))
        search_picture(r, name)
        lines.append(f"| measure_search | {name} | {json.dumps(crit)} | {r.verdict.text} | {len(r.checks)} | | |")
    (OUT / "verify.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    _ = rows  # the index is loaded by the tools; imported here so a missing CSV fails early


if __name__ == "__main__":
    main()
