"""A field visit end to end over HTTP, exactly as the iPhone app makes it, on the hand-made test cafe (TEST DATA: no
real place was scanned). Uploads the RoomPlan export, starts one visit per report kind, answers one field task with a
LiDAR-style door measurement, sends drawn ceiling photos for the smoke alarm census, waits for the checks, and saves
each PDF.

    uv run python -m threshold.report.dryrun --server http://linuxbox:8843 --out $THRESHOLD_DATA_DIR/shots/field
"""
from __future__ import annotations

import argparse
import io
import json
import random
import time
from pathlib import Path

import httpx

from ..roomplan.demo import cafe

BUSINESS, PLACE, ADDRESS = "Test Cafe (made up)", "Ground floor shop", "Test address, Nassau Street, Princeton NJ"


def ceiling(alarm: bool, seed: int) -> bytes:
    """A drawn ceiling (drop-ceiling grid, a light panel, and a smoke alarm when asked), labelled as a test image."""
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(seed)
    W, H = 1200, 900
    im = Image.new("RGB", (W, H), (236, 234, 228))
    d = ImageDraw.Draw(im)
    for _ in range(9000):
        g = rnd.randrange(215, 245)
        d.point((rnd.randrange(W), rnd.randrange(H)), fill=(g, g, g - 4))
    for x in range(0, W, 300):
        d.line([(x, 0), (x, H)], fill=(200, 198, 192), width=6)
    for y in range(0, H, 300):
        d.line([(0, y), (W, y)], fill=(200, 198, 192), width=6)
    d.rectangle([620, 320, 880, 560], fill=(250, 250, 246), outline=(190, 190, 185), width=4)
    if alarm:
        cx, cy = 360, 460
        d.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], fill=(248, 248, 245), outline=(175, 175, 170), width=4)
        d.ellipse([cx - 50, cy - 50, cx + 50, cy + 50], outline=(190, 190, 185), width=3)
        for k in range(-40, 41, 10):
            d.line([(cx + k, cy - 30), (cx + k, cy + 30)], fill=(205, 205, 200), width=2)
        d.ellipse([cx + 52, cy - 8, cx + 64, cy + 4], fill=(40, 170, 60))
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    ImageDraw.Draw(im).text((14, H - 26), "TEST IMAGE (drawn)", fill=(150, 150, 150))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def capture(c: httpx.Client, token: str, meta: dict, body: bytes | None = None) -> dict:
    r = c.post(f"/api/phone/{token}/capture", params={"meta": json.dumps(meta)}, content=body or b"")
    r.raise_for_status()
    return r.json()


def wait(c: httpx.Client, ws: str, limit: float = 180) -> dict:
    t0 = time.time()
    while time.time() - t0 < limit:
        st = c.get(f"/api/report/{ws}/status").json()
        if st["done"]:
            return st
        time.sleep(1)
    raise TimeoutError(f"visit {ws} did not finish in {limit} s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8843")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--kinds", default="accessibility,fire,fitout")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    c = httpx.Client(base_url=a.server, timeout=180)
    t0 = time.time()
    up = c.post("/api/scans/user", json={"export": cafe(), "name": PLACE, "kind": "storefront", "address": ADDRESS})
    up.raise_for_status()
    sid = up.json()["sid"]
    print(f"scan {sid}: {len(up.json()['rooms'])} rooms ({time.time() - t0:.1f} s)")
    log = {"sid": sid, "visits": {}}
    for kind in a.kinds.split(","):
        t1 = time.time()
        v = c.post("/api/report/visit", json={"sid": sid, "kind": kind, "business": BUSINESS, "place": PLACE,
                                               "address": ADDRESS}).json()
        ws, token = v["workspace"], v["token"]
        st = wait(c, ws)
        print(f"{kind}: {ws}, checks finished in {time.time() - t1:.1f} s:",
              ", ".join(f"{t['tool']} {t['verdict']['status'] if t['verdict'] else t['status']}" for t in st["tools"]))
        if kind == "accessibility":  # the restroom door, measured on site with LiDAR the way the app sends it
            tasks = c.get(f"/api/phone/{token}").json()["tasks"]
            door = next((t for t in tasks if t["kind"] == "width" and t.get("status") != "done"), None)
            if door:
                said = capture(c, token, {"kind": "reading", "task": door["id"], "scan": sid, "device": "dry-run threshold-ios/1",
                                          "values": {"value_m": 0.715, "unit": "m", "sensor": "arkit_lidar", "err_m": 0.01}})
                print("  measured on site:", door["title"], "->", (said.get("outcome") or {}).get("text") or said.get("problem"))
        if kind == "fire":
            rooms = {r["label"]: r["id"] for r in c.get(f"/api/scan/{sid}/plan").json()["rooms"]}
            for label, alarm, seed in (("Dining Room", True, 1), ("Kitchen", False, 2)):
                capture(c, token, {"kind": "photo", "scan": sid, "room": rooms[label], "values": {"check": "smoke_alarm"},
                                   "note": f"Ceiling of {label}, for the smoke alarm check", "device": "dry-run threshold-ios/1"},
                        ceiling(alarm, seed))
            print("  ceiling photos: Dining Room (alarm drawn), Kitchen (none drawn); Storage left without a photo")
        t2 = time.time()
        pdf = c.get(f"/api/report/{ws}.pdf")
        pdf.raise_for_status()
        f = a.out / f"test-cafe-{kind}.pdf"
        f.write_bytes(pdf.content)
        (a.out / f"test-cafe-{kind}.html").write_text(c.get(f"/api/report/{ws}.html").text)
        print(f"  report {f} ({len(pdf.content) // 1024} KB, printed in {time.time() - t2:.1f} s)")
        log["visits"][kind] = {"workspace": ws, "pdf": str(f)}
    (a.out / "dry-run.json").write_text(json.dumps(log, indent=1))
    print(f"total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
