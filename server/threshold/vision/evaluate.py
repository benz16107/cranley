"""Accuracy check on a small set. Run: `python -m threshold.vision.evaluate rooms|objects|contents SID...`.
Scan ids stay out of the repo; the sets used are listed in `$THRESHOLD_DATA_DIR/shots/perception/eval/SETS.md`.

Results (JSON and annotated crops) go to `$THRESHOLD_DATA_DIR/shots/perception/eval/`, never the repo.
"""
from __future__ import annotations

import collections
import io
import json
import sys

from PIL import Image, ImageDraw

from ..config import DATA
from ..sources import matterport as mp
from . import reader

OUT = DATA / "shots" / "perception" / "eval"


def plan(sid: str) -> dict:
    return json.loads((DATA / "fixtures" / "scanplan" / f"{sid}.json").read_text())


def rooms(sids: list[str]) -> None:
    rows = []
    for sid in sids:
        for r in reader.label_rooms(plan(sid)):
            rows.append({"sid": sid, **r})
            print(sid, f"{r['matterport_label']!s:14} -> {r['label']:14} {r['confidence']:6} {'ok' if r['agrees'] else 'MISS'}")
    scored = [r for r in rows if r["matterport_label"]]  # Matterport left some rooms unlabelled
    n = len(scored)
    exact = sum(r["agrees"] for r in scored)
    lenient = sum(r["agrees_lenient"] for r in scored)
    print(f"\n{len(rows)} rooms read, {n} with a Matterport label: exact agreement {exact}/{n} ({exact / n:.0%}), lenient {lenient}/{n} ({lenient / n:.0%})")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "label_rooms.json").write_text(json.dumps(rows, indent=1))


def crop(sid: str, ref: str, box: list[float], label: str, path) -> None:
    _, pano, face = ref.split("/")
    im = Image.open(io.BytesIO(mp.pano_face(sid, pano, int(face), "2k"))).convert("RGB")
    W = im.width
    x0, y0, x1, y1 = (v * W for v in box)
    pad = max(80, (x1 - x0), (y1 - y0))
    c = im.crop((max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(W, y1 + pad)))
    d = ImageDraw.Draw(c)
    ox, oy = max(0, x0 - pad), max(0, y0 - pad)
    d.rectangle([x0 - ox, y0 - oy, x1 - ox, y1 - oy], outline=(255, 40, 40), width=4)
    d.text((6, 6), label, fill=(255, 255, 0))
    c.thumbnail((480, 480))
    c.save(path, quality=85)


def objects(sids: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    allrows = []
    for sid in sids:
        found = reader.find_objects(plan(sid), max_panos=8)
        print(sid, dict(collections.Counter(f["label"] for f in found)))
        for i, f in enumerate(found):
            m = f["finding"]["media"][0]
            path = OUT / f"obj_{sid}_{i:03d}_{f['label'].replace(' ', '_')}.jpg"
            crop(sid, m["ref"], m["box"], f"{f['label']} ({f['finding']['source']['confidence']})", path)
            allrows.append({"sid": sid, "crop": path.name, **f})
    (OUT / "find_objects.json").write_text(json.dumps(allrows, indent=1))
    print(len(allrows), "findings; crops in", OUT)


def contents(sids: list[str]) -> None:
    p = plan(sids[0])
    room = next(r for r in p["rooms"] if r.get("label") == "Living Room")
    out = reader.contents(p, room["id"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "contents.json").write_text(json.dumps(out, indent=1))
    for it in out["items"]:
        print(f"{it['name']:30} x{it['count']} {it['category']:14} {it['size_class']:22} {it['cost_class']:18} fixture={it['fixture']}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python -m threshold.vision.evaluate rooms|objects|contents SID [SID ...]")
    {"rooms": rooms, "objects": objects, "contents": contents}[sys.argv[1]](sys.argv[2:])
