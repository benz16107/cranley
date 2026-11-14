"""Pick a spread of scans, fetch them (cached), and print what is usable in each ScanPlan, by kind of scan.

    uv run python scripts/sample_quality.py            # the saved sample ($THRESHOLD_DATA_DIR/sample_sids.txt), or a new one
    uv run python scripts/sample_quality.py --new 40   # draw 40 more scans across kinds, add them to the sample

Scan ids are the sponsor's data, so the sample list lives in the data folder, not in git.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from threshold.config import DATA  # noqa: E402
from threshold.sources import index, matterport as mp  # noqa: E402

LIST = DATA / "sample_sids.txt"
# (kind, extra filter, how many): chosen so every kind and the awkward shapes are in the sample
QUOTAS = [("house", dict(splat=True), 6), ("house", dict(floors_min=2), 3), ("apartment_unit", {}, 8),
          ("amenity", {}, 5), ("office", {}, 6), ("office", dict(floors_min=2), 2), ("warehouse", {}, 5),
          ("retail", {}, 2), ("other", {}, 3), ("apartment_unit", dict(floors_min=2), 2), ("amenity", dict(floors_min=2), 1)]


def draw(n_extra_seed: int = 7) -> list[str]:
    rng = random.Random(n_extra_seed)
    have = {p.stem for p in (DATA / "raw").glob("*.json")} | set(LIST.read_text().split() if LIST.exists() else [])
    picked: list[str] = []
    for kind, flt, n in QUOTAS:
        _, rows = index.search(kind=kind, rooms_min=1, limit=100000, **flt)
        pool = [r["sid"] for r in rows if r["sid"] not in have and r["sid"] not in picked and r["panos"] >= 3]
        picked += rng.sample(pool, min(n, len(pool)))
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", action="store_true", help="draw a fresh sample and add it to the list")
    args = ap.parse_args()
    if args.new or not LIST.exists():
        LIST.write_text("\n".join(draw()) + "\n" if not LIST.exists() else LIST.read_text() + "\n".join(draw()) + "\n")
    sids = [s for s in LIST.read_text().split() if s] + [p.stem for p in sorted((DATA / "raw").glob("*.json"))]
    sids = list(dict.fromkeys(sids))
    flags = ("walls", "polygons", "openings", "labels", "georef")
    by_kind: dict[str, list[dict]] = collections.defaultdict(list)
    print(f"{'sid':12} {'kind':15} {'seg':5} {'city':12} fl rooms(poly/unb/void) walls opens panos  W P O L G")
    for sid in sids:
        try:
            p = mp.plan(sid)
        except Exception as e:
            print(f"{sid:12} FAILED {type(e).__name__}: {e}")
            continue
        r, q = index.rows()[sid], p["quality"]
        c = q["counts"]
        kind = r["kind"]
        by_kind[kind].append(q)
        print(f"{sid:12} {kind:15} {r['segment'][:4]:5} {(r['city'] or '?')[:12]:12} {c['floors']:2} "
              f"{c['rooms']:3}({c['rooms_with_polygon']}/{c['rooms_unbounded']}/{c['rooms_void']}) {c['walls']:5} {c['openings']:5} "
              f"{c['panos']:5}  " + " ".join("Y" if q[f] else "." for f in flags))
    print(f"\n{'kind':15} {'n':>3} " + " ".join(f"{f:>9}" for f in flags))
    total = [q for qs in by_kind.values() for q in qs]
    for kind, qs in sorted(by_kind.items()) + [("ALL", total)]:
        print(f"{kind:15} {len(qs):3} " + " ".join(f"{sum(q[f] for q in qs) / len(qs):9.0%}" for f in flags))


if __name__ == "__main__":
    main()
