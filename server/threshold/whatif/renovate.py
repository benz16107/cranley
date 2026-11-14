"""The what-if run the renovate tool and POST /api/whatif share: try each edit alone, pick one per problem, apply the
package to a stored `w_` scan, and re-run the goal's tools on it."""
from __future__ import annotations

from ..tools.registry import ToolContext
from . import compare, cost, store
from .edits import EditError, apply, parse
from .propose import propose

RECORD_ONLY = {"grab_bars"}  # no tool measures these from geometry, so they never show a flip


def _try(plan: dict, edit, goal: str, before: dict, ctx: ToolContext) -> dict:
    try:
        after, diff = apply(plan, [edit])
    except EditError as e:
        return {"edit": edit.model_dump(), "error": str(e), "fixed": 0, "broke": 0, "cost": None}
    res = compare.run(after, goal, compare.context({after["sid"]: after}, ctx))
    fl = compare.flips(before, res)
    c = cost.line(diff[0], after)
    fixed = sum(f["change"] == "fixed" for f in fl)
    return {"edit": edit.model_dump(), "text": diff[0]["text"], "short": diff[0]["short"], "change": diff[0], "flips": fl, "fixed": fixed,
            "better": sum(f["change"] == "better" for f in fl), "broke": sum(f["change"] in ("broke", "worse") for f in fl),
            "cost": c, "per_1k": round(1000 * fixed / c["total"], 2) if c["total"] else None,
            "measured": edit.op not in RECORD_ONLY, "error": None}


def run(ctx: ToolContext, scan: str, goal: str = "wheelchair_ready", edits: list | None = None,
        prices: dict[str, float] | None = None, city: bool = False) -> dict:
    if goal not in compare.GOALS:
        raise ValueError(f"unknown goal {goal!r}; goals: {sorted(compare.GOALS)}")
    plan = ctx.plan(scan)
    if not plan["quality"].get("walls"):
        return {"available": False, "reason": "This scan has no wall graph, so there is no geometry to renovate.",
                "scan": scan, "goal": goal}
    wi = plan.get("whatif") or {}
    base, prior = wi.get("base") or scan, wi.get("edits") or []
    ctx.step(f"Running the {len(compare.GOALS[goal]['tools'])} tools for '{compare.GOALS[goal]['title']}' on the scan as it is")
    before = compare.run(plan, goal, ctx)
    if edits is None:
        cands = propose(plan, goal)
        ctx.step(f"Proposed {len(cands)} edits from the failing checks")
    else:
        cands = [{"edit": e, "target": f"edit{i}", "why": "your edit"} for i, e in enumerate(parse(edits))]
    tried = []
    for c in cands:
        t = _try(plan, c["edit"], goal, before, ctx)
        tried.append({**t, "target": c["target"], "why": c["why"]})
    ctx.step(f"Tried each of the {len(tried)} edits alone and re-ran the tools on each")
    # the package: every edit you gave; else the best working edit per problem (most fixed, then cheapest)
    if edits is not None:
        pick = [t for t in tried if not t["error"]]
    else:
        best: dict[str, dict] = {}
        for t in tried:
            if t["error"] or (t["fixed"] == 0 and t["measured"]) or t["broke"]:
                continue
            k = best.get(t["target"])
            if k is None or (t["fixed"], -t["cost"]["total"]) > (k["fixed"], -k["cost"]["total"]):
                best[t["target"]] = t
        pick = list(best.values())
    package, skipped = [], []
    for t in pick:  # apply in order; an edit that clashes with one before it is dropped and said so
        try:
            apply(plan, [*[p["edit"] for p in package], t["edit"]])
            package.append(t)
        except EditError as e:
            skipped.append({"edit": t["edit"], "reason": str(e)})
    for t in tried:
        t["in_package"] = any(t is p for p in package)
    out = {"available": True, "scan": scan, "base": base, "goal": goal, "goal_title": compare.GOALS[goal]["title"],
           "tools": list(compare.GOALS[goal]["tools"]), "before": _summary(before), "candidates": _ranked(tried),
           "skipped": skipped, "sid": None, "after": None, "flips": [], "package": [], "total_cost": 0,
           "assumptions": [], "fork": None, "still_failing": []}
    if not package:
        out["assumptions"] = cost.assumptions(set(), prices)
        return out
    after, diff = store.save(base, [*prior, *[p["edit"] for p in package]], ctx.plan(base) if prior else plan)
    diff = diff[len(prior):]
    ctx.step(f"Saved the renovated plan as {after['sid']} and re-ran the tools on it")
    res = compare.run(after, goal, compare.context({after["sid"]: after}, ctx))
    lines = [{"edit": p["edit"], "text": d["text"], "change": d, "cost": cost.line(d, after, prices)}
             for p, d in zip(package, diff)]
    used = {i["price"] for ln in lines for i in ln["cost"]["items"]} | \
           {i["price"] for t in tried if t["cost"] for i in t["cost"]["items"]}
    out["still_failing"] = [f"{c['rule']}: {c['tool']}:{c['id']}" for c in compare.checks(res).values()
                            if c["status"] == "fail"]
    out.update(sid=after["sid"], after=_summary(res), flips=compare.flips(before, res), package=lines,
               total_cost=sum(ln["cost"]["total"] for ln in lines), assumptions=cost.assumptions(used, prices))
    if city:
        from ..facts import forks
        ctx.step("Running the city-wide scenario on a database fork")
        out["fork"] = forks.city_scenario(plan, after, ctx.step)
    return out


def _summary(results: dict[str, dict]) -> dict:
    cs = compare.checks(results)
    return {"failing": sum(c["status"] == "fail" for c in cs.values()),
            "warn": sum(c["status"] in ("warn", "unknown") for c in cs.values()),
            "passing": sum(c["status"] == "pass" for c in cs.values()),
            "verdicts": {t: r["verdict"] for t, r in results.items()}}


def _ranked(tried: list[dict]) -> list[dict]:
    def key(t):
        return (t["error"] is not None, -t["fixed"], -t.get("better", 0), (t["cost"] or {}).get("total") or 0)
    return sorted(tried, key=key)
