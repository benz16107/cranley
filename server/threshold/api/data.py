"""Scan data routes (Contract 2 in docs/ARCHITECTURE.md). The first cut: plan, panorama faces, floor plan,
and the building list. The data workstream extends this."""
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Response

from ..sources import matterport as mp

router = APIRouter(prefix="/api")


def _or_404(fn, *a, **k):
    try:
        return fn(*a, **k)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None


@router.get("/buildings")
def buildings() -> dict:
    """One GeoJSON point per address, with the scans at it."""
    groups = defaultdict(list)
    for r in mp.index().values():
        if r["lat"] and r["lon"]:
            groups[(round(float(r["lat"]), 5), round(float(r["lon"]), 5))].append(r)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
         "properties": {"address": rows[0]["address"], "city": rows[0]["city"], "segment": rows[0]["segment"],
                        "scans": [{"sid": r["sid"], "name": r["name"], "rooms": int(r["room_count"] or 0),
                                   "panos": int(r["pano_count"] or 0)} for r in rows],
                        "count": len(rows), "splat": any(r["splat"] == "yes" for r in rows),
                        "defurnished": any(r["defurnished"] == "yes" for r in rows)}}
        for (lat, lon), rows in groups.items()]}


@router.get("/scan/{sid}/plan")
def plan(sid: str) -> dict:
    return _or_404(mp.plan, sid)


@router.get("/scan/{sid}/pano/{pano}/{face}.jpg")
def pano_face(sid: str, pano: str, face: int, res: str = "2k", view: str = "furnished") -> Response:
    return Response(_or_404(mp.pano_face, sid, pano, face, res, view), media_type="image/jpeg",
                    headers={"Cache-Control": "max-age=86400"})


@router.get("/scan/{sid}/floorplan/{floor}.{fmt}")
def floorplan(sid: str, floor: str, fmt: str, flags: str = "photogramy") -> Response:
    return Response(_or_404(mp.floorplan, sid, floor, fmt, flags), media_type=f"image/{'jpeg' if fmt == 'jpg' else fmt}",
                    headers={"Cache-Control": "max-age=86400"})
