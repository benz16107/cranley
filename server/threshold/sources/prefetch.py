"""Warm the disk cache for a list of scans, politely (one shared rate limit, retries on 429 and 5xx).

    uv run python -m threshold.sources.prefetch SID [SID ...] [--file ids.txt] [--floorplans] [--panos 2k|4k]
                                                 [--equirect 2048] [--drone 60]

Plans only by default. The other options add floor plans (jpg), every panorama's six cube faces (or one stitched
equirect per pano with --equirect), and drone photo metadata. Nothing is fetched twice: the cache is checked first.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

from . import hackathon, matterport as mp


def warm(sid: str, floorplans: bool = False, panos: str | None = None, equirect: int | None = None, drone: int = 0) -> str:
    p = mp.plan(sid)
    done = [f"plan ({len(p['rooms'])} rooms)"]
    if floorplans:
        n = 0
        for fp in p["floorplans"]:
            if fp["format"] == "jpg" and fp["flags"] == ["photogramy"]:
                mp.floorplan(sid, fp["floor"], "jpg", "photogramy")
                n += 1
        done.append(f"{n} floor plans")
    if panos or equirect:
        for pano in p["panos"]:
            if equirect:
                mp.equirect(sid, pano["id"], equirect)
            else:
                for face in range(6):
                    mp.pano_face(sid, pano["id"], face, panos)
        done.append(f"{len(p['panos'])} panos")
    if drone and p["has"]["splat"]:
        done.append(f"{len(hackathon.drone_list(sid, drone)['photos'])} drone photos")
    return ", ".join(done)


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("sids", nargs="*")
    a.add_argument("--file", help="a file with one scan id per line")
    a.add_argument("--floorplans", action="store_true")
    a.add_argument("--panos", choices=["2k", "4k"])
    a.add_argument("--equirect", type=int, metavar="WIDTH")
    a.add_argument("--drone", type=int, default=0, metavar="N", help="read GPS and gimbal for N drone photos per splat scan")
    a.add_argument("--threads", type=int, default=4)
    args = a.parse_args(argv)
    sids = args.sids + ([s.strip() for s in open(args.file) if s.strip() and not s.startswith("#")] if args.file else [])
    if not sids:
        a.error("give scan ids or --file")

    def one(sid: str) -> bool:
        try:
            print(f"{sid}  {warm(sid, args.floorplans, args.panos, args.equirect, args.drone)}", flush=True)
            return True
        except Exception as e:  # keep going: one bad scan should not stop the rest
            print(f"{sid}  FAILED  {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            return False

    with ThreadPoolExecutor(args.threads) as pool:
        ok = list(pool.map(one, sids))
    print(f"{sum(ok)} of {len(sids)} scans cached")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
