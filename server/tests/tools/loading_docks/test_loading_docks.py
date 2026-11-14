from tests.tools._site.fakes import facts, ll, offline  # noqa: F401
from shapely import wkt

from threshold.aerial import detect, site
from threshold.tools import run_tool
from threshold.tools._site import metres
from threshold.tools.loading_docks import assign, faces_of, keep_doors


def det(e, n, image, conf=0.5, box=(0, 0, 30, 100)):
    lon, lat = ll(e, n)
    return {"label": "loading dock", "confidence": conf, "anchor": {"geo": [lon, lat]}, "polygon": "POINT(0 0)",
            "image": image, "pixel_bbox": list(box)}


def fake_dets():
    # building is 40 m square centred on the site; four doors 5 m off its north wall, seen in oblique-south
    north = [det(x, 25, "oblique-south", box=(100 + 40 * i, 900, 30, 100)) for i, x in enumerate((-15, -5, 5, 15))]
    return north + [
        det(-5, 25, "oblique-south", conf=0.3, box=(141, 902, 30, 100)),  # same door twice
        det(0, 0, "oblique-south", box=(500, 400, 30, 40)),               # on the roof
        det(0, 70, "oblique-south", box=(600, 300, 30, 100)),             # another building
        det(26, 0, "oblique-north", box=(700, 900, 30, 100)),             # east wall seen edge-on
    ]


def test_doors_kept_per_wall():
    fp_m = metres(wkt.loads(facts({})["footprint"]), 29.7)
    doors = keep_doors(fake_dets(), fp_m, 29.7)
    by = assign(doors, faces_of(fp_m))
    assert {k: len(v) for k, v in by.items()} == {"north": 4}


def test_run_compares_with_record(offline):  # noqa: F811
    offline.setattr(site, "site_facts", lambda lat, lon: facts({"footprint_area": 1600.0}))
    offline.setattr(detect, "detect", lambda *a, **k: {"detections": fake_dets(), "images": []})
    import threshold.tools.loading_docks as ld
    offline.setattr(ld, "record_claims", lambda rec: {"dock_doors": {"value": 5, "path": "x"}, "drive_in_bays": {"value": 1, "path": "y"}})
    r = run_tool("loading_docks", {"lat": 29.7, "lon": -95.4, "use_vision": False})
    m = {x.id: x.value for x in r.metrics}
    assert m["aerial_docks"] == 4 and m["side.north"] == 4 and m["record_docks"] == 5
    assert {c.id: c.status for c in r.checks}["record_agrees"] == "pass"  # 4 against 6, within 2


def test_a_record_of_no_doors_disagrees_with_doors_seen():
    from threshold.tools.loading_docks import agree
    assert agree(2, 0) == "warn" and agree(0, 0) == "pass" and agree(4, 6) == "pass"


def test_a_home_is_not_applicable(monkeypatch):
    from threshold.sources import index
    monkeypatch.setattr(index, "rows", lambda: {"h1": {"kind": "house"}})
    r = run_tool("loading_docks", {"scan": "h1"})
    assert r.verdict.status == "unknown" and "home" in r.verdict.text
    assert run_tool("truck_access", {"scan": "h1"}).verdict.status == "unknown"
