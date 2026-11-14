"""Pure maths: projection, locating against a hand-made room, and the ortho pixel transform. No network."""
import math

import numpy as np
import pytest

from threshold.aerial.site import Ortho, square
from threshold.vision import locate as loc
from threshold.vision import projection as pj

S = 1000


def z_quat(deg):
    a = math.radians(deg) / 2
    return [0.0, 0.0, math.sin(a), math.cos(a)]


@pytest.mark.parametrize("face", range(6))
def test_face_round_trip(face):
    rng = np.random.default_rng(face)
    rot = [0.01, -0.02, 0.6, 0.8]
    for u, v in rng.uniform(5, S - 5, size=(50, 2)):
        d = pj.face_pixel_to_scan(face, u, v, S, rot)
        f, u2, v2 = pj.scan_to_face_pixel(d, S, rot)
        assert f == face and abs(u - u2) < 1e-6 and abs(v - v2) < 1e-6


def test_face_centres_in_camera_frame():
    centre = lambda f: pj.face_pixel_to_cam(f, S / 2, S / 2, S)
    assert np.allclose(centre(1), [1, 0, 0])
    assert np.allclose(centre(2), [0, -1, 0])  # faces turn to the right (clockwise seen from above)
    assert np.allclose(centre(3), [-1, 0, 0])
    assert np.allclose(centre(4), [0, 1, 0])
    assert np.allclose(centre(0), [0, 0, 1])
    assert np.allclose(centre(5), [0, 0, -1])


def test_side_faces_upright_and_left_to_right():
    # top of a side face points up; its right edge meets the next face's left edge
    assert pj.face_pixel_to_cam(1, S / 2, 0, S)[2] > 0
    for k in range(1, 5):
        nxt = k % 4 + 1
        assert np.allclose(pj.face_pixel_to_cam(k, S, 300, S), pj.face_pixel_to_cam(nxt, 0, 300, S))


@pytest.mark.parametrize("k", range(1, 5))
def test_measured_cap_layout_shares_edges(k):
    # The up face's edges meet every side face's top edge, and the down face its bottom edge: the measured
    # layout makes the shared edges coincide pixel for pixel along their length.
    for u in (10, 500, 990):
        top = pj.face_pixel_to_cam(k, u, 0, S)
        f, _, _ = pj.cam_to_face_pixel(top + np.array([0, 0, 1e-3]), S)
        assert f == 0
        bottom = pj.face_pixel_to_cam(k, u, S, S)
        f, _, _ = pj.cam_to_face_pixel(bottom - np.array([0, 0, 1e-3]), S)
        assert f == 5
    # face 1's top edge is the up face's bottom edge, left to right
    assert np.allclose(pj.face_pixel_to_cam(1, 200, 0, S), pj.face_pixel_to_cam(0, 200, S, S))
    assert np.allclose(pj.face_pixel_to_cam(1, 200, S, S), pj.face_pixel_to_cam(5, 200, 0, S))


