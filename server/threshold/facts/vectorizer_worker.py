"""The pgai vectorizer worker for Threshold, run in its own environment (its dependencies conflict with the app's):

  uvx --python 3.12 --from "pgai[vectorizer-worker]==0.12.1" python -I server/threshold/facts/vectorizer_worker.py \
      [--target cloud|local] [--once]

It reads the database URL from $THRESHOLD_DATA_DIR/.env (TIGER_DATABASE_URL, or TIGER_LOCAL_DATABASE_URL with
--target local) so the URL never appears on a command line or in a log. Imports nothing from the app."""
import datetime as dt
import os
import pathlib
import sys

KEYS = {"cloud": "TIGER_DATABASE_URL", "local": "TIGER_LOCAL_DATABASE_URL", "test": "TIGER_TEST_DATABASE_URL"}


def url(target: str) -> str:
    data = pathlib.Path(os.environ.get("THRESHOLD_DATA_DIR", "~/Code/hackathons/hackprinceton26-data"))
    pairs = dict(l.split("=", 1) for l in (data / ".env").read_text().splitlines() if "=" in l and not l.startswith("#"))
    return os.environ.get(KEYS[target]) or pairs[KEYS[target]]


if __name__ == "__main__":
    import asyncio

    from pgai.vectorizer import Worker
    target = sys.argv[sys.argv.index("--target") + 1] if "--target" in sys.argv else "cloud"
    asyncio.run(Worker(url(target), once="--once" in sys.argv, poll_interval=dt.timedelta(seconds=30)).run())
