"""Accuracy run for the room labeller. Labels a fixed set of commercial scans, saves the evidence crops and contact
sheets for checking by eye, and scores the labels against a hand-made truth file. Everything it writes is
derived from sponsor data, so it goes under $THRESHOLD_DATA_DIR/shots/tools/room_labeller/, never into git.

    uv run python -m threshold.tools.room_labeller.evaluate label     # model calls (cached after the first run)
    uv run python -m threshold.tools.room_labeller.evaluate sheets    # contact sheets from the saved labels
    uv run python -m threshold.tools.room_labeller.evaluate score     # confusion table against truth.json

truth.json: {"<sid>/<room>": "<label from COMMERCIAL_LABELS>"} written by the person checking the sheets.
"""
from __future__ import annotations

import io
import json
import sys
import time
from collections import Counter, defaultdict

from PIL import Image, ImageDraw, ImageFont

from ...config import DATA
from ...sources import matterport as mp
from ...vision import reader
from ..registry import ToolContext
from . import facts, label_scan

OUT = DATA / "shots" / "tools" / "room_labeller"
# {kind of space: [sid]}; which scans is sponsor data, so the list lives in the data folder, never in git
SET: dict[str, list[str]] = json.loads((DATA / "fixtures" / "room_labeller_set.json").read_text())


def label() -> None:
    rows, cost = [], []
    for kind, sids in SET.items():
        for sid in sids:
            ctx = ToolContext()
            t = time.time()
            out = label_scan(ctx, sid, include_labelled=True, relabel=True, max_rooms=80)
            plan = out["plan"]
            for r in facts.live_rooms(plan):
                e = out["doc"]["rooms"].get(r["id"])
                if not e or e["label_source"] != "vision":
                    continue
                f = out["facts"][r["id"]]
                rows.append({"kind": kind, "sid": sid, "room": r["id"], "label": e["label"], "confidence": e["confidence"],
                             "peek": bool(e.get("peek")), "reason": e["reason"], "evidence": e["evidence"],
                             "matterport_label": e.get("matterport_label"), "area": f["area"], "walls": facts.quality(plan)["walls"]})
            cost.append({"sid": sid, "kind": kind, "calls": out["calls"], "seconds": round(time.time() - t, 1),
                         "rooms": len(facts.live_rooms(plan))})
            print(sid, kind, cost[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "labels.json").write_text(json.dumps(rows, indent=1))
    old = json.loads((OUT / "cost.json").read_text()) if (OUT / "cost.json").exists() else {}
    first = {c["sid"]: c for c in old.get("first_run", [])}
    for c in cost:  # keep the uncached timing from the first run
        first.setdefault(c["sid"], c)
    (OUT / "cost.json").write_text(json.dumps({"first_run": list(first.values()), "last_run": cost}, indent=1))


def _face(ev: dict, px: int, ring: tuple[float, float] | None = None) -> Image.Image:
    im = Image.open(io.BytesIO(mp.pano_face(ev["sid"], ev["pano"], ev["face"], "2k"))).convert("RGB").resize((px, px))
    if ring:
        u, v = ring[0] * px / reader.ROOM_PX, ring[1] * px / reader.ROOM_PX
        ImageDraw.Draw(im).ellipse([u - 30, v - 30, u + 30, v + 30], outline=(255, 0, 0), width=4)
    return im


def tile(row: dict, n: int) -> Image.Image:
    ev = row["evidence"]
    W, big, small = 560, 420, 140
    im = Image.new("RGB", (W, big + small + 46), "white")
    ring = None
    if row["peek"]:
        plan = mp.plan(row["sid"])
        room = next(r for r in plan["rooms"] if r["id"] == row["room"])
        view = reader._peek_view(plan, room)
        ring = (view[2], view[3]) if view else None
    im.paste(_face(ev, big, ring), (0, 0))
    others = [f for f in (1, 2, 3, 4) if f != ev["face"]] if not row["peek"] else []
    for i, f in enumerate(others):
        im.paste(_face({**ev, "face": f}, small), (i * small, big))
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=15)
    d.text((6, big + small + 4), f"#{n} {row['label']} ({row['confidence']}{', through door' if row['peek'] else ''})",
           fill="black", font=font)
    d.text((6, big + small + 24), f"{row['kind']} | {row['sid']} | {row['area'] or 0:.0f} m2"
           + (f" | MP: {row['matterport_label']}" if row["matterport_label"] else ""), fill=(80, 80, 80), font=font)
    return im


def sheets() -> None:
    rows = json.loads((OUT / "labels.json").read_text())
    d = OUT / "sheets"
    d.mkdir(parents=True, exist_ok=True)
    index = {}
    for start in range(0, len(rows), 6):
        part = rows[start:start + 6]
        sheet = Image.new("RGB", (560 * 2 + 10, (420 + 140 + 46 + 10) * 3), (230, 230, 230))
        for i, row in enumerate(part):
            n = start + i + 1
            index[n] = f"{row['sid']}/{row['room']}"
            sheet.paste(tile(row, n), ((i % 2) * 570, (i // 2) * 616))
        sheet.save(d / f"sheet_{start // 6 + 1:02d}.jpg", quality=82)
    (d / "index.json").write_text(json.dumps(index, indent=1))
    print(f"{len(rows)} rooms on {len(range(0, len(rows), 6))} sheets in {d}")


def score() -> str:
    rows = {f"{r['sid']}/{r['room']}": r for r in json.loads((OUT / "labels.json").read_text())}
    truth = json.loads((OUT / "truth.json").read_text())
    pairs = [(truth[k], rows[k]) for k in truth if k in rows]
    labels = sorted({t for t, _ in pairs} | {r["label"] for _, r in pairs})
    conf = defaultdict(Counter)
    for t, r in pairs:
        conf[t][r["label"]] += 1
    ok = sum(t == r["label"] for t, r in pairs)
    lines = [f"Checked by eye: {len(pairs)} rooms. Exact agreement: {ok} ({100 * ok / max(len(pairs), 1):.0f}%).", ""]
    for name, sel in (("by kind of space", lambda r: r["kind"]), ("by confidence", lambda r: r["confidence"]),
                      ("seen from inside or through a door", lambda r: "through a door" if r["peek"] else "inside"),
                      ("wall graph", lambda r: "walls" if r["walls"] else "no walls")):
        g = defaultdict(lambda: [0, 0])
        for t, r in pairs:
            g[sel(r)][0] += t == r["label"]
            g[sel(r)][1] += 1
        lines.append(f"{name}: " + ", ".join(f"{k} {a}/{n}" for k, (a, n) in sorted(g.items())))
    lines += ["", "Confusion (rows: truth, columns: labeller; only labels that occur)", ""]
    short = {l: l.split(" or ")[0][:12] for l in labels}
    lines.append("| truth \\ said | " + " | ".join(short[l] for l in labels) + " |")
    lines.append("|---" * (len(labels) + 1) + "|")
    for t in labels:
        if sum(conf[t].values()):
            lines.append(f"| {t} | " + " | ".join(str(conf[t][l] or "") for l in labels) + " |")
    mp_pairs = [r for r in rows.values() if r["matterport_label"]]
    if mp_pairs:
        lines += ["", f"Rooms Matterport had labelled, labeller's call beside it ({len(mp_pairs)}): " +
                  ", ".join(f"{r['matterport_label']}->{r['label']}" for r in mp_pairs)]
    text = "\n".join(lines)
    (OUT / "accuracy.md").write_text(text)
    return text


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "label"
    if cmd == "label":
        label()
    elif cmd == "sheets":
        sheets()
    else:
        print(score())
