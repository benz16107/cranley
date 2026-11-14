"""Small hand-made plans and records for the truth tools; no sponsor data and no network.

The home: living room 6 x 5, two bedrooms 4 x 3 (the second has no window and no closet), a full bathroom off the
first bedroom, a half bathroom off the living room, a walk-in closet off the first bedroom, a garage, a void and an
unbounded patio. Interior living area 63.8 m2 (686.7 ft2).
"""
import pytest

from threshold.tools.record_vs_reality import gather


def _rect(rid, label, x, y, w, d, height=2.5, walls=True):
    pts = [[x, y], [x + w, y], [x + w, y + d], [x, y + d]]
    wall_ids = [f"{rid}w{i}" for i in range(4)] if walls else []
    room = {"id": rid, "floor": "f1", "label": label, "label_confidence": 1, "label_source": "matterport",
            "polygon": pts if walls else [], "area": w * d, "height": height, "width": w, "depth": d,
            "walls": wall_ids, "holes": [], "center": [x + w / 2, y + d / 2]}
    ws = [{"id": wall_ids[i], "floor": "f1", "a": pts[i], "b": pts[(i + 1) % 4], "type": "wall", "thickness": 0.1,
           "length": float(((pts[i][0] - pts[(i + 1) % 4][0]) ** 2 + (pts[i][1] - pts[(i + 1) % 4][1]) ** 2) ** 0.5),
           "rooms": [rid], "openings": []} for i in range(4)] if walls else []
    return room, ws


def make_home(windows=True, walls=True, b2_height=2.5):
    spec = [("L", "Living Room", 0, 0, 6, 5), ("B1", "Bedroom", 6, 0, 4, 3), ("B2", "Bedroom", 6, 3, 4, 3),
            ("T1", "Bathroom", 10, 0, 2, 2.5), ("T2", "Bathroom", 0, 5, 1.5, 1.2), ("C1", "Closet", 10, 2.5, 1.5, 2),
            ("G", "Garage", -6, 0, 6, 6), ("V", "Void", 3, 5, 1, 1)]
    rooms, walls_ = [], []
    for rid, lab, x, y, w, d in spec:
        r, ws = _rect(rid, lab, x, y, w, d, height=b2_height if rid == "B2" else 2.5, walls=walls)
        rooms.append(r)
        walls_ += ws
    patio, _ = _rect("P", None, 0, -3, 4, 2, walls=False)
    patio["height"] = None
    rooms.append(patio)
    opens = []

    def op(oid, typ, rooms_, wall, center, width=0.9, height=2.0, sill=0.0):
        o = {"id": oid, "wall": wall, "floor": "f1", "type": typ, "width": width, "height": height, "sill": sill,
             "center": center, "rooms": rooms_}
        opens.append(o)
        for w in walls_:
            if w["id"] == wall:
                w["openings"].append(oid)

    if walls:
        op("d1", "doorway", ["L", "B1"], "Lw1", [6, 1.5])
        op("d2", "doorway", ["L", "B2"], "Lw1", [6, 4.0])
        op("d3", "doorway", ["B1", "T1"], "B1w1", [10, 1.0])
        op("d4", "doorway", ["L", "T2"], "Lw2", [0.75, 5])
        op("d5", "doorway", ["B1", "C1"], "B1w1", [10, 2.7])
        op("d6", "doorway", ["L", "G"], "Lw3", [0, 2.5])
        op("d7", "doorway", ["L"], "Lw0", [3, 0])  # front door
        if windows:
            op("w1", "window", ["L"], "Lw0", [1.5, 0], width=2.0, height=1.5, sill=0.9)
            op("w2", "window", ["B1"], "B1w0", [8, 0], width=1.2, height=1.2, sill=0.9)
    q = {"walls": walls, "polygons": walls, "openings": walls, "labels": True, "georef": True, "counts": {}, "notes": []}
    return {"schema": "scanplan/1", "sid": "home1", "name": "12 Test Street", "quality": q,
            "geo": {"lat": 34.0, "lon": -118.3, "altitude": 0, "yaw_deg": 0.0, "translation": {"x": 0, "y": 0},
                    "source": "test"},
            "has": {"room_labels": True, "openings": walls, "splat": False, "defurnished": False},
            "ids": {}, "floors": [{"id": "f1", "label": "Floor 1", "sequence": 0, "elevation": 0.0}],
            "walls": walls_, "rooms": rooms, "openings": opens,
            "panos": [{"id": f"p{r['id']}", "label": r["id"], "position": [*r["center"], 1.5], "rotation": [0, 0, 0, 1],
                       "floor": "f1", "room": r["id"], "neighbors": []} for r in rooms if r["walls"]],
            "floorplans": []}


