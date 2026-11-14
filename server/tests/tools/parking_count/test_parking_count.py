from _site.fakes import LAT, ll, square_wkt
from shapely import wkt

from threshold.tools._site import metres
from threshold.tools.parking_count import stalls_from


def stall(cx, cy, w, h, conf="high"):
    lon, lat = ll(cx, cy)
    return {"label": "parking space", "image": "spherical-ortho", "confidence": conf, "anchor": {"geo": [lon, lat]},
            "polygon": square_wkt(cx, cy, w, h)}


def test_singles_rows_and_lots():
    area = metres(wkt.loads(square_wkt(0, 0, 200)), LAT)
    dets = [stall(0, 0, 2.7, 5.5), stall(0.2, 0, 2.7, 5.5, "low"),     # one stall boxed twice
            stall(10, 0, 2.7, 5.5),
            stall(0, 20, 27, 5.5),                                     # a row of ten
            stall(1, 20, 2.7, 5.5),                                    # a stall inside that row
            stall(0, 60, 40, 40),                                      # a whole lot: dropped
            stall(500, 500, 2.7, 5.5)]                                 # off the parcel
    st = stalls_from(dets, area, LAT)
    assert len(st["singles"]) == 2 and [r["n"] for r in st["rows"]] == [10] and len(st["dropped"]) == 1
    assert st["count"] == 12
