"""The building facts database (Tiger Data: Postgres with TimescaleDB, PostGIS, pgvector, pgvectorscale).

    uv run python -m threshold.facts migrate          apply migrations
    uv run python -m threshold.facts load             scans, buildings, measures, rooms, doors and seed facts
    uv run python -m threshold.facts flood [--city Houston --kind house --limit 200]
    uv run python -m threshold.facts rooms [--limit 300]      describe rooms with the vision model and embed them
    uv run python -m threshold.facts compress         convert every finished chunk to the columnstore; print ratios
    uv run python -m threshold.facts stats            row counts, sizes, compression
    uv run python -m threshold.facts bench            query times with and without indexes
    uv run python -m threshold.facts drop_all --yes   delete everything this project stored (after the event)

Connection: TIGER_DATABASE_URL in $THRESHOLD_DATA_DIR/.env.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import db


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("cmd", choices=["migrate", "load", "flood", "rooms", "compress", "stats", "bench", "drop_all"])
    a.add_argument("--yes", action="store_true", help="confirm drop_all")
    a.add_argument("--city", default="Houston")
    a.add_argument("--kind", default="house")
    a.add_argument("--limit", type=int, default=None)
    a.add_argument("--workers", type=int, default=8)
    args = a.parse_args(argv)
    if not db.url():
        print("TIGER_DATABASE_URL is not set in $THRESHOLD_DATA_DIR/.env", file=sys.stderr)
        return 2
    if args.cmd == "drop_all":
        if not args.yes:
            print("This deletes every table, view, index and fact this project stored. Re-run with --yes.")
            return 1
        db.drop_all()
        print("Dropped schema threshold, role threshold_reader and the migration record.")
        return 0
    if args.cmd == "migrate":
        out = db.migrate()
    elif args.cmd == "load":
        from . import load
        db.migrate()
        out = load.load(workers=args.workers)
    elif args.cmd == "flood":
        from . import flood
        out = flood.run_many(city=args.city, kind=args.kind, limit=args.limit or 200, workers=args.workers)
    elif args.cmd == "rooms":
        from . import rooms
        out = rooms.build(limit=args.limit or 300)
    elif args.cmd == "compress":
        from . import stats
        out = stats.compress()
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
