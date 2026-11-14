"""Wall recovery from the schematic DXF and PNG, on hand-made drawings; and on a real no-wall scan when the data
folder has it.

Two rooms, inner faces drawn, a 0.2 m wall between them with a 0.9 m door:

    y=3  +--------+  +--------+
         |   A    |  |   B    |       A: x 0..4, B: x 4.2..8.2; door in the shared wall, y 1.0..1.9
    y=0  +--------+  +--------+
"""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from threshold.config import DATA
from threshold.scanplan import apply_recovered_walls
from threshold.sources import recover

A = [(0, 0), (4, 0), (4, 3), (0, 3)]
B = [(4.2, 0), (8.2, 0), (8.2, 3), (4.2, 3)]


def ring_lines(pts):
    return [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


def dxf_text(lines) -> str:
    body = "".join(f"0\nLINE\n8\n0\n10\n{a[0]}\n20\n{a[1]}\n30\n0.0\n11\n{b[0]}\n21\n{b[1]}\n31\n0.0\n" for a, b in lines)
    return f"999\nCreated by hand\n0\nSECTION\n2\nENTITIES\n{body}0\nENDSEC\n0\nEOF\n"


def png(lines, door=None, ox=40, oy=340, dotted=True) -> np.ndarray:
    """Draw the outlines at 100 px/m (x_px = ox + 100 x, y_px = oy - 100 y), 6 px wide, with the door's span
    left open on both faces and, like Matterport, a dotted line across it."""
    img = Image.new("L", (900, 400), 255)
    d = ImageDraw.Draw(img)
    P = lambda p: (ox + p[0] * 100, oy - p[1] * 100)
    for a, b in lines:
        d.line([P(a), P(b)], fill=0, width=6)
    if door:
        y0, y1 = door
        for x in (4.0, 4.2):
            d.line([P((x, y0)), P((x, y1))], fill=255, width=8)
            if dotted:
                for y in np.arange(y0, y1, 0.08):
                    d.line([P((x, y)), P((x, y + 0.03))], fill=0, width=2)
    return np.asarray(img)


PANOS = [{"id": "pa", "position": [2, 1.5, 1.4], "room": "A", "floor": "f"},
         {"id": "pb", "position": [6, 1.5, 1.4], "room": "B", "floor": "f"}]
ROOMS = [{"id": "A", "floor": "f", "area": 12.0, "polygon": []}, {"id": "B", "floor": "f", "area": 12.0, "polygon": []}]


def test_dxf_lines_reads_line_entities():
    assert recover.dxf_lines(dxf_text(ring_lines(A))) == [((0.0, 0.0), (4.0, 0.0)), ((4.0, 0.0), (4.0, 3.0)),
                                                          ((4.0, 3.0), (0.0, 3.0)), ((0.0, 3.0), (0.0, 0.0))]


def test_shared_wall_sits_midway_with_the_gap_as_thickness():
    lines = ring_lines(A) + ring_lines(B)
    polys = recover.faces(lines)
    match = recover.match_rooms(polys, ROOMS, PANOS)
    walls = recover.build_walls({r: polys[i] for r, i in match.items()})
    shared = [w for w in walls if len(w["rooms"]) == 2]
    assert len(shared) == 1 and sorted(shared[0]["rooms"]) == ["A", "B"]
    assert shared[0]["thickness"] == pytest.approx(0.2) and shared[0]["a"][0] == pytest.approx(4.1)
    assert abs(shared[0]["a"][1] - shared[0]["b"][1]) == pytest.approx(3.0)
    outer = [w for w in walls if len(w["rooms"]) == 1]
    assert len(outer) == 6 and all(w["thickness"] is None for w in outer)


def test_newer_style_open_corners_and_door_gaps_still_close():
    # each face its own segment, corners 1 cm open, and A's right face and B's left face open at the door
    lines = [((0, 0.01), (0, 3)), ((0.01, 3), (4, 3)), ((4, 2.99), (4, 1.9)), ((4, 1.0), (4, 0.01)), ((3.99, 0), (0, 0)),
             ((4.2, 0.01), (4.2, 1.0)), ((4.2, 1.9), (4.2, 2.99)), ((4.21, 3), (8.2, 3)), ((8.2, 2.99), (8.2, 0)),
             ((8.19, 0), (4.21, 0))]
    polys = recover.faces(lines)
    assert sorted(round(p.area, 1) for p in polys) == [12.0, 12.0]


def test_door_found_in_the_png_with_its_width():
    lines = ring_lines(A) + ring_lines(B)
    rec = recover.recover_floor(dxf_text(lines), png(lines, door=(1.0, 1.9)), ROOMS, PANOS)
    assert rec["registration"] > 0.9
    doors = [o for o in rec["openings"] if o["type"] == "doorway"]
    assert len(doors) == 1 and doors[0]["width"] == pytest.approx(0.9, abs=0.05)
    assert doors[0]["center"] == pytest.approx([4.1, 1.45], abs=0.05) and sorted(doors[0]["rooms"]) == ["A", "B"]
    assert not [o for o in rec["openings"] if o["type"] != "doorway"]  # the outer walls are solid


def test_registration_finds_an_offset_png():
    lines = ring_lines(A) + ring_lines(B)
    ox, oy, score = recover.register(png(lines, ox=63, oy=311) < 128, lines)
    assert (ox, oy) == pytest.approx((63, 311), abs=1.5) and score > 0.9


def test_recovered_walls_are_marked_and_never_called_measured():
    lines = ring_lines(A) + ring_lines(B)
    rec = recover.recover_floor(dxf_text(lines), png(lines, door=(1.0, 1.9)), ROOMS, PANOS)
    plan = {"sid": "t", "geo": None, "has": {"openings": False}, "floors": [{"id": "f"}], "walls": [], "openings": [],
            "panos": PANOS, "stairs": [],
            "rooms": [{**r, "label": None, "label_confidence": None, "area_source": "matterport", "walls": [],
                       "holes": [], "hole_polygons": [], "extra_polygons": [], "polygon_source": None} for r in ROOMS],
            "quality": {"walls": False, "georef": False, "counts": {"edges_dropped": 0}, "notes": ["no wall graph: ..."]}}
    apply_recovered_walls(plan, [recover.plan_parts("f", "r0", rec)], "apartment_unit")
    q = plan["quality"]
    assert q["walls"] and q["walls_source"] == "dxf" and q["walls_confidence"] in ("medium", "low")
    assert q["walls_error_m"] > 0 and q["opening_width_error_m"] > 0
    assert all(w["source"] == "dxf" for w in plan["walls"]) and all(o["height"] is None for o in plan["openings"])
    assert all(r["polygon_source"] == "dxf" and r["area"] == 12.0 for r in plan["rooms"])  # Matterport's area kept
    assert not any(n.startswith("no wall graph") for n in q["notes"]) and "not measured" in q["notes"][-1]
    door = next(o for o in plan["openings"] if o["type"] == "doorway")
    assert door["exterior"] is False


def test_real_no_wall_scan_gets_recovered_walls():
    if not (DATA / "cache" / "floorplan" / "<scan-id>").exists():
        pytest.skip("data folder without the <scan-id> schematic")
    from threshold.sources import matterport as mp
    p = mp.plan("<scan-id>")
    assert p["quality"]["walls_source"] == "dxf" and p["quality"]["walls"]
    assert p["quality"]["counts"]["rooms_recovered"] == 6 and sum(o["type"] == "doorway" for o in p["openings"]) >= 4
