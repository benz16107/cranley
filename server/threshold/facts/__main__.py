"""The building facts database (Tiger Data: Postgres with TimescaleDB, PostGIS, pgvector, pgvectorscale).

    uv run python -m threshold.facts migrate          apply migrations
    uv run python -m threshold.facts load             scans, buildings, measures, rooms, doors and seed facts
                                                     (on the cloud database it needs --yes: it empties the flood
                                                     series and room descriptions too)
    uv run python -m threshold.facts measures         refresh only measures, doors and scan flags from a rebuilt
                                                     measures table (safe on the cloud: nothing else is touched)
    uv run python -m threshold.facts flood [--city Houston --kind house --limit 200]
    uv run python -m threshold.facts rooms [--limit 300]      describe rooms with the vision model and embed them
    uv run python -m threshold.facts compress         convert every finished chunk to the columnstore; print ratios
    uv run python -m threshold.facts ops              load saved workspaces' op logs into op_log
    uv run python -m threshold.facts stats            row counts, sizes, compression
    uv run python -m threshold.facts bench            query times with and without indexes
    uv run python -m threshold.facts drop_all --target cloud --yes   delete everything stored on the Tiger Cloud
                                                     service (after the event); --target test for the local test DB

Connection: TIGER_DATABASE_URL in $THRESHOLD_DATA_DIR/.env.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import db


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("cmd", choices=["migrate", "load", "measures", "flood", "rooms", "compress", "stats", "bench", "ops", "drop_all"])
    a.add_argument("--yes", action="store_true", help="confirm drop_all, or load on the cloud database")
    a.add_argument("--target", choices=sorted(db.TARGETS), help="drop_all: which database (required)")
    a.add_argument("--city", default="Houston")
    a.add_argument("--kind", default="house")
    a.add_argument("--limit", type=int, default=None)
    a.add_argument("--workers", type=int, default=8)
    args = a.parse_args(argv)
    if not db.url():
        print("TIGER_DATABASE_URL is not set in $THRESHOLD_DATA_DIR/.env", file=sys.stderr)
        return 2
    if args.cmd == "drop_all":
        if not args.target or not args.yes:
            print("drop_all deletes every table, view, index and fact this project stored. Name the database and "
                  "confirm: --target cloud --yes (the Tiger Cloud service) or --target test --yes (local tests).")
            return 1
        print(f"{args.target}: {db.drop_all(target=args.target)}")
        return 0
    if args.cmd == "load" and not db.is_local(db.url()) and not args.yes:
        # load empties scan, building, measures, room, door, room_text, flood_run and flood_depth before refilling
        # the first five; the flood series and room descriptions then have to be rebuilt (flood, rooms: model calls)
        print("load on the cloud database deletes the flood series and the room descriptions along with the tables "
              "it reloads. Confirm with --yes, then run flood and rooms again.")
        return 1
    if args.cmd == "migrate":
        out = db.migrate()
    elif args.cmd == "load":
        from . import load
        db.migrate()
        out = load.load(workers=args.workers)
    elif args.cmd == "measures":
        from . import load
        out = load.load_measures()
    elif args.cmd == "flood":
        from . import flood
        out = flood.run_many(city=args.city, kind=args.kind, limit=args.limit or 200, workers=args.workers)
    elif args.cmd == "rooms":
        from . import rooms
        out = rooms.build(limit=args.limit or 300)
    elif args.cmd == "compress":
        from . import stats
        out = stats.compress()
    elif args.cmd == "ops":
        from . import record
        out = record.backfill_ops()
    elif args.cmd == "stats":
        from . import stats
        out = stats.stats()
    else:
        from . import stats
        out = stats.bench()
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
