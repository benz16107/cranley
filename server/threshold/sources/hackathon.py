"""The hackathon site: splats, sky cubemaps and drone photos for the 232 scans with `splat == yes`.

`<site>/resources/<sid>/<file>` redirects to a signed link that lasts an hour, so the browser never gets one:
this server follows it and serves the bytes.

The splat CDN ignores Range (it answers 200 with the whole file, gzip-encoded, whatever the request asks;
checked 2026-11-13). So a splat is downloaded once into the cache, and Range is served from that file, including
while the download is still running: a request for the first 60 MB is answered as soon as 60 MB have arrived.
Drone photos do honour Range, which is how their GPS is read from the first 48 KB.
"""
from __future__ import annotations

import io
import json
import re
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import httpx
from PIL import Image, ImageOps

from ..config import env
from .upstream import cache_path, cached, check, one_flight, send

DEFAULT_SITE = "https://beta-app.matterport.com/2026-princeton-hackathon"
XMP_BYTES = 48 * 1024
ENVMAP = ("px", "nx", "py", "ny", "pz", "nz")
_resize = threading.Semaphore(3)  # a 20 megapixel JPEG takes about 100 MB to decode


def _site() -> str:
    return (env().get("HACKATHON_SITE") or DEFAULT_SITE).rstrip("/")


def _auth() -> tuple[str, str] | None:
    e = env()
    return (e["HACKATHON_SITE_USER"], e["HACKATHON_SITE_PASSWORD"]) if e.get("HACKATHON_SITE_USER") and e.get("HACKATHON_SITE_PASSWORD") else None


def _get(path: str, *, stream: bool = False, headers: dict | None = None) -> httpx.Response:
    try:
        return send("GET", f"{_site()}/{path}", stream=stream, headers=headers, auth=_auth())
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            raise LookupError("the hackathon site wants a password: set HACKATHON_SITE_USER and HACKATHON_SITE_PASSWORD") from None
        if code == 404:
            raise LookupError("this scan has no splat or drone photos (only the scans with splat == yes do)") from None
        raise


def catalog(sid: str) -> dict:
    """The site's catalog entry: segment, splatBytes, images (drone photo file names)."""
    check(sid, "sid")
    return json.loads(cached(cache_path("site", f"{sid}.json"), lambda: json.dumps(_get(f"api/models/{sid}").json()).encode()))


# --- drone photos ---
def _read_head(path: str, n: int) -> bytes:
    """The first n bytes of a file. Asks for a range, and stops reading at n even if the server sends everything."""
    r = _get(path, stream=True, headers={"Range": f"bytes=0-{n - 1}", "Accept-Encoding": "identity"})
    try:
        buf = b""
        for chunk in r.iter_raw():
            buf += chunk
            if len(buf) >= n:
                break
        return buf[:n]
    finally:
        r.close()


def _xmp(head: bytes) -> dict:
    tags = {k.decode(): v.decode() for k, v in re.findall(rb'drone-dji:(\w+)="([^"]*)"', head)}
    num = lambda k: float(tags[k]) if k in tags else None  # noqa: E731
    return {"lat": num("GpsLatitude"), "lon": num("GpsLongitude"), "alt": num("RelativeAltitude"),
            "alt_abs": num("AbsoluteAltitude"), "gimbal_yaw_deg": num("GimbalYawDegree"),
            "gimbal_pitch_deg": num("GimbalPitchDegree"), "flight_yaw_deg": num("FlightYawDegree"),
            "gimbal_roll_deg": num("GimbalRollDegree"), "gps_status": tags.get("GpsStatus"),
            "product": tags.get("ProductName"),
            "rtk_std_hgt": num("RtkStdHgt"),
            # calibrated pinhole intrinsics, in pixels of the full-size original
            "focal_px": num("CalibratedFocalLength"), "cx_px": num("CalibratedOpticalCenterX"),
            "cy_px": num("CalibratedOpticalCenterY"),
            # the laser range finder's hit along the optical axis; altitudes in the same frames as alt and alt_abs
            "lrf_status": tags.get("LRFStatus"), "lrf_m": num("LRFTargetDistance"), "lrf_lat": num("LRFTargetLat"),
            "lrf_lon": num("LRFTargetLon"), "lrf_alt": num("LRFTargetAlt"), "lrf_alt_abs": num("LRFTargetAbsAlt")}


def _drone_meta(sid: str, name: str) -> dict:
    raw = cached(cache_path("drone", sid, "meta3", f"{name}.json"),
                 lambda: json.dumps(_xmp(_read_head(f"resources/{sid}/drone-imagery/{name}", XMP_BYTES))).encode())
    return {"name": name, **json.loads(raw)}


