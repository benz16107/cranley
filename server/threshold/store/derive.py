"""What the MongoDB store keeps besides the log, derived from a workspace document (JSON). Pure functions; no database.

- history: one searchable item per brief, finding, note, removed tool and shortlisted building (Atlas Search).
- memory: one per workspace with a brief: the need in the person's words and how it turned out (Vector Search).
- shortlist: one per shortlisted scan, with a GeoJSON point when the scan's location is known (2dsphere).

`where(sid)` gives a scan's {address, city, lat, lon}; the default reads the scan index.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

Where = Callable[[str], dict | None]


def scan_place(sid: str) -> dict | None:
    from ..sources import index
    r = index.rows().get(sid)
    return index.public(r) if r else None


def digest(d: dict) -> str:
    return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


def _sid_of(f: dict, runs: dict) -> str | None:
    run = runs.get(f.get("run") or "")
    return (run or {}).get("sid") or (f.get("anchor") or {}).get("sid")


def history(doc: dict, where: Where = scan_place) -> list[dict]:
    ws, prof, b = doc["id"], doc.get("profile", "default"), doc.get("brief") or {}
    runs = {r["id"]: r for r in doc.get("runs", [])}
    persona = b.get("persona") or "none"

    def place(sid):
        p = (where(sid) or {}) if sid else {}
        return {"sid": sid, "address": p.get("address"), "city": p.get("city")}

    base = {"workspace": ws, "profile": prof, "persona": persona, "at": doc.get("updated", 0)}
    out = []
    if b.get("text") or b.get("summary"):
        cities = sorted({c for c in ((where(s) or {}).get("city") for s in (b.get("scope") or {}).get("sids", [])) if c})
        out.append({**base, "_id": f"{ws}:brief", "kind": "brief", "title": b.get("summary") or "",
                    "text": " ".join([b.get("text") or "", *(b.get("limits") or [])]).strip(), "city": cities})
    for f in doc.get("findings", []):
        if f.get("superseded_by"):
            continue
        fb = f.get("feedback") or {}
        run = runs.get(f.get("run") or "") or {}
        out.append({**base, **place(_sid_of(f, runs)), "_id": f"{ws}:f:{f['id']}", "kind": "finding",
                    "finding": f["id"], "run": f.get("run"), "tool": f.get("tool") or run.get("tool"),
                    "status": f.get("status"), "title": f.get("title") or "", "text": f.get("detail") or "",
                    "feedback": fb.get("verdict"), "reason": fb.get("reason") or ""})
    for p in doc.get("panels", []):
        for i, blk in enumerate(p.get("blocks", [])):
            if blk.get("type") == "Note" and blk.get("text"):
                run = runs.get(p.get("run") or "") or {}
                out.append({**base, **place(run.get("sid")), "_id": f"{ws}:n:{p['id']}:{i}", "kind": "note",
                            "tool": p.get("tool"), "title": p.get("title") or "", "text": blk["text"]})
    for t in doc.get("tools", []):
        if not t.get("enabled", True) and t.get("by") == "user":
            out.append({**base, "_id": f"{ws}:t:{t['id']}", "kind": "tool_removed", "tool": t["id"],
                        "title": t["id"], "text": "", "reason": t.get("reason") or ""})
    for s in doc.get("shortlist", []):
        out.append({**base, **place(s["sid"]), "_id": f"{ws}:s:{s['sid']}", "kind": "shortlist",
                    "title": "Shortlisted", "text": s.get("note") or ""})
    return out


def memory(doc: dict) -> dict | None:
    """The need and its outcome. `text` is what gets embedded: the person's words and the composer's summary."""
    b = doc.get("brief") or {}
    if not b.get("text"):
        return None
    tools = doc.get("tools", [])
    pref = doc.get("prefs", {})
    return {"_id": doc["id"], "workspace": doc["id"], "profile": doc.get("profile", "default"),
            "persona": b.get("persona") or "none", "text": f"{b['text']} {b.get('summary') or ''}".strip(),
            "need": b["text"], "summary": b.get("summary") or "",
            "tools": [{"id": t["id"], "reason": t.get("reason", "")} for t in tools if t.get("enabled", True)],
            "removed": [{"tool": t["id"], "reason": t.get("reason", "")} for t in tools
                        if not t.get("enabled", True) and t.get("by") == "user"],
            "rejected": [{"title": f.get("title", ""), "tool": f.get("tool"), "reason": (f.get("feedback") or {}).get("reason") or ""}
                         for f in doc.get("findings", []) if (f.get("feedback") or {}).get("verdict") == "rejected"],
            "thresholds": {k: v["value"] for k, v in pref.items()
                           if v.get("by") == "user" and not k.startswith(("label.", "doubt.", "tool.off.", "mute."))},
            "shortlisted": len(doc.get("shortlist", [])), "limits": b.get("limits") or [],
            "at": doc.get("updated", 0)}


def shortlist(doc: dict, where: Where = scan_place) -> list[dict]:
    out = []
    for s in doc.get("shortlist", []):
        p = where(s["sid"]) or {}
        row = {"_id": f"{doc['id']}:{s['sid']}", "workspace": doc["id"], "profile": doc.get("profile", "default"),
               "sid": s["sid"], "note": s.get("note", ""), "by": s.get("by", "user"),
               "address": p.get("address"), "city": p.get("city")}
        if p.get("lat") is not None and p.get("lon") is not None:
            row["location"] = {"type": "Point", "coordinates": [p["lon"], p["lat"]]}
        out.append(row)
    return out


def lines(memories: list[dict]) -> list[str]:
    """Recalled memories as prompt lines: how a similar need was set up and what that person taught."""
    out = []
    for m in memories:
        parts = [f'"{m["need"][:200]}"', f"persona {m['persona']}",
                 "tools " + ", ".join(t["id"] for t in m.get("tools", [])) if m.get("tools") else "no tools"]
        parts += [f"they removed {r['tool']}" + (f" ({r['reason']})" if r["reason"] else "") for r in m.get("removed", [])]
        parts += [f'they rejected "{r["title"]}"' + (f" ({r['reason']})" if r["reason"] else "") for r in m.get("rejected", [])[:3]]
        if m.get("thresholds"):
            parts.append("they set " + ", ".join(sorted(m["thresholds"])))
        out.append("- " + "; ".join(parts))
    return out
