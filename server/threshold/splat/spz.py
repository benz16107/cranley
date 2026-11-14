"""Read a 3DGS .ply (as Brush writes it) and pack it as Niantic's .spz, version 2, for the web.

The layout follows Niantic's reference loader (github.com/nianticlabs/spz, MIT): a 16 byte header, then positions
as 24 bit fixed point, alphas, colours, scales, rotations (x, y, z of a unit quaternion with w >= 0) and SH
coefficients, each a block over all points, the whole file gzipped. Coordinates are written exactly as the .ply has
them: no axis change, so both files are in the scan frame.
"""
from __future__ import annotations

import gzip
import struct
from pathlib import Path

import numpy as np

MAGIC = 0x5053474E
FRACTIONAL_BITS = 12   # 1/4096 m steps, positions within +-2 km
COLOR_SCALE = 0.15
SH_DIMS = {0: 0, 1: 3, 2: 8, 3: 15}


def read_ply(path: Path) -> dict[str, np.ndarray]:
    """Float32 columns by name of a binary little-endian .ply with one vertex element of floats."""
    data = Path(path).read_bytes()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    head = data[:end].decode().splitlines()
    n = int(next(l for l in head if l.startswith("element vertex")).split()[2])
    props = [l.split()[2] for l in head if l.startswith("property")]
    if any(l.split()[1] != "float" for l in head if l.startswith("property")):
        raise ValueError("expected float properties only")
    a = np.frombuffer(data, np.float32, n * len(props), end).reshape(n, len(props))
    return {k: a[:, i] for i, k in enumerate(props)}


def write_ply(path: Path, cols: dict[str, np.ndarray]) -> None:
    n = len(next(iter(cols.values())))
    head = ["ply", "format binary_little_endian 1.0", f"element vertex {n}", *(f"property float {k}" for k in cols), "end_header"]
    body = np.stack([np.asarray(v, np.float32) for v in cols.values()], 1)
    Path(path).write_bytes(("\n".join(head) + "\n").encode() + body.astype("<f4").tobytes())


def sh_degree(cols: dict) -> int:
    rest = sum(k.startswith("f_rest_") for k in cols)
    return {v * 3: d for d, v in SH_DIMS.items()}[rest]


def _u8(x) -> np.ndarray:
    return np.clip(np.round(x), 0, 255).astype(np.uint8)


def _sh_quant(x: np.ndarray, bucket: int) -> np.ndarray:
    q = np.clip(np.round(x * 128) + 128, 0, 255)
    return np.clip(np.floor((q + bucket / 2) / bucket) * bucket, 0, 255).astype(np.uint8)


def encode(cols: dict[str, np.ndarray]) -> bytes:
    n = len(cols["x"])
    deg = sh_degree(cols)
    xyz = np.stack([cols["x"], cols["y"], cols["z"]], 1).astype(np.float64)
    fixed = np.round(xyz * (1 << FRACTIONAL_BITS)).astype(np.int32).reshape(-1)
    pos = (fixed.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3]).reshape(-1)  # low 3 bytes, two's complement
    alpha = _u8(255 / (1 + np.exp(-cols["opacity"].astype(np.float64))))
    dc = np.stack([cols[f"f_dc_{i}"] for i in range(3)], 1)
    colour = _u8(dc * (COLOR_SCALE * 255) + 0.5 * 255).reshape(-1)
    scale = _u8((np.stack([cols[f"scale_{i}"] for i in range(3)], 1) + 10) * 16).reshape(-1)
    q = np.stack([cols[f"rot_{i}"] for i in range(4)], 1).astype(np.float64)  # w, x, y, z
    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    q *= np.where(q[:, :1] < 0, -1, 1)
    rot = _u8(q[:, 1:] * 127.5 + 127.5).reshape(-1)
    parts = [struct.pack("<IIIBBBB", MAGIC, 2, n, deg, FRACTIONAL_BITS, 0, 0), pos.tobytes(), alpha.tobytes(),
             colour.tobytes(), scale.tobytes(), rot.tobytes()]
    dims = SH_DIMS[deg]
    if dims:
        # .ply keeps each channel's coefficients together (f_rest_{c * dims + j}); .spz keeps rgb together per coefficient
        sh = np.stack([np.stack([cols[f"f_rest_{c * dims + j}"] for c in range(3)], 1) for j in range(dims)], 1)
        out = np.empty(sh.shape, np.uint8)
        out[:, :3] = _sh_quant(sh[:, :3], 8)
        out[:, 3:] = _sh_quant(sh[:, 3:], 16)
        parts.append(out.reshape(-1).tobytes())
    return gzip.compress(b"".join(parts), compresslevel=6)


def ply_to_spz(ply: Path, spz: Path) -> int:
    """Write spz from ply; returns the number of splats."""
    cols = read_ply(ply)
    tmp = spz.with_suffix(".spz.tmp")
    tmp.write_bytes(encode(cols))
    tmp.replace(spz)
    return len(cols["x"])
