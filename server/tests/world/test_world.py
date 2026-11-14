"""World engine checks on small hand-made data (no sponsor data, no network)."""
import numpy as np

from threshold.geometry import georef
from threshold.world import frame, geotiff, mesh, splatfit


def test_frame_matches_georef_with_and_without_the_refit():
    plan = {"geo": {"lat": 29.7, "lon": -95.4, "yaw_deg": 37.0, "translation": {"x": 3.0, "y": -5.0}}}
    for fit in (None, {"verified": True, "rotation_deg": -4.0, "pivot_enu": [1.5, 2.5], "shift_enu": [0.8, -1.1]}):
        plan["geo"]["fit"] = fit
        fr = frame.scan_to_enu(plan)
        for x, y in ((0, 0), (4, 1), (-7, 9)):
            e, n = georef._rot(x, y, fr["rot_deg"])
            assert np.allclose((e + fr["t"][0], n + fr["t"][1]), georef.to_enu(plan, x, y), atol=1e-9)
    assert frame.scan_to_enu({"geo": None}) is None


def test_lonlat_round_trip():
    lon, lat = frame.enu_to_lonlat(34.0, -118.2, 120.0, -45.0)
    assert np.allclose(frame.lonlat_to_enu(34.0, -118.2, lon, lat), (120.0, -45.0), atol=1e-6)


def test_geotiff_round_trip():
    h = np.arange(12, dtype=np.float32).reshape(3, 4)
    for order in "<>":  # Vexcel's files are big-endian
        r = geotiff.read(geotiff.write(h, x0=100.0, y0=50.0, dx=2.0, dy=2.0, e=order))
        assert np.array_equal(r.heights, h) and (r.x0, r.y0, r.dx, r.dy) == (100.0, 50.0, 2.0, 2.0)


def _room():
    """A 4 x 3 x 2.5 m box seen from inside: floor, ceiling and four walls, two triangles each."""
    V = np.array([[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0], [0, 0, 2.5], [4, 0, 2.5], [4, 3, 2.5], [0, 3, 2.5]], np.float32)
    quads = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    F = np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))], np.int32)
    return V, F


def test_layout_gives_every_triangle_its_own_texels():
    V, F = _room()
    F = mesh.face_frames(V, F)
    lay = mesh.layout(V, F, atlas=1024)
    assert lay["uv"].min() >= 0 and lay["uv"].max() <= 1
    seen = np.zeros((1024, 1024), np.int32)
    for i in range(len(F)):
        px, py, _, _ = mesh.cell_texels(int(lay["kw"][i]), int(lay["kh"][i]))[int(lay["slot"][i])]
        seen[lay["y"][i] + py, lay["x"][i] + px] += 1
    assert seen.max() == 1  # no texel belongs to two triangles
    # each corner's texture coordinate lands inside the triangle's own texels
    for i in range(len(F)):
        for u, v in lay["uv"][i]:
            assert seen[int((1 - v) * 1024), int(u * 1024)] == 1


def test_assign_needs_a_clear_line_of_sight_and_a_facing_surface():
    V, F = _room()
    # a second room beyond the x = 4 wall, with its own camera
    V2 = V + np.array([4.0, 0, 0], np.float32)
    Vall, Fall = np.concatenate([V, V2]), np.concatenate([F, F + 8])
    cams = np.array([[2, 1.5, 1.4], [6, 1.5, 1.4]], np.float32)
    Fall = mesh.facing_in(Vall, Fall, cams)
    owner = mesh.assign(Vall, Fall, cams)
    centre_x = Vall[Fall].mean(1)[:, 0]
    assert (owner[centre_x < 3.9] == 0).all() and (owner[centre_x > 4.1] == 1).all()


