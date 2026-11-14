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
    print(r.verdict.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
