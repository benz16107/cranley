import gzip
import json
import struct

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from threshold.api import interior_splat
from threshold.splat import dataset, seed, spz
from threshold.vision.projection import cam_to_face_pixel, quat_matrix


def _quat_from(R):
    from threshold.splat.dataset import rot_to_qvec
    w, x, y, z = rot_to_qvec(R)
    return [x, y, z, w]


@pytest.mark.parametrize("face", range(6))
def test_colmap_pose_projects_like_the_measured_face_layout(face):
    rng = np.random.default_rng(face)
    rotation = rng.normal(size=4)
    rotation /= np.linalg.norm(rotation)
    centre = np.array([1.0, -2.0, 1.4])
    R, t = dataset.face_pose(centre, rotation, face)
    n = 512
    hits = 0
    for _ in range(200):
        p = centre + rng.normal(size=3) * 3
        k, u, v = cam_to_face_pixel(quat_matrix(rotation).T @ (p - centre), n)
        if k != face:
            continue
        pc = R @ p + t
        assert pc[2] > 0
        assert np.allclose([pc[0] / pc[2] * n / 2 + n / 2, pc[1] / pc[2] * n / 2 + n / 2], [u, v], atol=1e-6)
        hits += 1
    assert hits > 5


def test_qvec_round_trips():
    rng = np.random.default_rng(3)
    for _ in range(50):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        R = quat_matrix(q)
        assert np.allclose(quat_matrix(_quat_from(R)), R, atol=1e-9)


def test_held_out_sweeps_land_on_the_eval_indices():
    panos = [f"p{i:02d}" for i in range(19)]
    seq, period, held = dataset.order(panos, 8)
    ev = [i for i, (p, _) in enumerate(seq) if p in held]
    assert ev == list(range(0, len(seq), period))
    assert len(ev) == 6 * len(held) and len(set(seq)) == len(seq)
    dropped = {(p, f) for p in panos for f in range(6)} - set(seq)
    assert all(f == 5 for _, f in dropped)
    assert dataset.order(panos, 0)[1] == 0


def test_visibility_hides_a_point_behind_a_wall():
    ys, zs = np.meshgrid(np.linspace(-1, 1, 80), np.linspace(-1, 1, 80))
    wall = np.stack([np.full(ys.size, 2.0), ys.ravel(), zs.ravel()], 1)
    pts = np.vstack([wall, [[4.0, 0.0, 0.0], [1.0, 0.0, 0.0]]])
    seen = seed.visible(pts, np.zeros(3))
    assert not seen[-2] and seen[-1] and seen[:-2].mean() > 0.95


def _decode(data: bytes, dims: int):
    raw = gzip.decompress(data)
    magic, ver, n, deg, frac, _, _ = struct.unpack("<IIIBBBB", raw[:16])
    o = 16
    b = np.frombuffer(raw, np.uint8, n * 9, o).reshape(n * 3, 3).astype(np.int32); o += n * 9
    v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
    v = np.where(v & 0x800000, v - (1 << 24), v)
    xyz = (v / (1 << frac)).reshape(n, 3)
    alpha = np.frombuffer(raw, np.uint8, n, o) / 255; o += n
    rgb = np.frombuffer(raw, np.uint8, n * 3, o).reshape(n, 3); o += n * 3
    scale = np.frombuffer(raw, np.uint8, n * 3, o).reshape(n, 3) / 16 - 10; o += n * 3
    rot = np.frombuffer(raw, np.uint8, n * 3, o).reshape(n, 3) / 127.5 - 1; o += n * 3
    sh = np.frombuffer(raw, np.uint8, n * dims * 3, o).reshape(n, dims, 3)
    return magic, ver, deg, xyz, alpha, rgb, scale, rot, sh, len(raw) - o - n * dims * 3


def test_spz_round_trip():
    rng = np.random.default_rng(0)
    n, dims = 100, 8
    q = rng.normal(size=(n, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    cols = {"x": rng.uniform(-20, 20, n), "y": rng.uniform(-20, 20, n), "z": rng.uniform(-3, 6, n),
            "opacity": rng.normal(size=n), **{f"rot_{i}": q[:, i] for i in range(4)},
            **{f"scale_{i}": rng.uniform(-6, -1, n) for i in range(3)},
            **{f"f_dc_{i}": rng.uniform(-1, 1, n) for i in range(3)},
            **{f"f_rest_{i}": rng.uniform(-0.3, 0.3, n) for i in range(3 * dims)}}
    cols = {k: np.asarray(v, np.float32) for k, v in cols.items()}
    magic, ver, deg, xyz, alpha, rgb, scale, rot, sh, left = _decode(spz.encode(cols), dims)
    assert (magic, ver, deg, left) == (spz.MAGIC, 2, 2, 0)
    assert np.abs(xyz - np.stack([cols["x"], cols["y"], cols["z"]], 1)).max() < 1e-3
    assert np.abs(alpha - 1 / (1 + np.exp(-cols["opacity"]))).max() < 0.01
    assert np.abs(scale - np.stack([cols[f"scale_{i}"] for i in range(3)], 1)).max() < 0.04
    assert np.abs((rgb / 255 - 0.5) / spz.COLOR_SCALE - np.stack([cols[f"f_dc_{i}"] for i in range(3)], 1)).max() < 0.03
    sign = np.where(q[:, :1] < 0, -1, 1)
    assert np.abs(rot - q[:, 1:] * sign).max() < 0.01
    # coefficient j of channel c is f_rest_{c * dims + j}
    assert np.abs((sh[:, 4, 1].astype(float) - 128) / 128 - cols[f"f_rest_{dims + 4}"]).max() < 16 / 128


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(interior_splat, "ROOT", tmp_path)
    app = FastAPI()
    app.include_router(interior_splat.router)
    return TestClient(app), tmp_path


def test_route_404_until_trained(client):
    c, _ = client
    assert c.get("/api/scan/abcdefghijk/interior-splat").status_code == 404
    assert c.get("/api/scan/abcdefghijk/interior-splat.json").status_code == 404


def test_route_serves_ranges_and_sidecar(client):
    c, root = client
    (root / "abcdefghijk").mkdir()
    body = bytes(range(256)) * 10
    (root / "abcdefghijk" / "interior.spz").write_bytes(body)
    (root / "abcdefghijk" / "interior.json").write_text(json.dumps({"to_scanplan": "identity"}))
    full = c.get("/api/scan/abcdefghijk/interior-splat")
    assert full.status_code == 200 and full.content == body
    part = c.get("/api/scan/abcdefghijk/interior-splat", headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == body[10:20]
    assert part.headers["content-range"] == f"bytes 10-19/{len(body)}"
    assert c.get("/api/scan/abcdefghijk/interior-splat", headers={"Range": "bytes=99999-"}).status_code == 416
    assert c.get("/api/scan/abcdefghijk/interior-splat?format=ply").status_code == 404
    assert c.get("/api/scan/abcdefghijk/interior-splat.json").json() == {"to_scanplan": "identity"}