def test_cube_lookup_reads_the_face_a_direction_points_at():
    cube = np.zeros((6, 8, 8, 3), np.uint8)
    for f in range(6):
        cube[f] = f + 1
    d = np.array([[1, 0, 0], [0, 0, 1], [0, 0, -1], [-1, 0.1, 0]], np.float64)
    assert mesh.cube_lookup(cube, d)[:, 0].tolist() == [2, 1, 6, 4]  # faces 1 (forward), 0 (up), 5 (down), 3 (back)


def test_pack_layout():
    V, F = _room()
    plan = {"floors": [{"elevation": 0.0}, {"elevation": 2.0}]}
    floor = mesh.floor_of(V, F, plan)
    assert floor[0] == 0 and floor[2] == 1  # the floor's triangles, then the ceiling's (above the second floor's start)
    data = mesh.pack(V, F, np.zeros((len(F), 3, 2), np.float32), floor)
    assert data[:4] == mesh.MAGIC and len(data) == 8 + len(F) * 3 * (12 + 4 + 4)


def test_best_shift_and_align_recover_a_known_move():
    rng = np.random.default_rng(1)
    # a "neighbourhood": flat ground with a few boxes of different heights, as points and as a surface grid
    boxes = [(-30, -20, 14, 9, 5.0), (10, 15, 12, 16, 7.0), (25, -35, 8, 8, 4.0), (-45, 30, 10, 20, 9.0)]
    pts = rng.uniform(-80, 80, (120000, 2)).astype(np.float32)
    z = np.zeros(len(pts), np.float32)
    for x, y, w, d, h in boxes:
        z[(np.abs(pts[:, 0] - x) < w / 2) & (np.abs(pts[:, 1] - y) < d / 2)] = h
    bounds, shape = (-80.0, -80.0, 80.0, 80.0), (320, 320)
    dsm = {"heights": np.nan_to_num(splatfit.height_map(pts, z, bounds, shape)) + 20.0, "bounds_enu": bounds, "ground_m": 20.0}
    # the "splat": the same scene turned by -5 degrees and moved, so the fit must turn it +5 and move it back
    c, s = np.cos(np.radians(-5.0)), np.sin(np.radians(-5.0))
    moved = np.stack([(pts[:, 0] - 6.0) * c - (pts[:, 1] + 4.0) * s, (pts[:, 0] - 6.0) * s + (pts[:, 1] + 4.0) * c, z - 1.5], 1)
    out = splatfit.align(moved, dsm)
    assert abs(out["rot_deg"] - 5.0) <= 0.5 and np.allclose(out["t"][:2], (6.0, -4.0), atol=1.0) and out["verified"]
    assert abs(out["t"][2] - 1.5) < 0.2


def test_specks_are_dropped_and_real_pieces_kept():
    V, F = _room()
    big = np.concatenate([F + 8 * i for i in range(40)])       # forty rooms: 480 triangles, each room its own piece of 12
    joined = np.concatenate([big, np.array([[i * 8, (i + 1) * 8, (i + 1) * 8 + 1] for i in range(39)])])  # stitched into one piece
    speck = np.array([[900, 901, 902]])
    kept = mesh.without_specks(np.concatenate([joined, speck]))
    assert len(kept) == len(joined) and 900 not in kept


def test_neighbours_pair_triangles_across_shared_edges_only():
    F = np.array([[0, 1, 2], [2, 1, 3], [4, 5, 6]], np.int32)  # two triangles sharing edge 1-2, and one apart
    n = mesh.neighbours(F)
    assert n[0].tolist() == [1, -1, -1]   # across the edge opposite corner 0 (vertices 1 and 2) lies triangle 1
    assert n[1].tolist() == [-1, -1, 0]   # triangle 1's edge 2-1 is opposite its corner 2 (vertex 3)
    assert n[2].tolist() == [-1, -1, -1]


