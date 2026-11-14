"""How many scanned houses have a pool, from Vexcel's property facts (one cached call per house).

    cd server && uv run python -m threshold.tools.path_to_water.survey [sample_of_others]

Reads every residential scan with a drone capture plus a seeded random sample of the other residential
scans. Writes the per-house rows to $THRESHOLD_DATA_DIR/shots/tools/path_to_water/pool_survey.json (sponsor
data, never the repo) and prints the counts.
"""
from __future__ import annotations

import json
import random
import sys

from ...aerial import site, vexcel
from ...config import DATA
from ...sources import index


def survey(sample: int = 60, seed: int = 7) -> dict:
    houses = [r for r in index.rows().values() if r.get("segment") == "residential" and r.get("lat")]
    drone = [r for r in houses if (r.get("drone_photos") or 0) not in ("", "0", 0, None)]
    others = sorted((r for r in houses if r not in drone), key=lambda r: r["sid"])
    picked = random.Random(seed).sample(others, min(sample, len(others)))
    out = []
    for group, rs in (("drone", drone), ("sample", picked)):
        for r in rs:
            try:
                p = ((site.property_raw(float(r["lat"]), float(r["lon"])).get("features") or [{}])[0]).get("properties") or {}
            except vexcel.VexcelError as e:
                out.append({"sid": r["sid"], "group": group, "error": str(e)[:120]})
                continue
            kinds = [k for k in ("in-ground", "above-ground", "hot-tub") if p.get(f"pool.types.{k}.detected")]
            out.append({"sid": r["sid"], "group": group, "lat": float(r["lat"]), "lon": float(r["lon"]),
                        "pool": bool(p.get("pool.detected")), "kinds": kinds,
                        "enclosed": sum(p.get(f"pool.types.{k}.enclosed.count") or 0 for k in kinds),
                        "open": sum(p.get(f"pool.types.{k}.non-enclosed.count") or 0 for k in kinds),
                        "area_m2": p.get("pool.total-area"), "inside_parcel": p.get("request-information.inside-parcel")})
    summary = {}
    for g in ("drone", "sample"):
        rs = [r for r in out if r["group"] == g and "error" not in r]
        pools = [r for r in rs if r["pool"]]
        summary[g] = {"houses": len(rs), "errors": sum(1 for r in out if r["group"] == g and "error" in r),
                      "with_pool": len(pools), "in_ground": sum("in-ground" in r["kinds"] for r in pools),
                      "enclosed": sum(r["enclosed"] > 0 for r in pools), "open": sum(r["open"] > 0 for r in pools)}
    return {"summary": summary, "rows": out}


def main(argv: list[str]) -> None:
    res = survey(int(argv[0]) if argv else 60)
    f = DATA / "shots" / "tools" / "path_to_water" / "pool_survey.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(res, indent=1))
    print(json.dumps(res["summary"], indent=1))
    print(f"rows: {f}")


if __name__ == "__main__":
    main(sys.argv[1:])
