"""Threads in one JSON file under $THRESHOLD_DATA_DIR/photon/ (outside the repo: it holds people's handles).

A thread is one chat (a Photon Space). It points at the workspace it is working in, and every answer message is
remembered with its workspace, so a native reply to an old answer goes back to that answer's workspace."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from ..config import DATA

FILE = DATA / "photon" / "state.json"
_lock = threading.RLock()
SEEN_MAX = 2000      # message ids kept for de-duplication (Photon may deliver an event twice)
ANSWERS_MAX = 300    # answer message ids kept per thread


def _load(f: Path) -> dict:
    try:
        return json.loads(f.read_text())
    except (FileNotFoundError, ValueError):
        return {"threads": {}, "seen": [], "calls": {}}


class State:
    def __init__(self, file: Path = FILE):
        self.file = file
        self.data = _load(file)
        self.data.setdefault("calls", {})

    def save(self) -> None:
        with _lock:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1))
            tmp.replace(self.file)

    def first_time(self, message_id: str) -> bool:
        """True once per message id."""
        with _lock:
            seen = self.data["seen"]
            if message_id in seen:
                return False
            seen.append(message_id)
            del seen[:-SEEN_MAX]
            self.save()
            return True

    def thread(self, space: str) -> dict[str, Any]:
        with _lock:
            return self.data["threads"].setdefault(space, {"workspace": None, "answers": {}, "created": time.time()})

    def update(self, space: str, **fields) -> dict:
        with _lock:
            t = self.thread(space)
            t.update(fields)
            self.save()
            return t

    def remember(self, space: str, message_id: str, workspace: str, **more) -> None:
        """An answer we sent: a reply to it comes back to this workspace."""
        if not message_id:
            return
        with _lock:
            a = self.thread(space)["answers"]
            a[message_id] = {"workspace": workspace, **more}
            for k in list(a)[:-ANSWERS_MAX]:
                del a[k]
            self.save()

    def answer(self, space: str, message_id: str | None) -> dict | None:
        return self.thread(space)["answers"].get(message_id) if message_id else None

    def by_handle(self, handle: str) -> tuple[str, dict] | None:
        """The newest thread whose person has this handle (a caller's number finds their text thread)."""
        hits = [(s, t) for s, t in self.data["threads"].items() if t.get("handle") == handle]
        return max(hits, key=lambda x: x[1].get("touched", 0)) if hits else None
