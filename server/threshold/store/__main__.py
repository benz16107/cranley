"""python -m threshold.store <command>

  setup     create collections and indexes (search and vector indexes too) and wait until they answer
  migrate   copy every workspace and profile from the JSON files into MongoDB (skips ones already there)
  status    counts, search index states, how memories are embedded
  drop_all --target <kind>:<database>
            delete the whole database: run after the event (CoStar's terms require deleting derived data). The target
            must name the deployment: atlas:threshold for the cluster at MONGODB_URI, local:threshold for Docker.

  --local   use MONGODB_TEST_URI (the local deployment) instead of MONGODB_URI. The connection string is never printed.
"""
from __future__ import annotations

import json
import sys

from . import FileStore, connect


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    if cmd not in ("setup", "migrate", "status", "drop_all"):
        print(__doc__)
        return 2
    if "--local" in argv:
        from ..config import env
        if not env().get("MONGODB_TEST_URI"):
            print("MONGODB_TEST_URI is not set")
            return 2
        m = connect(env()["MONGODB_TEST_URI"])
    else:
        m = connect()
    if cmd == "setup":
        print("ready" if m.wait_ready() else "search indexes still building", json.dumps(m.status(), indent=1))
    elif cmd == "status":
        print(json.dumps(m.status(), indent=1))
    elif cmd == "migrate":
        from ..agent.workspace import STORE, Session
        files = FileStore(STORE)
        done = 0
        for f in sorted(STORE.glob("ws_*.json")):
            if f.name.endswith(".casefile.json") or m.workspaces.find_one({"_id": f.stem}, {"_id": 1}):
                continue
            s = Session.load(f.stem, store=files)
            m.save(s.meta(), s.log, 0, s.doc)
            done += 1
        for f in sorted((STORE / "profiles").glob("*.json")):
            m.merge_profile(f.stem, {p["key"]: (p.get("at", 0), p if p.get("value") is not None else None)
                                     for p in files.profile(f.stem)})
        print(f"migrated {done} workspaces", json.dumps(m.status()["counts"]))
    elif cmd == "drop_all":
        target = argv[argv.index("--target") + 1] if "--target" in argv[:-1] else None
        if target != m.target:
            print(f"Refusing: this would delete {m.target}. Run again with --target {m.target} to confirm.")
            return 1
        print("dropped", json.dumps(m.drop_all()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