def test_seams_only_where_owners_differ_and_the_guest_sees_the_triangle():
    V, F = _room()
    cams = np.array([[1, 1.5, 1.4], [3, 1.5, 1.4]], np.float32)
    F = mesh.facing_in(V, F, cams)
    occ = mesh.occupancy(mesh.surface_points(V, F, mesh.VOXEL * 0.6))
    owner = mesh.assign(V, F, cams, occ)
    f, c, p, tau = mesh.seams(V, F, owner, cams, occ)
    assert len(f) > 0 and (owner[f] != p).all() and ((tau >= 0.2) & (tau <= 1)).all()
    assert len(mesh.seams(V, F, np.zeros(len(F), np.int32), cams, occ)[0]) == 0  # one owner everywhere: no seam


def test_gains_bring_two_exposures_together():
    rng = np.random.default_rng(2)
    truth = rng.uniform(0.2, 0.6, (400, 3))
    i, j = np.zeros(400, np.int64), np.ones(400, np.int64)
    g = mesh.gains(i, j, truth * 1.25, truth * 0.8, 2)  # panorama 0 is too bright, panorama 1 too dark
    after = np.abs(truth * 1.25 * g[0] - truth * 0.8 * g[1]).mean()
    assert after < 0.25 * np.abs(truth * 1.25 - truth * 0.8).mean() and g[0, 0] < 1 < g[1, 0]
    assert abs(g[:, 0].mean() - 1) < 1e-6  # the pair keeps its overall brightness


def test_paint_weights_an_owner_fully_and_a_guest_only_near_its_edge():
    V, F = _room()
    F = mesh.face_frames(V, F)
    lay = mesh.layout(V, F, atlas=1024)
    acc, wsum = np.zeros((1024, 1024, 3), np.uint16), np.zeros((1024, 1024), np.uint16)
    cube = [np.full((6, 8, 8, 3), 200, np.uint8)]
    one = np.array([0])
    mesh.paint(acc, wsum, V, F, lay, one, np.array([2, 1.5, 1.4], np.float32), np.eye(3, dtype=np.float32), cube)
    assert set(np.unique(wsum)) == {0, mesh.ONE}
    mesh.paint(acc, wsum, V, F, lay, one, np.array([2, 1.5, 1.4], np.float32), np.eye(3, dtype=np.float32), cube,
               np.array([0]), np.array([0.5], np.float32))
    assert wsum.max() == 2 * mesh.ONE and (wsum == mesh.ONE).any()  # doubled on the seam edge, untouched far from it
    lit = wsum > 0
    assert np.all(acc[lit] // wsum[lit][:, None] == 200)


def test_trim_keeps_the_rooms_and_drops_the_yard_in_an_l_shaped_corner():
    V = np.array([[0.5, 0.5, 0], [1.5, 0.5, 0], [1, 1.5, 0],      # inside the L
                  [7, 7, 0], [8, 7, 0], [7.5, 8, 0],              # in the corner the L leaves open
                  [0.5, 0.5, 9], [1.5, 0.5, 9], [1, 1.5, 9]], np.float32)  # far above the ceiling
    F = np.arange(9, dtype=np.int32).reshape(3, 3)
    plan = {"floors": [{"elevation": 0.0}], "walls": [], "panos": [],
            "rooms": [{"polygon": [[0, 0], [10, 0], [10, 4], [0, 4]], "height": 2.5}, {"polygon": [[0, 4], [4, 4], [4, 10], [0, 10]], "height": 2.5}]}
    assert mesh.trim(V, F, plan).tolist() == [[0, 1, 2]]


def test_a_mesh_of_loose_triangles_is_welded_and_not_mistaken_for_specks():
    V, F = _room()
    loose_V, loose_F = V[F].reshape(-1, 3), np.arange(len(F) * 3, dtype=np.int32).reshape(-1, 3)  # every triangle its own vertices
    assert len(mesh.without_specks(loose_F)) == len(F)          # all "pieces" are tiny: nothing is a speck
    wV, wF = mesh.weld(loose_V, loose_F)
    assert len(wV) == len(V) and (mesh.neighbours(wF) >= 0).any()  # welded, triangles have neighbours again
