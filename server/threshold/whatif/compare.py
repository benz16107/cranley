"""Run the relevant tools on a plan and its edited copy, and say which checks flipped."""
from __future__ import annotations

import copy

from ..tools.registry import ToolContext, run_tool

# goal -> the tools that judge it, with the inputs that keep them on geometry (no panorama reading: the panoramas
# show the building as it is, not as edited)
GOALS: dict[str, dict] = {
    "bathroom_route": {"title": "Step-free route to the bathroom",
                       "tools": {"step_free_route": {"destinations": ["Bathroom"], "read_panoramas": False},
                                 "bathroom_clearance": {"read_panoramas": False}}},
    "bathroom_turn": {"title": "Turning circle in the bathroom",
                      "tools": {"turning_space": {"rooms": ["Bathroom"]},
                                "bathroom_clearance": {"read_panoramas": False}}},
    "door_widths": {"title": "Doors wide enough for a wheelchair",
                    "tools": {"door_widths": {"min_width_m": 0.815}}},
    "wheelchair_ready": {"title": "Wheelchair-ready home",
                         "tools": {"door_widths": {"min_width_m": 0.815},
                                   "step_free_route": {"read_panoramas": False},
                                   "turning_space": {},
                                   "bathroom_clearance": {"read_panoramas": False}}},
}
RANK = {"pass": 0, "warn": 1, "unknown": 1, "fail": 2}


def context(plans: dict[str, dict], parent: ToolContext | None = None) -> ToolContext:
    """A tool context that serves these plans (fresh copies, since tools may change what they get) before any
    other scan."""
    base = parent or ToolContext()
    return ToolContext(plans=lambda s: copy.deepcopy(plans[s]) if s in plans else base.plans(s), on_step=None,
                       sites=base.sites)


def run(plan: dict, goal: str, ctx: ToolContext) -> dict[str, dict]:
    """tool id -> its ToolResult as a dict, for every tool the goal names."""
    out = {}
    for tid, inputs in GOALS[goal]["tools"].items():
        out[tid] = run_tool(tid, {"scan": plan["sid"], **inputs}, ctx).model_dump()
    return out


def checks(results: dict[str, dict]) -> dict[str, dict]:
    return {f"{tid}:{c['id']}": {**c, "tool": tid} for tid, r in results.items() for c in r["checks"]}


def flips(before: dict[str, dict], after: dict[str, dict]) -> list[dict]:
    """Every check whose status or measurement changed. `change` is fixed, better, worse, broke, gone or new."""
    b, a = checks(before), checks(after)
    out = []
    for k in dict.fromkeys([*b, *a]):
        x, y = b.get(k), a.get(k)
        if x and y and x["status"] == y["status"] and x.get("measured") == y.get("measured"):
            continue
        if x and y:
            sx, sy = RANK[x["status"]], RANK[y["status"]]
            change = ("fixed" if y["status"] == "pass" else "better") if sy < sx else \
                     ("broke" if x["status"] == "pass" else "worse") if sy > sx else "measure"
        else:
            change = "gone" if x else "new"
        c = y or x
        out.append({"key": k, "tool": c["tool"], "check": c["id"], "rule": c["rule"], "unit": c["unit"],
                    "threshold": c.get("threshold"), "change": change,
                    "before": {"status": x["status"], "measured": x.get("measured")} if x else None,
                    "after": {"status": y["status"], "measured": y.get("measured")} if y else None})
    order = ["fixed", "better", "broke", "worse", "measure", "new", "gone"]
    return sorted(out, key=lambda f: order.index(f["change"]))


def failing(results: dict[str, dict]) -> int:
    return sum(1 for c in checks(results).values() if c["status"] == "fail")
