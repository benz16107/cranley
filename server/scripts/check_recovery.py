"""Measure wall recovery honestly: on scans that HAVE a wall graph, recover walls from the schematic DXF and PNG
as if they did not, and compare rooms, areas, door positions and widths with the measured ones. With --nowall,
run recovery over real no-wall scans and count how many get usable walls. --shots draws comparisons to
$THRESHOLD_DATA_DIR/shots/walls/.

    cd server && uv run python scripts/check_recovery.py [--n 15] [--nowall 30] [--shots]
"""
from __future__ import annotations

import io
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from threshold.config import DATA
from threshold.geometry._plan import polygons
from threshold.scanplan import normalize
from threshold.sources import index, recover
from threshold.sources import matterport as mp

SHOTS = DATA / "shots" / "walls"
MATCH_M = 0.75  # a recovered opening within this of a measured one is the same opening


def floor_inputs(sid: str, floor: str):
    dxf = mp.floorplan(sid, floor, "dxf", "schematic").decode("utf-8", "replace")
    png = np.asarray(Image.open(io.BytesIO(mp.floorplan(sid, floor, "png", "schematic"))).convert("L"))
    return dxf, png


def cached_models(walls: bool) -> list[str]:
    out = []
    for f in sorted((DATA / "cache" / "model").glob("*.json")):
        m = json.loads(f.read_text())
        nv = sum(len(fl.get("vertices") or []) for fl in m.get("floors") or [])
        if bool(nv) == walls and m.get("rooms"):
            out.append(m["id"])
    return out


