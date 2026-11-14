"""The smallest GeoTIFF reader that opens Vexcel's elevation rasters: one band of 32-bit floats, either byte order,
tiles or strips, deflate or no compression, placed by a tiepoint and a pixel scale in Web Mercator metres.

Pillow reads the pixels but trips over the file's XMP tag, and a raster library is a large dependency for one
file shape. Anything this does not understand raises ValueError; nothing is guessed.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

import numpy as np

_TYPES = {1: "B", 2: "c", 3: "H", 4: "I", 5: "II", 11: "f", 12: "d", 16: "Q"}
_DEFLATE = (8, 32946)


@dataclass
class Raster:
    """heights[row, col] with row 0 at the north edge; (x, y) of a pixel centre is the Mercator point
    (x0 + (col + 0.5) * dx, y0 - (row + 0.5) * dy). Missing cells are NaN."""
    heights: np.ndarray
    x0: float
    y0: float
    dx: float
    dy: float


def read(data: bytes) -> Raster:
    e = {b"II": "<", b"MM": ">"}.get(data[:2])  # Vexcel writes big-endian
    if e is None or struct.unpack_from(e + "H", data, 2)[0] != 42:
        raise ValueError("not a TIFF")
    (ifd,) = struct.unpack_from(e + "I", data, 4)
    (n,) = struct.unpack_from(e + "H", data, ifd)
    tags: dict[int, tuple] = {}
    for i in range(n):
        tag, typ, count, raw = struct.unpack_from(e + "HHI4s", data, ifd + 2 + 12 * i)
        if typ not in _TYPES:
            continue
        fmt = e + _TYPES[typ] * count
        size = struct.calcsize(fmt)
        tags[tag] = struct.unpack_from(fmt, raw if size <= 4 else data, 0 if size <= 4 else struct.unpack(e + "I", raw)[0])
    one = lambda t, d=None: tags[t][0] if t in tags else d  # noqa: E731
    w, h = one(256), one(257)
    if one(258) != 32 or one(339) != 3 or one(277, 1) != 1 or one(317, 1) != 1:
        raise ValueError("expected one band of 32-bit floats with no predictor")
    comp = one(259, 1)
    if comp != 1 and comp not in _DEFLATE:
        raise ValueError(f"compression {comp} is not handled")
    unpack = (lambda b: b) if comp == 1 else zlib.decompress
    out = np.full((h, w), np.nan, np.float32)
    if 324 in tags:  # tiles
        tw, th = one(322), one(323)
        for i, (off, size) in enumerate(zip(tags[324], tags[325])):
            r, c = (i // -(-w // tw)) * th, (i % -(-w // tw)) * tw
            tile = np.frombuffer(unpack(data[off:off + size]), e + "f4").reshape(th, tw)
            out[r:r + th, c:c + tw] = tile[:h - r, :w - c]
    else:  # strips
        rows = one(278, h)
        for i, (off, size) in enumerate(zip(tags[273], tags[279])):
            strip = np.frombuffer(unpack(data[off:off + size]), e + "f4").reshape(-1, w)
            out[i * rows:i * rows + len(strip)] = strip
    nodata = b"".join(tags[42113]).rstrip(b"\x00").decode() if 42113 in tags else None
    if nodata:
        out[out == np.float32(float(nodata))] = np.nan
    if 33550 not in tags or 33922 not in tags:
        raise ValueError("no tiepoint and pixel scale")
    (dx, dy, _), (i, j, _, x, y, _) = tags[33550], tags[33922][:6]
    return Raster(out, x - i * dx, y + j * dy, dx, dy)


def write(heights: np.ndarray, x0: float, y0: float, dx: float, dy: float, e: str = "<") -> bytes:
    """A one-strip, uncompressed file `read` accepts, in either byte order. For tests."""
    h, w = heights.shape
    body = heights.astype(e + "f4").tobytes()
    scale, tie = struct.pack(e + "3d", dx, dy, 0.0), struct.pack(e + "6d", 0.0, 0.0, 0.0, x0, y0, 0.0)
    entries = [(256, 4, 1, w), (257, 4, 1, h), (258, 3, 1, 32), (259, 3, 1, 1), (273, 4, 1, 8), (277, 3, 1, 1),
               (278, 4, 1, h), (279, 4, 1, len(body)), (339, 3, 1, 3),
               (33550, 12, 3, 8 + len(body)), (33922, 12, 6, 8 + len(body) + len(scale))]
    ifd = 8 + len(body) + len(scale) + len(tie)
    out = (b"II" if e == "<" else b"MM") + struct.pack(e + "HI", 42, ifd) + body + scale + tie + struct.pack(e + "H", len(entries))
    for tag, typ, count, value in entries:
        out += struct.pack(e + "HHI", tag, typ, count) + (struct.pack(e + "HH", value, 0) if typ == 3 else struct.pack(e + "I", value))
    return out + struct.pack(e + "I", 0)
