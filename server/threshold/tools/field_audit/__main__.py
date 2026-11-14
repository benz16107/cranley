"""Run the field audit and write its table for review (sponsor data: write it under $THRESHOLD_DATA_DIR only).

    uv run python -m threshold.tools.field_audit [--out DIR] [--sample 150] [--deep-top 15]

Writes field_audit.csv (every compared claim, ranked), field_summary.csv (by field), top15.json (the full checks)
and result.json (the ToolResult).
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

from ...config import DATA
from ..registry import default_plan
from . import TABLE, draw, run_audit, to_result


def picture(summary: list[dict], result: dict):
    """Bars of how often each field disagrees, then the deep checks' evidence crops."""
    from PIL import Image, ImageDraw

    from ..record_vs_reality.review import COLOR, PAD, THUMB, W, _crop, _font
    rows = [s for s in summary if s["checked"]]
    top = result["findings"]
    thumbs = [(f, im) for f in top for m in (f.get("media") or [])[:1] if (im := _crop(m)) is not None][:8]
    h = PAD * 3 + 34 * len(rows) + 30 + 22 * len(top) + ((len(thumbs) + 3) // 4) * (THUMB + 40)
    img = Image.new("RGB", (W, h), "white")
    d = ImageDraw.Draw(img)
    f = _font(15)
    d.text((PAD, PAD), result["verdict"]["text"][:140], fill=(0, 0, 120), font=f)
    y = PAD * 2 + 10
    for s in rows:
        share = s["share"] or 0
        d.text((PAD, y), f"{s['field']}", fill=(0, 0, 0), font=f)
        d.rectangle([260, y, 260 + int(600 * share), y + 22], fill=COLOR["fail"] if share > 0.25 else COLOR["warn"])
        d.text((870, y), f"{s['contradicted']} of {s['checked']} disagree" + (f", {s['over_10pct']} over 10%" if s.get("over_10pct") else ""),
               fill=(0, 0, 0), font=f)
        y += 34
    y += 10
    for t in top:
        d.text((PAD, y), f"[{t['status']}] {t['title']}"[:140], fill=COLOR.get(t["status"], (0, 0, 0)), font=f)
        y += 22
    y += 10
    for i, (fd, im) in enumerate(thumbs):
        x, yy = PAD + (i % 4) * (THUMB + 10), y + (i // 4) * (THUMB + 40)
        img.paste(im, (x, yy))
        d.text((x, yy + im.height + 4), fd["title"][:34], fill=(0, 0, 0), font=_font(13))
    return img


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DATA / "shots" / "tools" / "field_audit"))
    ap.add_argument("--sample", type=int, default=150)
    ap.add_argument("--deep-top", type=int, default=15)
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    if DATA.resolve() not in out.resolve().parents:
        print(f"refusing to write sponsor data outside {DATA}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    res = run_audit(draw(a.sample), default_plan, a.deep_top, step=lambda s: print(s, flush=True))
    top = {(t["sid"], t["claim_key"]): t for t in res["top"]}
    with open(out / "field_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, TABLE, extrasaction="ignore")
        w.writeheader()
        for r in res["rows"]:
            w.writerow({**r, **{k: top.get((r["sid"], r["claim_key"]), {}).get(k) for k in ("deep_verdict", "judgement", "judgement_reason")}})
    with open(out / "field_summary.csv", "w", newline="") as f:
        cols = ["field", "claims", "checked", "contradicted", "share", "cannot_verify", "over_10pct", "median_ratio", "by_kind"]
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(res["summary"])
    (out / "top15.json").write_text(json.dumps(res["top"], indent=1, default=str))
    (out / "skipped.json").write_text(json.dumps(res["skipped"], indent=1))
    r = to_result(res)
    r.tool = "field_audit"
    (out / "result.json").write_text(r.model_dump_json(indent=1))
    picture(res["summary"], json.loads(r.model_dump_json())).save(out / "field_audit.png")
    print(r.verdict.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
