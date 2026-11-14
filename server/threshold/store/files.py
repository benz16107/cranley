"""The default store: one JSON file per workspace (<root>/<id>.json, the whole log) and one per profile
(<root>/profiles/<profile>.json, preferences merged key by key under a file lock). What Session did before the
store interface existed, moved here unchanged."""
from __future__ import annotations

import fcntl
import json
import pathlib


class FileStore:
    def __init__(self, root):
        self.root = pathlib.Path(root)

    def load(self, id: str) -> dict:
        f = self.root / f"{id}.json"
        if not f.exists():
            raise LookupError(f"no workspace {id}")
        return json.loads(f.read_text())

    def since(self, id: str, seq: int) -> list[dict]:
        return [e for e in self.load(id)["log"] if e["seq"] > seq]

    def save(self, meta: dict, log: list, new_from: int, doc) -> None:
        # shortcut: no conflict check between processes; one server owns the files. THRESHOLD_STORE=mongo when several write.
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{meta['id']}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({**meta, "log": [e.model_dump(mode="json", by_alias=True) for e in log]}))
        tmp.replace(path)

    def profile(self, profile: str) -> list[dict]:
        prof = self.root / "profiles" / f"{profile}.json"
        return list(json.loads(prof.read_text()).values()) if prof.exists() else []

    def merge_profile(self, profile: str, changes: dict[str, tuple[float, dict | None]]) -> None:
        """changes: key -> (when this workspace changed it, the preference or None if removed). A key is written
        unless another workspace changed it later; a removal stays as a dated deletion."""
        prof = self.root / "profiles" / f"{profile}.json"
        prof.parent.mkdir(parents=True, exist_ok=True)
        with open(prof.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)  # other processes and threads on the same profile wait here
            data = json.loads(prof.read_text()) if prof.exists() else {}
            for key, (at, p) in changes.items():
                if (data.get(key) or {}).get("at", 0) > at:
                    continue
                data[key] = {**p, "at": at} if p else {"key": key, "value": None, "at": at}
            tmp = prof.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(prof)
