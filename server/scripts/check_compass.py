"""Settle the georef convention: lay each house's plan outline on its Vexcel building footprint under the four
yaw-sign x translation combinations and score the overlap. Prints one row per house and a summary; with --shots,
draws five overlays on the orthophoto under $THRESHOLD_DATA_DIR/shots/walls/.

    cd server && uv run python scripts/check_compass.py [n_houses] [--shots]
"""
from __future__ import annotations

import io
import statistics
import sys

from PIL import Image, ImageDraw

from threshold.aerial import site
from threshold.config import DATA
from threshold.geometry import georef
from threshold.sources import footprint, index
from threshold.sources import matterport as mp

COMBOS = [(1, "scan"), (1, "enu"), (-1, "scan"), (-1, "enu")]


def houses(n: int) -> list[str]:
    rows = index.rows()
    have = {p.stem for p in (DATA / "cache" / "model").glob("*.json")}
    out = [s for s, r in sorted(rows.items()) if r.get("kind") == "house" and r.get("drone_photos") and s in have]
    return out[:n]


def main(n: int = 14, shots: bool = False) -> None:
    table = []
    for sid in houses(n):
        plan = mp.plan(sid)
        if not plan["quality"]["walls"] or not (plan.get("geo") or {}).get("lat"):
            continue
        fp = footprint.footprint_enu(plan)
        if fp is None:
            print(f"{sid}: no footprint")
            continue
        scores = {c: footprint.overlap(plan, fp, yaw_sign=c[0], translation=c[1]) for c in COMBOS}
        fit = footprint.fit(plan, fp, yaw_sign=1, translation="enu")
        flip = footprint.fit(plan, fp, yaw_sign=-1, translation="enu")
        table.append((sid, scores, fit, flip))
        cells = "  ".join(f"{s:+d}/{t:<4} IoU {v['iou']:.2f} off {v['offset_m']:5.1f}m" for (s, t), v in scores.items())
        print(f"{sid}  yaw {plan['geo']['yaw_deg']:7.1f}  {cells}  | fit rot {fit['rotation_deg']:+6.1f} "
              f"shift {fit['shift_m']:4.1f}m IoU {fit['iou']:.2f} resid {fit['residual_m']:.2f}m"
              f" | yaw -1 refit rot {flip['rotation_deg']:+6.1f} IoU {flip['iou']:.2f}")
    print("\nmedian IoU / wins per combination (raw, no refit):")
    for c in COMBOS:
        ious = [s[c]["iou"] for _, s, *_ in table]
        wins = sum(max(s, key=lambda k: s[k]["iou"]) == c for _, s, *_ in table)
        offs = [s[c]["offset_m"] for _, s, *_ in table]
        print(f"  yaw_sign {c[0]:+d} translation {c[1]:<4}  median IoU {statistics.median(ious):.2f}  "
              f"wins {wins}/{len(table)}  median centroid offset {statistics.median(offs):.1f} m")
    good = [(f, g) for _, _, f, g in table if footprint.verdict(f) or footprint.verdict(g)]
    print(f"refit with free rotation (+-{footprint.MAX_ROTATION_DEG} deg) and shift, {len(good)} houses where either sign fits:")
    print(f"  yaw +1 fits better in {sum(f['iou'] > g['iou'] for f, g in good)}, yaw -1 in {sum(g['iou'] > f['iou'] for f, g in good)}")
    turn = [(f, g) for (f, g), y in zip(good, [t[0] for t in table if footprint.verdict(t[2]) or footprint.verdict(t[3])])
            if 20 < abs(mp.plan(y)["geo"]["yaw_deg"]) < 160]
    print(f"  of those, {len(turn)} have |yaw| between 20 and 160 deg (where the sign matters): "
          f"yaw +1 fits in {sum(footprint.verdict(f) for f, _ in turn)}, yaw -1 in {sum(footprint.verdict(g) for _, g in turn)}")
    rots = [f["rotation_deg"] for f, _ in good]
    print(f"  yaw +1 refit rotation: median {statistics.median(rots):+.1f} deg, abs median {statistics.median(abs(r) for r in rots):.1f} deg; "
          f"shift median {statistics.median(f['shift_m'] for f, _ in good):.1f} m; residual median {statistics.median(f['residual_m'] for f, _ in good):.2f} m")
    if shots:
        for sid, _, fit, _ in [t for t in table if footprint.verdict(t[2])][:5]:
            overlay(sid, fit)


def overlay(sid: str, fit: dict) -> None:
    plan = mp.plan(sid)
    g = plan["geo"]
    o = site.ortho(g["lat"], g["lon"], size_m=50, px=1024)
    img = Image.open(io.BytesIO(o.image)).convert("RGB")
    d = ImageDraw.Draw(img)
    fp = site.site_facts(g["lat"], g["lon"])["footprint"]
    from shapely import wkt
    poly = wkt.loads(fp)
    d.line([o.to_px(x, y) for x, y in poly.exterior.coords], fill=(255, 220, 0), width=3)
    outline = footprint.plan_outline(plan)
    for s, t, colour in ((georef.YAW_SIGN, georef.TRANSLATION, (255, 40, 40)),
                         (-georef.YAW_SIGN, georef.TRANSLATION, (80, 160, 255))):
        pts = [georef.to_latlon(plan, x, y, yaw_sign=s, translation=t) for x, y in outline.exterior.coords]
        d.line([o.to_px(lon, lat) for lat, lon in pts], fill=colour, width=3)
    d.text((10, 10), f"{sid}  yellow: Vexcel footprint  red: plan, chosen convention  blue: opposite yaw sign\n"
                     f"refit residual {fit['residual_m']:.2f} m, rotation {fit['rotation_deg']:+.1f} deg, shift {fit['shift_m']:.1f} m",
           fill=(255, 255, 255))
    out = DATA / "shots" / "walls" / f"compass_{sid}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=88)
    print("wrote", out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(int(args[0]) if args else 14, "--shots" in sys.argv)