def test_rotation_turns_camera_heading_into_scan_heading():
    d = pj.face_pixel_to_scan(1, S / 2, S / 2, S, z_quat(30))
    assert pj.yaw_pitch(d) == pytest.approx((30.0, 0.0), abs=1e-9)
    # a point 2 m north-east-ish of the camera lands on the face that looks at it
    f, u, v = pj.point_to_face_pixel([1 + 2 * math.cos(math.radians(30)), 2 * math.sin(math.radians(30)), 1.5],
                                     [1, 0, 1.5], S, z_quat(30))
    assert (f, round(u), round(v)) == (1, S // 2, S // 2)


def test_equirect_round_trip_and_centre():
    rot = z_quat(-75)
    w, h = 2048, 1024
    assert pj.yaw_pitch(pj.equirect_to_scan(w / 2, h / 2, w, h, rot)) == pytest.approx((-75, 0), abs=1e-9)
    for x, y in [(10, 500), (1500, 100), (700, 900)]:
        x2, y2 = pj.scan_to_equirect(pj.equirect_to_scan(x, y, w, h, rot), w, h, rot)
        assert (x2, y2) == pytest.approx((x, y), abs=1e-6)


def test_direction_and_yaw_pitch_inverse():
    for yaw, pitch in [(0, 0), (135, -20), (-90, 60)]:
        assert pj.yaw_pitch(pj.direction(yaw, pitch)) == pytest.approx((yaw, pitch))


# ---- locate against a hand-made 4 m square room, 2.5 m high, camera at the centre 1.5 m up ----

def room_plan(height=2.5, walls=True):
    corners = [[-2, -2], [2, -2], [2, 2], [-2, 2]]
    ws = [{"id": f"w{i}", "floor": "f", "a": corners[i], "b": corners[(i + 1) % 4], "type": "wall"} for i in range(4)]
    return {"sid": "test", "floors": [{"id": "f", "sequence": 0}], "walls": ws if walls else [],
            "rooms": [{"id": "r", "floor": "f", "polygon": corners, "height": height, "walls": [w["id"] for w in ws] if walls else []}],
            "panos": [{"id": "p", "floor": "f", "room": "r", "position": [0.0, 0.0, 1.5], "rotation": z_quat(90)}]}


def test_locate_floor_under_camera():
    plan = room_plan()
    out = loc.locate(plan, plan["panos"][0], 5, [495, 495, 505, 505], S)
    assert out["surface"] == "floor" and out["point_anchor"]["point"] == pytest.approx([0, 0, 0], abs=0.01)
    assert out["anchor"]["pitch_deg"] == pytest.approx(-90, abs=1)


def test_locate_ceiling_and_wall():
    plan = room_plan()
    pano = plan["panos"][0]
    up = loc.locate(plan, pano, 0, [495, 495, 505, 505], S)
    assert up["surface"] == "ceiling" and up["point_anchor"]["point"][2] == pytest.approx(2.5)
    # face 1 looks along scan +y (rotation 90 deg); a box at the horizon hits the wall y = 2
    wall = loc.locate(plan, pano, 1, [480, 480, 520, 500], S)
    assert wall["surface"] == "wall" and wall["point_anchor"]["point"][1] == pytest.approx(2.0)
    assert wall["anchor"]["yaw_deg"] == pytest.approx(90, abs=0.5)


def test_locate_without_shell_keeps_direction_only_for_ceiling():
    plan = room_plan(height=None, walls=False)
    plan["rooms"][0]["polygon"] = []
    out = loc.locate(plan, plan["panos"][0], 0, [495, 495, 505, 505], S)
    assert out["point_anchor"] is None and out["anchor"]["pitch_deg"] == pytest.approx(90, abs=1)


def test_floor_z_from_camera_heights():
    plan = room_plan()
    plan["floors"].append({"id": "g", "sequence": 1})
    plan["panos"].append({"id": "q", "floor": "g", "room": None, "position": [0, 0, 4.3], "rotation": None})
    assert loc.floor_z(plan, "g") == pytest.approx(2.8)


# ---- aerial ----

def test_ortho_transform_round_trip():
    w, s, e, n = -95.1368, 29.5660, -95.1363, 29.5665
    o = Ortho(b"", 600, 690, (w, s, e, n))
    assert o.to_px(w, n) == pytest.approx((0, 0))
    assert o.to_px(e, s) == pytest.approx((600, 690))
    lon, lat = o.to_lonlat(123.4, 456.7)
    assert o.to_px(lon, lat) == pytest.approx((123.4, 456.7))
    assert o.metres_per_px == pytest.approx(0.0806, abs=1e-3)


def test_square_is_size_metres():
    from shapely import wkt

    from threshold.aerial.site import area_m2
    assert area_m2(wkt.loads(square(29.56, -95.13, 60)), 29.56) == pytest.approx(3600, rel=0.01)


def test_rays_meet_at_one_object_seen_from_two_panoramas():
    from threshold.vision.reader import rays_meet
    obj = np.array([2.0, 1.0, 0.5])
    a, b = np.array([0.0, 0.0, 1.5]), np.array([4.0, -1.0, 1.4])
    unit = lambda v: v / np.linalg.norm(v)
    t = rays_meet(a, unit(obj - a), b, unit(obj - b))
    assert t == pytest.approx((np.linalg.norm(obj - a), np.linalg.norm(obj - b)))
    assert rays_meet(a, unit(obj - a), b, unit(obj + [0, 1.0, 0] - b)) is None  # 1 m apart: two objects
    assert rays_meet(a, unit(a - obj), b, unit(obj - b)) is None  # behind the first camera


def test_ray_passes_through_a_doorway_into_the_next_room():
    plan = room_plan()
    plan["openings"] = [{"id": "d", "wall": "w2", "floor": "f", "type": "doorway", "width": 1.0, "height": 2.1,
                         "sill": 0.0, "center": [0.0, 2.0], "rooms": ["r", "r2"]}]
    plan["walls"][2]["openings"] = ["d"]
    plan["walls"].append({"id": "far", "floor": "f", "a": [-2, 4], "b": [2, 4], "type": "wall"})
    out = loc.locate(plan, plan["panos"][0], 1, [490, 480, 510, 500], S)  # face 1 looks along +y
    assert out["surface"] == "wall" and out["point_anchor"]["point"][1] == pytest.approx(4.0)
    # beside the doorway the near wall still stops the ray
    side = loc.locate(plan, plan["panos"][0], 1, [140, 480, 160, 500], S)
    assert side["point_anchor"]["point"][1] == pytest.approx(2.0)