def drone_list(sid: str, n: int = 60) -> dict:
    """Drone photos with GPS (degrees), height above take-off (m), gimbal angles (degrees), calibrated intrinsics and
    the laser range finder's target. Reading each photo's
    position costs one small request, so `n` photos spread evenly through the flight are described; n=0 is all of them."""
    names = catalog(sid).get("images") or []
    step = max(1, -(-len(names) // n)) if n else 1
    pick = names[::step]
    with ThreadPoolExecutor(8) as pool:
        photos = list(pool.map(lambda nm: _drone_meta(sid, nm), pick))
    return {"sid": sid, "count": len(names), "sampled": len(photos), "photos": photos}


def drone_image(sid: str, name: str, w: int = 1600) -> bytes:
    """A drone photo as a JPEG no wider or taller than w px (256 to 4000)."""
    check(sid, "sid"), check(name, "file")
    if not 256 <= w <= 4000:
        raise LookupError("w is 256 to 4000")
    if name not in (catalog(sid).get("images") or []):
        raise LookupError("no such drone photo")

    def make() -> bytes:
        data = _get(f"resources/{sid}/drone-imagery/{name}").content
        with _resize:
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            im.thumbnail((w, w))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=86)
        return out.getvalue()

    return cached(cache_path("drone", sid, f"w{w}", name), make)


def envmap(sid: str, face: str) -> bytes:
    """One of the six sky cubemap faces the splat was trained against (px nx py ny pz nz)."""
    check(sid, "sid")
    if face not in ENVMAP:
        raise LookupError("face is one of " + " ".join(ENVMAP))
    return cached(cache_path("splat", sid, f"env_{face}.jpg"), lambda: _get(f"resources/{sid}/splat/envmap/{face}.jpg").content)


# --- the splat ---
@dataclass
class _Download:
    total: int
    got: int = 0
    error: str | None = None
    done: threading.Event = field(default_factory=threading.Event)


_downloads: dict[str, _Download] = {}


def splat_size(sid: str) -> int:
    size = catalog(sid).get("splatBytes")
    if not size:
        raise LookupError("this scan has no splat")
    return int(size)


def _fetch_splat(sid: str, dl: _Download, part, final) -> None:
    try:
        r = _get(f"resources/{sid}/splat/splat.ply", stream=True, headers={"Accept-Encoding": "identity"})
        try:
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    f.flush()
                    dl.got += len(chunk)
        finally:
            r.close()
        if dl.got != dl.total:
            raise IOError(f"got {dl.got} bytes, the catalog says {dl.total}")
        part.rename(final)
    except Exception as e:  # noqa: BLE001 - recorded, and the next request starts over
        dl.error = f"{type(e).__name__}: {e}"
        part.unlink(missing_ok=True)
    finally:
        dl.done.set()


def _ensure_splat(sid: str) -> _Download:
    final, part = cache_path("splat", f"{sid}.ply"), cache_path("splat", f"{sid}.ply.part")
    total = splat_size(sid)
    with one_flight(f"splat:{sid}"):
        dl = _downloads.get(sid)
        if final.exists() and (dl is None or dl.done.is_set()):
            dl = _downloads[sid] = _Download(total, total)
            dl.done.set()
        elif dl is None or (dl.done.is_set() and dl.error):
            part.parent.mkdir(parents=True, exist_ok=True)
            part.touch()  # the first reader opens it before the download thread has written a byte
            dl = _downloads[sid] = _Download(total)
            threading.Thread(target=_fetch_splat, args=(sid, dl, part, final), daemon=True, name=f"splat-{sid}").start()
        return dl


def splat_bytes(sid: str, start: int, end: int, stall_s: float = 120) -> Iterator[bytes]:
    """Bytes start..end inclusive of the splat, waiting for the download when it has not got that far.
    Stops early (a short body the client notices) if the download fails or stalls for stall_s seconds."""
    dl = _ensure_splat(sid)
    final, part = cache_path("splat", f"{sid}.ply"), cache_path("splat", f"{sid}.ply.part")
    try:
        f = open(part if not final.exists() else final, "rb")
    except FileNotFoundError:  # renamed to final between the check and the open
        f = open(final, "rb")
    with f:
        pos, last_progress, seen = start, time.monotonic(), dl.got
        while pos <= end:
            have = dl.got
            if have != seen:
                seen, last_progress = have, time.monotonic()
            if pos >= have:
                if dl.error or dl.done.is_set() and pos >= dl.total or time.monotonic() - last_progress > stall_s:
                    return
                time.sleep(0.05)
                continue
            f.seek(pos)
            chunk = f.read(min(1 << 20, end + 1 - pos, have - pos))
            if not chunk:
                return
            yield chunk
            pos += len(chunk)