def claim(value, path, unit=None):
    return {"value": value, "unit": unit, "path": path}


HOME_RECORD = {
    "residential_listing": {"remarks": "Bright 2 bed, 1.5 bath with 9 ft ceilings and a fireplace.",
                            "property": {"address": {"latitude": 34.0, "longitude": -118.3}}},
    "residential_features": {"sections": [
        {"category": "Inside This Home", "subcategory": "Bedrooms and Bathrooms", "lines": ["Walk-In Closet", "2 Bedrooms"]},
        {"category": "Inside This Home", "subcategory": "Interior Spaces", "lines": ["Living Room with Fireplace"]},
        {"category": "Inside This Home", "subcategory": "Parking", "lines": ["2 Car Garage"]},
        {"category": "Community Details", "subcategory": "Amenities", "lines": ["Community Pool"]}]},
    "claims": {"beds": claim(2, "residential-listings.property.bedsMax"),
               "baths": claim(1.5, "residential-listings.property.bathsMax"),
               "living_area": claim(720, "residential-listings.property.sqftMax", "ft2"),
               "stories": claim(2, "residential-listings.property.stories"),
               "year_built": claim(1950, "residential-listings.property.yearBuilt")},
}

INDUSTRIAL_RECORD = {
    "scope": "building",
    "property": {"propertyType": 2, "primaryAddress": {"latitude": 29.8, "longitude": -95.5}},
    "claims": {"gross_area": claim(700.0, "grossBuildingAreaSquareFeet", "ft2"),
               "stories": claim(3, "numStoriesAboveGrade"),
               "ceiling_height": claim(24.0, "propertyIndustrial.structural.ceilingHeightFeet", "ft"),
               "dock_doors": claim(4, "propertyIndustrial.numExternalLoadingDocks"),
               "construction_material": claim("Metal", "buildingConstructionMaterial")},
}

UNIT_RECORD = {
    "scope": "unit",
    "property": {"propertyType": 11, "primaryAddress": {"latitude": 29.7, "longitude": -95.4}},
    "claims": {"gross_area": claim(250000.0, "grossBuildingAreaSquareFeet", "ft2"),
               "unit_beds": claim(2, "propertyApartment.models[].numBeds"),
               "unit_area_min": claim(700, "propertyApartment.models[].minSquareFeet", "ft2"),
               "unit_area_max": claim(700, "propertyApartment.models[].maxSquareFeet", "ft2")},
}


def site(**facts):
    """Aerial site facts in the shape aerial.site.site_facts returns."""
    src = {"layer": "vexcel", "method": "lookup", "confidence": "medium", "note": "test"}
    return {"lat": 29.8, "lon": -95.5, "structure": "at the point", "parcel": None,
            "facts": [{"id": k, "label": k, "value": v, "unit": None, "source": src} for k, v in facts.items()]}


@pytest.fixture
def records(monkeypatch):
    """Route gather.record to hand-made records keyed by scan id."""
    table = {"home1": HOME_RECORD}

    def fake(sid):
        return table.get(sid)
    monkeypatch.setitem(gather.SOURCES, "record", fake)
    return table
