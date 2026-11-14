"""Field audit: the CoStar researcher's version of record versus reality, across many properties.

First pass, plans and records only (no model calls): every cheap comparison on a sample of scans spread over homes,
apartment units, offices and industrial buildings, summarised by field (how often listed and measured area differ
by more than 10%, how often bedroom counts disagree, ...). Second pass: the most interesting disagreements get the
full check with the aerial photo and the panoramas, and a judgement on which side looks wrong. Every row names its
scan, the record field path, both values and the evidence, so the table can go on a roadmap and be traced back.

    uv run python -m threshold.tools.field_audit --out "$THRESHOLD_DATA_DIR/shots/tools/field_audit"
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from .. import Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from ..record_vs_reality import audit, gather
from ..record_vs_reality import claims as cl

QUOTA = {"home": 50, "apartment unit": 40, "office": 35, "industrial": 25}
FAMILY = {"living_area": "area", "unit_area": "area", "title_area": "area", "beds": "bedrooms", "unit_beds": "bedrooms",
          "title_beds": "bedrooms", "baths": "bathrooms", "unit_baths": "bathrooms", "title_baths": "bathrooms",
          "stories": "stories", "ceiling_height": "ceiling height", "ceiling_height_main": "ceiling height",
          "walk_in_closet": "walk-in closet", "laundry_in_unit": "laundry", "garage": "garage",
          "typical_floor_area": "area", "gross_area": "area", "rentable_area": "area"}
TABLE = ["rank", "sid", "name", "kind", "scope", "field", "claim_key", "record_value", "record_unit", "record_path",
         "record_origin", "measured_value", "measured_unit", "ratio", "verdict", "confidence", "severity", "reason",
         "evidence", "deep_verdict", "judgement", "judgement_reason", "plan_walls"]


class Inputs(BaseModel):
    scans: list[str] | None = field(None, description="Scan ids to audit; empty draws a spread sample")
    sample: int = field(150, ge=4, le=400, description="Scans to draw when none are given")
    deep_top: int = field(15, ge=0, le=30, description="Disagreements to re-check with the aerial photo and panoramas")


def _h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def draw(n: int = 150) -> list[tuple[str, str]]:
    """(sid, kind) pairs spread over homes, apartment units, offices and industrial, the same draw every time.
    Scans whose model is already in the cache come first, to spare the shared Matterport key."""
    from ...config import CACHE
    from ...sources import costar
    j = costar.joins()
    cached = {f.stem for f in (CACHE / "model").glob("*.json")}
    ptype = {}
    pools: dict[str, list[str]] = defaultdict(list)
    for sid in j["model_listing"]:
        pools["home"].append(sid)
    for sid, pids in j["model_property"].items():
        pid = pids[0]
        if pid not in ptype:
            ptype[pid] = (costar.get("commercial-property", pid) or {}).get("propertyType")
        t = ptype[pid]
        if t == 11:
            if "beds" in cl.parse_title(scan_name(sid)):
                pools["apartment unit"].append(sid)
        elif t == 5:
            pools["office"].append(sid)
        elif t in (2, 7):
            pools["industrial"].append(sid)
    total = sum(QUOTA.values())
    out = []
    for kind, q in QUOTA.items():
        k = max(1, round(n * q / total))
        pool = sorted(pools[kind], key=lambda s: (s not in cached, _h(s)))
        out += [(s, kind) for s in pool[:k]]
    return out


def scan_name(sid: str) -> str:
    from ...sources import index
    return (index.rows().get(sid) or {}).get("name") or ""


def severity(c: dict) -> float:
    """How far apart record and measurement are, on one scale for every field (0 = agree)."""
    if c["verdict"] != "contradicted":
        return 0.0
    w = {"high": 1.0, "medium": 0.8, "low": 0.4}[c["confidence"]]
    if c.get("ratio"):
        return w * abs(math.log(c["ratio"]))
    cv, mv = c["claim"]["value"], c["measured"]["value"]
    if isinstance(cv, (int, float)) and isinstance(mv, (int, float)) and not isinstance(cv, bool):
        return w * abs(mv - cv) / max(1.0, abs(cv))
    return w * 0.5


def rows_for(sid: str, kind: str, plan: dict, a: dict) -> list[dict]:
    out = []
    for c in a["comparisons"]:
        if c["verdict"] == "context":
            continue
        ev = ""
        if c.get("rooms"):
            ev = "rooms counted: " + " ".join(r["room"] for r in c["rooms"]["counted"])
        elif c.get("media"):
            ev = " ".join(f"{m['kind']}:{m['ref']}" for m in c["media"][:3])
        elif c.get("pins"):
            ev = "rooms: " + " ".join(c["pins"][:8])
        elif c.get("anchor"):
            ev = str(c["anchor"])
        out.append({"sid": sid, "name": plan.get("name"), "kind": kind, "scope": a["scan"]["scope"],
                    "field": FAMILY.get(c["key"], c["key"].replace("_", " ")), "claim_key": c["key"],
                    "record_value": c["claim"]["value"], "record_unit": c["claim"].get("unit"),
                    "record_path": c["claim"]["path"], "record_origin": c["claim"]["origin"],
                    "measured_value": c["measured"]["value"], "measured_unit": c["measured"].get("unit"),
                    "ratio": round(c["ratio"], 3) if c.get("ratio") else None, "verdict": c["verdict"],
                    "confidence": c["confidence"], "severity": round(severity(c), 3), "reason": c["reason"],
                    "evidence": ev, "plan_walls": bool((plan.get("quality") or {}).get("walls"))})
    return out


def cheap(sids: list[tuple[str, str]], plans, step=lambda s: None) -> tuple[list[dict], list[dict]]:
    """First pass over many scans: plans and records only. Returns (rows, skipped)."""
    def one(pair):
        sid, kind = pair
        try:
            plan = plans(sid)
        except Exception as e:  # noqa: BLE001 - one unreachable scan must not stop the audit
            return [], {"sid": sid, "kind": kind, "why": f"plan: {str(e)[:120]}"}
        rec = gather.record(sid)
        if rec is None:
            return [], {"sid": sid, "kind": kind, "why": "no record"}
        return rows_for(sid, kind, plan, audit(plan, rec, deep=False)), None

    rows, skipped = [], []
    with ThreadPoolExecutor(4) as ex:
        for i, (r, skip) in enumerate(ex.map(one, sids)):
            rows += r
            if skip:
                skipped.append(skip)
            if (i + 1) % 25 == 0:
                step(f"Read {i + 1} of {len(sids)} scans")
    return rows, skipped


def summary(rows: list[dict]) -> list[dict]:
    """Per field: scans compared, contradicted, cannot verify, and for area how often the gap exceeds 10%."""
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["field"]].append(r)
    out = []
    for f, rs in by.items():
        checked = [r for r in rs if r["verdict"] in ("confirmed", "contradicted")]
        bad = [r for r in checked if r["verdict"] == "contradicted"]
        row = {"field": f, "claims": len(rs), "checked": len(checked), "contradicted": len(bad),
               "cannot_verify": len(rs) - len(checked), "share": round(len(bad) / len(checked), 3) if checked else None,
               "by_kind": dict(Counter(r["kind"] for r in bad))}
        ratios = [r["ratio"] for r in checked if r["ratio"]]
        if ratios:
            row["over_10pct"] = sum(1 for x in ratios if abs(x - 1) > 0.10)
            row["median_ratio"] = round(sorted(ratios)[len(ratios) // 2], 3)
        out.append(row)
    return sorted(out, key=lambda r: (-(r["contradicted"]), r["field"]))


def pick(rows: list[dict], k: int) -> list[dict]:
    """The k most interesting disagreements: largest severity, at most k/3 per field and one per scan."""
    cap = max(2, k // 3)
    per: Counter = Counter()
    seen: set[str] = set()
    out = []
    for r in sorted((r for r in rows if r["verdict"] == "contradicted"), key=lambda r: -r["severity"]):
        partial = r["ratio"] and r["ratio"] < 0.6  # a partial scan: nothing to learn about the record
        if r["sid"] in seen or per[r["field"]] >= cap or partial:
            continue
        out.append(r)
        per[r["field"]] += 1
        seen.add(r["sid"])
        if len(out) == k:
            break
    return out


def judge(row: dict, plan: dict, deep: dict, labels: list[dict] | None) -> tuple[str, str]:
    """Which side looks wrong after the full check: ("record", why), ("measurement", why) or ("unclear", why)."""
    comps = {c["key"]: c for c in deep["comparisons"]}
    c = comps.get(row["claim_key"])
    if c and c["verdict"] == "confirmed":
        return "measurement", f"The full check confirms the claim: {c['reason'][:300]}"
    f = row["field"]
    if f == "area":
        if row["ratio"] and row["ratio"] < 0.6:
            return "measurement", "The scan covers well under the stated area: a partial scan, not a wrong record."
        others = [x for k, x in comps.items() if FAMILY.get(k) == "area" and k != row["claim_key"] and x.get("ratio")]
        agree = [x for x in others if x["verdict"] == "confirmed"]
        if agree:
            return "record", (f"A second source agrees with the scan: {agree[0]['claim']['origin']} says "
                              f"{agree[0]['claim']['value']} ({agree[0]['claim']['path']}).")
        st = comps.get("stories")
        if st and st["verdict"] == "contradicted" and (st["measured"]["value"] or 0) < (st["claim"]["value"] or 0):
            return "measurement", "The scan has fewer floors than the record's stories, so a floor was not scanned."
        fp = next((x for k, x in comps.items() if k in ("typical_floor_area", "gross_area") and x["layer"] == "vexcel"), None)
        if fp and fp["verdict"] == "confirmed" and row["kind"] != "home":
            return "measurement", "The aerial footprint agrees with the record, so the scan is the partial side."
        return "unclear", "No second source decides it; check the excluded rooms and the floor plan by eye."
    if f == "bedrooms" and labels is not None:
        n = sum(1 for x in labels if x["label"] == "Bedroom")
        want, got = row["record_value"], row["measured_value"]
        if n == want:
            return "measurement", (f"Reading the panoramas finds {n} bedrooms, as the record says; Matterport's labels "
                                   "missed one (a room furnished otherwise).")
        if n == got:
            return "record", f"Reading the panoramas also finds {n} bedrooms, so the record's count looks wrong."
        return "unclear", f"Reading the panoramas finds {n} bedrooms, matching neither side."
    if f == "bathrooms" and c:
        if c["verdict"] == "contradicted" and "panoramas" in c["reason"]:
            return "record", "With tubs and showers read from the panoramas the scan still disagrees: " + c["reason"][:200]
        return "unclear", "The bathroom panoramas were not all read, so full and half baths are a size guess."
    if f == "stories":
        est = None
        site = deep["evidence"].get("site")
        if site:
            h = next((x["value"] for x in site["facts"] if x["id"] == "roof_height"), None)
            shape = next((x["value"] for x in site["facts"] if x["id"] == "roof_shape"), None)
            if h:
                est = max(1, round((h - (2.0 if shape not in (None, "flat") else 0)) / 3.0))
        if est == row["record_value"]:
            return "measurement", f"The roof height suggests {est} stories, as the record says; a floor went unscanned."
        if est == row["measured_value"]:
            return "record", f"The roof height suggests {est} stories, as the scan has."
        return "unclear", "The roof height decides neither way."
    if f == "ceiling height":
        if row["kind"] == "industrial" and (row["measured_value"] or 0) < (row["record_value"] or 0):
            return "measurement", "The scan covers the office part of a warehouse; the clear height is in the bays."
        return "unclear", "Dropped ceilings and partial scans both lower the measured height."
    return "unclear", (c["reason"][:200] if c else "The full check did not reach this claim.")


def deep_check(picked: list[dict], plans, step=lambda s: None) -> None:
    """Run the full check on each picked row and add deep_verdict, judgement and judgement_reason to it."""
    for i, row in enumerate(picked):
        plan = plans(row["sid"])
        rec = gather.record(row["sid"])
        d = audit(plan, rec, deep=True)
        labels = None
        if row["field"] == "bedrooms":
            cands = [r["id"] for r in plan["rooms"] if (r.get("area") or 0) >= 6 and r.get("label") in
                     (None, "Bedroom", "Office", "Den", "Bonus Room", "Loft", "Family Room", "Game Room", "Living Room")]
            try:
                labels = gather.SOURCES["labels"](plan, cands)
            except Exception as e:  # noqa: BLE001
                labels = None
                row["judgement_reason"] = f"room labelling failed: {str(e)[:100]}"
            row["vision_labels"] = labels
        c = next((x for x in d["comparisons"] if x["key"] == row["claim_key"]), None)
        row["deep_verdict"] = c["verdict"] if c else None
        row["deep"] = c
        row["judgement"], row["judgement_reason"] = judge(row, plan, d, labels)
        step(f"Full check {i + 1} of {len(picked)}: {row['sid']} {row['field']}: {row['judgement']} looks wrong")


def run_audit(sids: list[tuple[str, str]], plans, deep_top: int = 15, step=lambda s: None) -> dict:
    rows, skipped = cheap(sids, plans, step)
    step(f"First pass: {len(rows)} claims on {len(sids) - len(skipped)} scans ({len(skipped)} skipped)")
    for i, r in enumerate(sorted(rows, key=lambda r: -r["severity"])):
        r["rank"] = i + 1
    top = pick(rows, deep_top) if deep_top else []
    if top:
        deep_check(top, plans, step)
    return {"rows": sorted(rows, key=lambda r: r["rank"]), "summary": summary(rows), "top": top, "skipped": skipped,
            "scans": [s for s, _ in sids]}


SRC = Source(layer="costar", method="lookup", confidence="high", note="Counts over the sampled scans' comparisons")


def to_result(out: dict) -> ToolResult:
    checks, metrics, findings = [], [], []
    for s in out["summary"]:
        fid = s["field"].replace(" ", "_")
        share = s["share"]
        checks.append(Check(id=fid, rule=f"{s['field'].capitalize()}: record and measurement disagree",
                            measured=s["contradicted"], threshold=s["checked"], unit="scans",
                            status="unknown" if share is None else "fail" if share > 0.25 else "warn" if share > 0.1 else "pass",
                            findings=[f"field_audit:{t['sid']}:{t['claim_key']}" for t in out["top"] if t["field"] == s["field"]]))
        if share is not None:
            metrics.append(Metric(id=f"disagree.{fid}", label=s["field"].capitalize(), value=round(100 * share),
                                  unit="%", source=SRC))
    for t in out["top"]:
        st = {"record": "fail", "measurement": "warn", "unclear": "unknown"}[t["judgement"]]
        c = t.get("deep") or {}
        findings.append(Finding(
            id=f"field_audit:{t['sid']}:{t['claim_key']}",
            title=f"{t['field'].capitalize()}: the {t['judgement']} looks wrong" if t["judgement"] != "unclear"
            else f"{t['field'].capitalize()}: unclear which side is wrong",
            status=st, detail=f"{t['name']} ({t['kind']}, {t['scope']}). {t['reason']} Full check: {t['judgement_reason']}",
            anchor=c.get("anchor") or ({"sid": t["sid"], "room": c["pins"][0]} if c.get("pins") else None),
            source=Source(layer=c.get("layer", "matterport"), method=c.get("method", "geometry"),
                          confidence=c.get("confidence", t["confidence"]), note=t["record_path"]),
            media=(c.get("media") or [])[:4]))
    n = len(out["scans"]) - len(out["skipped"])
    worst = [s for s in out["summary"] if s["share"]][:3]
    text = (f"{n} scans audited, {len(out['rows'])} claims compared. Most disagreement: "
            + ", ".join(f"{s['field']} ({s['contradicted']} of {s['checked']})" for s in worst) + ".") if worst else \
        f"{n} scans audited; no field disagreed."
    total = [Metric(id="scans", label="Scans audited", value=n, unit="", source=SRC),
             Metric(id="claims", label="Claims compared", value=len(out["rows"]), unit="", source=SRC),
             Metric(id="contradicted", label="Contradicted", value=sum(1 for r in out["rows"] if r["verdict"] == "contradicted"),
                    unit="", source=SRC)]
    return ToolResult(scope={"sids": out["scans"]}, verdict=Verdict(status="warn" if worst else "pass", text=text),
                      metrics=total + metrics, checks=checks, findings=findings)


@tool(id="field_audit", title="Field audit", icon="table",
      summary="Across many scans, which record fields disagree with what the scans measure, ranked, with evidence.",
      model_description="For a set of scans (or a spread sample of homes, apartment units, offices and industrial), "
                        "compare every cheap record claim with the plan, count disagreements by field (area off by more "
                        "than 10%, bedroom and bathroom counts, stories, ceiling height), then re-check the most "
                        "interesting disagreements with the aerial photo and panoramas and judge which side looks "
                        "wrong. Slow: minutes for 150 scans.",
      personas=["costar_researcher"],
      requires=[{"layer": "costar.property"}, {"layer": "matterport.rooms"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "EvidenceStrip", "StepLog"],
      annotations={"cost": "slow"}, examples=["Where are our records most often wrong?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sids = [(s, "given") for s in inputs.scans] if inputs.scans else draw(inputs.sample)
    if inputs.scans:
        sids = [(s, _kind(s)) for s, _ in sids]
    ctx.step(f"Auditing {len(sids)} scans")
    return to_result(run_audit(sids, ctx.plan, inputs.deep_top, ctx.step))


def _kind(sid: str) -> str:
    rec = gather.record(sid)
    k = cl.kind_of(rec)
    return "apartment unit" if k == "apartment" and "beds" in cl.parse_title(scan_name(sid)) else k


__all__ = ["TABLE", "draw", "run_audit", "summary", "to_result"]
