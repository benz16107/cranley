"""Where data and keys live. Both are outside the repo (CoStar terms: no sponsor data in git)."""
import os
import pathlib

DATA = pathlib.Path(os.environ.get("THRESHOLD_DATA_DIR", "~/Code/hackathons/hackprinceton26-data"))
CACHE = DATA / "cache"


def env() -> dict[str, str]:
    """Keys from the data folder's .env, overridden by real environment variables."""
    f = DATA / ".env"
    pairs = (l.strip().split("=", 1) for l in f.read_text().splitlines() if "=" in l and not l.lstrip().startswith("#")) if f.exists() else ()
    return {**{k: v for k, v in pairs if v}, **os.environ}
