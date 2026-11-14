"""Print the lat/lon of a scan's outline corners under each yaw and translation convention, so the lead can lay
them over an aerial photo and pick the one that matches. Also writes them as GeoJSON to the data folder
(never the repo).

    cd server && uv run python -m threshold.geometry.check_georef [sid]      # default: a Houston house
"""
from __future__ import annotations

import json
import sys

from shapely.ops import unary_union

from threshold.config import DATA

from . import georef
from ._plan import polygons


def outline_corners(plan: dict) -> list[tuple[float, float]]:
    shape = unary_union([p.buffer(0.05) for p in polygons(plan).values() if p is not None]).buffer(-0.05)
    poly = max(getattr(shape, "geoms", [shape]), key=lambda g: g.area)
    return list(poly.exterior.simplify(0.3).coords)[:-1]


def main(sid: str = "<scan-id>") -> None:
    plan = json.loads((DATA / "fixtures" / "scanplan" / f"{sid}.json").read_text())
    g = plan["geo"]
    print(f"{sid}  {plan.get('address') or plan.get('name')}  anchor {g['lat']:.7f}, {g['lon']:.7f}  "
          f"yaw_deg {g['yaw_deg']:.2f}  translation {g['translation']}")
    print(f"current convention: YAW_SIGN={georef.YAW_SIGN} TRANSLATION={georef.TRANSLATION!r}\n")
    corners = outline_corners(plan)
    features = []
    for sign in (1, -1):
        for tr in ("scan", "enu"):
            pts = [georef.to_latlon(plan, x, y, yaw_sign=sign, translation=tr) for x, y in corners]
            print(f"yaw_sign={sign:+d} translation={tr!r}:")
            for (x, y), (lat, lon) in zip(corners, pts):
                print(f"   scan ({x:7.2f}, {y:7.2f})  ->  {lat:.7f}, {lon:.7f}")
            features.append({"type": "Feature", "properties": {"sid": sid, "yaw_sign": sign, "translation": tr},
                             "geometry": {"type": "Polygon", "coordinates": [[[lon, lat] for lat, lon in pts + pts[:1]]]}})
    out = DATA / "shots" / "geometry" / f"georef_{sid}.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    print(f"\nGeoJSON with all four outlines: {out}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
