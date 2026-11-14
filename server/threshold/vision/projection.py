"""Exact maths between a pixel on a cube face (or an equirectangular image), a direction in the scan frame,
and back.

Frames. The scan frame is ScanPlan's: metres, x and y on the floor, z up. A panorama's camera frame is
also z up. Its `rotation` quaternion (x, y, z, w) turns camera-frame directions into scan-frame directions
(`R(q) @ d_cam`).

Cube faces. Matterport returns six square faces: 0 up, 1 to 4 around the horizon, 5 down. Pixel (u, v)
has u to the right and v down, continuous in [0, size] with 0 at the left or top edge. The face layout
below was measured on 2026-11-13, not assumed (`python -m threshold.vision.verify`): edge continuity
between faces picks the up and down orientation on three of three scans, and ScanPlan doorways projected
through `rotation` land on the doors in the images for <scan-id>, <scan-id> and <scan-id>
(`$THRESHOLD_DATA_DIR/shots/perception/doorways_*.jpg`). The other three face-1 headings miss every door.

Angles. `yaw_deg` is the heading in the scan frame, degrees counterclockwise from +x. `pitch_deg` is
elevation above the horizontal, positive up. Both are what Contract 3's pano anchor carries.
"""
from __future__ import annotations

import math

import numpy as np

# Measured layout (see module docstring). In the camera frame: face 1 looks along `FACE1_YAW_DEG`
# (counterclockwise from camera +x); faces 2, 3, 4 each turn a further 90 degrees clockwise seen from
# above (to the right). For the up and down faces, `*_TOP_YAW_DEG` is the camera-frame heading that
# points to the top edge of the face image.
FACE1_YAW_DEG = 0.0
UP_TOP_YAW_DEG = 180.0
DOWN_TOP_YAW_DEG = 0.0


def quat_matrix(q) -> np.ndarray:
    """Rotation matrix for a unit quaternion given as (x, y, z, w)."""
    x, y, z, w = (float(c) for c in q)
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _h(deg: float) -> np.ndarray:
    a = math.radians(deg)
    return np.array([math.cos(a), math.sin(a), 0.0])


def face_basis(face: int, layout: tuple[float, float, float] | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(forward, right, down) unit vectors of a face's image in the camera frame."""
    f1, up_top, down_top = layout or (FACE1_YAW_DEG, UP_TOP_YAW_DEG, DOWN_TOP_YAW_DEG)
    z = np.array([0.0, 0.0, 1.0])
    if 1 <= face <= 4:
        fwd = _h(f1 - 90.0 * (face - 1))
        right = np.cross(fwd, z)
        return fwd, right, -z
    if face == 0:
        top = _h(up_top)
        down = -top
        return z, np.cross(down, z), down  # looking up: right = down x forward
    if face == 5:
        top = _h(down_top)
        down = -top
        return -z, np.cross(down, -z), down  # right = down x forward, as for every face
    raise ValueError(f"no face {face}")


def face_pixel_to_cam(face: int, u, v, size: int, layout=None) -> np.ndarray:
    """Camera-frame unit direction(s) through pixel (u, v) of a face `size` pixels across (pixel centres at +0.5)."""
    fwd, right, down = face_basis(face, layout)
    a = 2 * (np.asarray(u, float)) / size - 1
    b = 2 * (np.asarray(v, float)) / size - 1
    d = fwd + a[..., None] * right + b[..., None] * down
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def cam_to_face_pixel(d_cam, size: int, layout=None) -> tuple[int, float, float]:
    """The face a camera-frame direction hits, and its pixel (u, v)."""
    d = np.asarray(d_cam, float)
    best = None
    for face in range(6):
        fwd, right, down = face_basis(face, layout)
        t = float(d @ fwd)
        if t <= 0:
            continue
        if best is None or t > best[0]:
            best = (t, face, fwd, right, down)
    t, face, fwd, right, down = best
    p = d / t
    return face, (float(p @ right) + 1) * size / 2, (float(p @ down) + 1) * size / 2


def cam_to_scan(d_cam, rotation) -> np.ndarray:
    return quat_matrix(rotation) @ np.asarray(d_cam, float) if rotation else np.asarray(d_cam, float)


def scan_to_cam(d_scan, rotation) -> np.ndarray:
    return quat_matrix(rotation).T @ np.asarray(d_scan, float) if rotation else np.asarray(d_scan, float)


def yaw_pitch(d) -> tuple[float, float]:
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    return math.degrees(math.atan2(d[1], d[0])), math.degrees(math.asin(max(-1.0, min(1.0, d[2]))))


def direction(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    return np.array([math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)])


# ---- the high-level conversions everyone else uses ---------------------------------------------

def face_pixel_to_scan(face: int, u: float, v: float, size: int, rotation, layout=None) -> np.ndarray:
    """Scan-frame unit direction through pixel (u, v) of a face."""
    return cam_to_scan(face_pixel_to_cam(face, u, v, size, layout), rotation)


def scan_to_face_pixel(d_scan, size: int, rotation, layout=None) -> tuple[int, float, float]:
    return cam_to_face_pixel(scan_to_cam(d_scan, rotation), size, layout)


def point_to_face_pixel(point, camera, size: int, rotation, layout=None) -> tuple[int, float, float]:
    """Where a scan-frame 3D point appears from a panorama at `camera` (its position)."""
    return scan_to_face_pixel(np.asarray(point, float) - np.asarray(camera, float), size, rotation, layout)


def equirect_to_scan(x: float, y: float, width: int, height: int, rotation) -> np.ndarray:
    """Equirectangular pixel to scan-frame direction. Column 0 is camera-frame heading +180 deg, the centre
    column is heading 0 (camera +x); headings decrease to the right, as on any panorama viewed from inside."""
    yaw = 180.0 - 360.0 * x / width
    pitch = 90.0 - 180.0 * y / height
    return cam_to_scan(direction(yaw, pitch), rotation)


def scan_to_equirect(d_scan, width: int, height: int, rotation) -> tuple[float, float]:
    yaw, pitch = yaw_pitch(scan_to_cam(d_scan, rotation))
    return ((180.0 - yaw) / 360.0 * width) % width, (90.0 - pitch) / 180.0 * height