def evaluate(sid: str, shots: bool) -> dict | None:
    plan = normalize(mp.model(sid), index.rows().get(sid))
    truth_polys = polygons(plan)
    res = {"sid": sid, "kind": (index.rows().get(sid) or {}).get("kind"), "floors": []}
    for fl in plan["floors"]:
        rooms = [r for r in plan["rooms"] if r["floor"] == fl["id"] and r["label"] != "Void"]
        truth = {r["id"]: truth_polys.get(r["id"]) for r in rooms if truth_polys.get(r["id"]) is not None}
        if not truth:
            continue
        try:
            dxf, png = floor_inputs(sid, fl["id"])
        except LookupError:
            continue
        panos = [p for p in plan["panos"] if p["floor"] == fl["id"]]
        stripped = [{**r, "polygon": []} for r in rooms]
        rec = recover.recover_floor(dxf, png, stripped, panos)
        areas = []
        for rid, poly in rec["polygons"].items():
            t = truth.get(rid)
            if t is not None:
                areas.append({"room": rid, "recovered": poly.area, "truth_polygon": t.area,
                              "matterport": next(r["area"] for r in rooms if r["id"] == rid),
                              "iou": poly.intersection(t).area / poly.union(t).area})
        from shapely.geometry import LineString, Point
        true_walls = [LineString([w["a"], w["b"]]) for w in plan["walls"] if w["floor"] == fl["id"] and w["type"] == "wall"]
        wall_err = {"shared": [], "outer": []}
        for w in rec["walls"]:
            mid = Point((w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2)
            if true_walls:
                wall_err["shared" if len(w["rooms"]) == 2 else "outer"].append(min(t.distance(mid) for t in true_walls))
        t_open = [o for o in plan["openings"] if o["floor"] == fl["id"]]
        pairs, used = [], set()
        for o in t_open:
            best = min((i for i in range(len(rec["openings"])) if i not in used),
                       key=lambda i: math.dist(rec["openings"][i]["center"], o["center"]), default=None)
            if best is not None and math.dist(rec["openings"][best]["center"], o["center"]) <= MATCH_M:
                used.add(best)
                pairs.append({"type": o["type"], "rooms_true": len(o["rooms"]), "rooms_rec": len(rec["openings"][best]["rooms"]),
                              "pos_err": math.dist(rec["openings"][best]["center"], o["center"]),
                              "width_true": o["width"], "width_rec": rec["openings"][best]["width"]})
        res["floors"].append({"floor": fl["id"], "rooms_truth": len(truth), "rooms_recovered": len(rec["polygons"]),
                              "rooms_truth_matched": sum(1 for a in areas), "faces_unmatched": rec["faces_unmatched"],
                              "registration": rec["registration"], "areas": areas, "wall_err": wall_err,
                              "openings_truth": len(t_open), "openings_truth_by_type": _count(o["type"] for o in t_open),
                              "openings_recovered": len(rec["openings"]), "pairs": pairs})
        if shots:
            draw_compare(sid, fl, plan, rec, png)
    return res if res["floors"] else None


def _count(it):
    out = {}
    for k in it:
        out[k] = out.get(k, 0) + 1
    return out


def draw_compare(sid: str, fl: dict, plan: dict, rec: dict, png: np.ndarray | None, tag: str = "compare") -> None:
    """Measured walls grey (when the scan has them), recovered walls red, openings: measured orange, recovered blue.
    The schematic PNG faint behind, at its registered offset."""
    ws = [w for w in rec["walls"]]
    pts = [p for w in ws for p in (w["a"], w["b"])] + [p for w in plan["walls"] if w["floor"] == fl["id"] for p in (w["a"], w["b"])]
    if not pts:
        return
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    s = 60
    x0, y0 = min(xs) - 0.8, min(ys) - 0.8
    W, H = int((max(xs) - x0 + 0.8) * s), int((max(ys) - y0 + 0.8) * s)
    img = Image.new("RGB", (W, H), "white")
    if png is not None:
        ox, oy, _ = recover.register(png < 128, recover.dxf_lines(mp.floorplan(sid, fl["id"], "dxf", "schematic").decode()))
        bg = Image.fromarray(png).convert("RGB")
        # crop/scale the PNG into this canvas: canvas px = (x - x0) * s ; png px = ox + x * 100
        k = s / recover.PX_PER_M
        bg = bg.resize((int(bg.width * k), int(bg.height * k)))
        img.paste(Image.blend(Image.new("RGB", bg.size, "white"), bg, 0.3), (int(-ox * k - x0 * s), int(H - oy * k + y0 * s)))
    d = ImageDraw.Draw(img)
    T = lambda p: ((p[0] - x0) * s, H - (p[1] - y0) * s)
    for w in plan["walls"]:
        if w["floor"] == fl["id"] and w["type"] == "wall":
            d.line([T(w["a"]), T(w["b"])], fill=(120, 120, 120), width=7)
    for w in ws:
        d.line([T(w["a"]), T(w["b"])], fill=(220, 30, 30), width=2)
    for o in plan["openings"]:
        if o["floor"] == fl["id"]:
            c = T(o["center"])
            d.ellipse([c[0] - 7, c[1] - 7, c[0] + 7, c[1] + 7], outline=(255, 140, 0), width=3)
    for o in rec["openings"]:
        c, half = np.array(o["center"]), o["width"] / 2
        w = rec["walls"][o["wall"]]
        u = (np.array(w["b"]) - np.array(w["a"])) / max(np.linalg.norm(np.array(w["b"]) - np.array(w["a"])), 1e-9)
        d.line([T(c - u * half), T(c + u * half)], fill=(30, 90, 230), width=5)
    d.text((8, 8), f"{sid} {fl.get('label') or ''}: grey measured walls, red recovered, orange rings measured "
                   f"openings, blue bars recovered openings", fill=(0, 0, 0))
    SHOTS.mkdir(parents=True, exist_ok=True)
    img.save(SHOTS / f"{tag}_{sid}_{fl.get('sequence') or 0}.png")


def summarize(results: list[dict]) -> None:
    fl = [f for r in results for f in r["floors"]]
    print(f"\n== recovery on {len(results)} scans with a wall graph ({len(fl)} floors), as if they had none")
    rt, rr = sum(f["rooms_truth"] for f in fl), sum(f["rooms_truth_matched"] for f in fl)
    print(f"rooms: {rr} of {rt} measured rooms recovered with an outline ({rr / rt:.0%}); "
          f"{sum(f['faces_unmatched'] for f in fl)} DXF outlines matched no room")
    a = [x for f in fl for x in f["areas"]]
    rel = [abs(x["recovered"] - x["matterport"]) / x["matterport"] for x in a if x["matterport"]]
    relp = [abs(x["recovered"] - x["truth_polygon"]) / x["truth_polygon"] for x in a]
    print(f"room area vs Matterport's floor area: median error {statistics.median(rel):.1%}, 90th pct "
          f"{sorted(rel)[int(0.9 * len(rel))]:.1%}; vs the wall-centre outline: median {statistics.median(relp):.1%} "
          f"(recovered outlines are inner faces, so smaller)")
    print(f"room outline IoU with the measured outline: median {statistics.median(x['iou'] for x in a):.2f}, "
          f"10th pct {sorted(x['iou'] for x in a)[len(a) // 10]:.2f}")
    for k in ("shared", "outer"):
        e = sorted(x for f in fl for x in f["wall_err"][k])
        if e:
            print(f"{k} wall centre lines: {len(e)}, distance to the nearest measured wall median {statistics.median(e):.3f} m, "
                  f"90th pct {e[int(0.9 * len(e))]:.3f} m")
    for kind, sel in (("doorways and openings", ("doorway", "opening")), ("windows", ("window",))):
        tot = sum(v for f in fl for k, v in f["openings_truth_by_type"].items() if k in sel)
        pr = [p for f in fl for p in f["pairs"] if p["type"] in sel]
        if not tot:
            continue
        print(f"{kind}: {len(pr)} of {tot} measured found within {MATCH_M} m ({len(pr) / tot:.0%})", end="")
        if pr:
            pe = [p["pos_err"] for p in pr]
            we = [abs(p["width_rec"] - p["width_true"]) for p in pr if p["width_true"]]
            print(f"; position error median {statistics.median(pe):.2f} m; width error median "
                  f"{statistics.median(we):.2f} m, 90th pct {sorted(we)[int(0.9 * len(we))]:.2f} m", end="")
        print()
    rec = sum(f["openings_recovered"] for f in fl)
    matched = sum(len(f["pairs"]) for f in fl)
    print(f"recovered openings: {rec}, of which {matched} match a measured opening ({matched / max(rec, 1):.0%} precision)")
    print(f"registration (share of DXF line samples on PNG ink): median "
          f"{statistics.median(f['registration'] for f in fl if f['registration'] is not None):.2f}")
    for r in results:
        for f in r["floors"]:
            print(f"  {r['sid']} {r['kind']:<15} rooms {f['rooms_truth_matched']}/{f['rooms_truth']}  openings "
                  f"{len(f['pairs'])}/{f['openings_truth']} found, {f['openings_recovered']} recovered  reg {f['registration']:.2f}")


def nowall(n: int, shots: bool) -> None:
    """Full pipeline (mp.plan) on real no-wall scans: cached ones first, then sample_sids.txt, then a few
    apartment units and offices from the index, fetched one model at a time (cached)."""
    rows = index.rows()
    pool = cached_models(False)
    pool += [s for s in (DATA / "sample_sids.txt").read_text().split() if s not in pool]
    pool += [s for s, r in sorted(rows.items()) if r.get("kind") in ("apartment_unit", "office") and s not in pool][::97]
    done, usable, conf = [], 0, {}
    for sid in pool:
        if len(done) >= n:
            break
        try:
            raw = mp.model(sid)
        except LookupError:
            continue
        if sum(len(f.get("vertices") or []) for f in raw.get("floors") or []) or not raw.get("rooms"):
            continue
        p = mp.plan(sid)
        q = p["quality"]
        ok = bool(q["walls"] and q.get("walls_source") == "dxf")
        usable += ok
        conf[q.get("walls_confidence") if ok else "none"] = conf.get(q.get("walls_confidence") if ok else "none", 0) + 1
        c = q["counts"]
        done.append(sid)
        print(f"  {sid} {(rows.get(sid) or {}).get('kind') or '?':<15} usable {ok!s:<5} conf {q.get('walls_confidence')!s:<6} "
              f"rooms outlined {c.get('rooms_recovered')}/{c['rooms']} walls {c['walls']} openings {c['openings']} "
              f"registration {c.get('schematic_registration')}")
        if shots and ok and len(done) <= 8:
            draw_on_photo(p)
    print(f"\n== {usable} of {len(done)} real no-wall scans got usable walls ({usable / max(len(done), 1):.0%}); confidence {conf}")


def draw_on_photo(p: dict) -> None:
    """Recovered walls (red), outlines (thin yellow) and openings (blue) on Matterport's photographic floor plan,
    which carries its own origin and resolution, so this is an independent check of the frame."""
    for fl in p["floors"]:
        fp = next((f for f in p["floorplans"] if f["floor"] == fl["id"] and f["flags"] == ["photogramy"] and f["format"] == "jpg"), None)
        if fp is None or not any(w["floor"] == fl["id"] for w in p["walls"]):
            continue
        img = Image.open(io.BytesIO(mp.floorplan(p["sid"], fl["id"], "jpg", "photogramy"))).convert("RGB")
        d = ImageDraw.Draw(img)
        r, (ox, oy) = fp["resolution"], (fp["origin"]["x"], fp["origin"]["y"])
        T = lambda q: ((q[0] - ox) * r, img.height - (q[1] - oy) * r)
        for room in p["rooms"]:
            if room["floor"] == fl["id"] and room["polygon"]:
                d.line([T(v) for v in room["polygon"] + room["polygon"][:1]], fill=(255, 220, 0), width=1)
        for w in p["walls"]:
            if w["floor"] == fl["id"]:
                d.line([T(w["a"]), T(w["b"])], fill=(230, 30, 30), width=3)
        walls = {w["id"]: w for w in p["walls"]}
        for o in p["openings"]:
            if o["floor"] == fl["id"]:
                w = walls[o["wall"]]
                a, b = np.array(w["a"]), np.array(w["b"])
                u = (b - a) / max(np.linalg.norm(b - a), 1e-9)
                c = np.array(o["center"])
                d.line([T(c - u * o["width"] / 2), T(c + u * o["width"] / 2)], fill=(40, 120, 255), width=7)
        for pano in p["panos"]:
            if pano["floor"] == fl["id"]:
                c = T(pano["position"])
                d.ellipse([c[0] - 4, c[1] - 4, c[0] + 4, c[1] + 4], fill=(0, 200, 0))
        d.text((8, 8), f"{p['sid']} (no wall graph): recovered walls red, outlines yellow, openings blue, panoramas green",
               fill=(255, 255, 255))
        SHOTS.mkdir(parents=True, exist_ok=True)
        img.save(SHOTS / f"recovered_{p['sid']}_{fl.get('sequence') or 0}.jpg", quality=88)


def main() -> None:
    args = sys.argv[1:]
    if "--nowall" in args:
        nowall(int(args[args.index("--nowall") + 1]), "--shots" in args)
        return
    n = int(args[args.index("--n") + 1]) if "--n" in args else 15
    shots = "--shots" in args
    rows = index.rows()
    walled = [s for s in cached_models(True) if (rows.get(s) or {}).get("segment") == "commercial"]
    walled += [s for s in cached_models(True) if (rows.get(s) or {}).get("kind") == "house"][: max(0, n - len(walled))]
    results = []
    for sid in walled:
        if len(results) >= n:
            break
        r = evaluate(sid, shots and len(results) < 6)
        if r:
            results.append(r)
    summarize(results)
    out = DATA / "shots" / "walls" / "recovery_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1, default=float))


if __name__ == "__main__":
    main()
