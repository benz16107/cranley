"""Still frames from a walk-through video, with ffmpeg. Frames are cached beside the capture."""
from __future__ import annotations

import json
import shutil
import subprocess

from . import store

FRAME_PX = 1024
MAX_SECONDS = 180   # a walk-through longer than this is sampled over its first three minutes


def duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, timeout=60)
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError):
        return 0.0  # a recording straight from a browser often has no duration in its header


def extract(cid: str, n: int = 8, root=None) -> list[tuple[float, bytes]]:
    """`n` frames spread evenly over a video capture: [(seconds from the start, JPEG bytes)]."""
    if not shutil.which("ffmpeg"):
        raise LookupError("ffmpeg is not installed on the server, so videos cannot be read")
    src = store.path(cid, root)
    if src is None:
        raise LookupError(f"capture {cid} has no file")
    d = src.with_suffix(".frames")
    # the first extraction wins: frame files are named by index, and findings point at "capture#index"
    marker = next(d.glob("n*.json"), None) or d / f"n{n}.json"
    if not marker.exists():
        d.mkdir(exist_ok=True)
        length = min(duration(src), MAX_SECONDS)
        if length <= 0:  # no duration in the header: decode once to count it
            probe = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-f", "null", "-", "-stats"],
                                   capture_output=True, text=True, timeout=300)
            import re
            t = re.findall(r"time=(\d+):(\d+):([\d.]+)", probe.stderr)
            length = min(sum(float(x) * k for x, k in zip(t[-1], (3600, 60, 1))), MAX_SECONDS) if t else 0.0
        times = [round(length * (i + 0.5) / n, 2) for i in range(n)] if length > 0 else [0.0]
        for i, t in enumerate(times):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(src), "-frames:v", "1",
                            "-vf", f"scale='min({FRAME_PX},iw)':-2", "-q:v", "4", str(d / f"{i}.jpg")],
                           capture_output=True, timeout=120)
        times = [t for i, t in enumerate(times) if (d / f"{i}.jpg").exists()]
        marker.write_text(json.dumps(times))
    times = json.loads(marker.read_text())
    return [(t, (d / f"{i}.jpg").read_bytes()) for i, t in enumerate(times) if (d / f"{i}.jpg").exists()]


def frame(cid: str, i: int, root=None) -> bytes:
    src = store.path(cid, root)
    f = src.with_suffix(".frames") / f"{int(i)}.jpg" if src else None
    if f is None or not f.exists():
        raise LookupError("no such frame")
    return f.read_bytes()
