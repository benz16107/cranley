"""Write the generated parts of the site from the code, so the docs cannot drift from it.

    cd server && uv run python ../site/scripts/generate.py

Reads the tool registry (manifests), the personas, the layer catalogue, FastAPI's OpenAPI schema, docs/MCP.md and the
tracks in docs/story.md. Runs every tool it can on the two made-up RoomPlan test scans (no real place) with an empty
data folder and the network switched off, so the examples on each tool page are real results and hold no sponsor data.
Writes Markdown under src/content/ and one JSON file, src/generated/site.json. Everything it writes is committed.
"""
from __future__ import annotations

import collections
import glob
import json
import math
import os
import pathlib
import re
import shutil
import signal
import socket
import sys
import tempfile

SITE = pathlib.Path(__file__).resolve().parent.parent
REPO = SITE.parent
os.environ["THRESHOLD_DATA_DIR"] = tempfile.mkdtemp(prefix="site-gen-")  # empty: no keys, no sponsor data
for k in ("TIGER_DATABASE_URL", "MONGODB_URI", "THRESHOLD_STORE", "ANTHROPIC_API_KEY", "LANGSMITH_TRACING"):
    os.environ.pop(k, None)
sys.path.insert(0, str(REPO / "server"))


def _no_network(*a, **k):
    raise OSError("the network is off while the docs are generated")


socket.socket.connect = _no_network          # tools that need an outside source say so instead of fetching
socket.create_connection = _no_network

from threshold.layers import catalog  # noqa: E402
from threshold.roomplan import convert, demo  # noqa: E402
from threshold.tools import types as T  # noqa: E402
from threshold.tools.registry import NotApplicable, ToolContext, ToolError, load  # noqa: E402

DOCS = SITE / "src/content/docs/docs"
TRACKS = SITE / "src/content/tracks"
HOME, CAFE = "u_testhome0001", "u_testcafe0001"
PLANS = {HOME: convert(demo.home(), HOME, "Test home (made up)"), CAFE: convert(demo.cafe(), CAFE, "Test cafe (made up)")}
ON_CAFE = {"fire_preplan", "egress_routes", "facility_audit", "office_fit", "takeoff_bid", "life_safety_census", "camera_coverage"}
# Inputs a person would be asked for, given here so the example can run. Shown on the page as the inputs used.
SLOW = {"smoke_clock"}  # runs NIST's CFAST for minutes; a subprocess the 20 s alarm cannot stop
ASKED = {"flood_rehearsal": {"depth_m": 0.6}, "valuables_height": {"depth_m": 0.6}, "office_fit": {"headcount": 6},
         "storm_plan": {"depth_m": 0.6, "hours_left": 6, "adults": 2}}
LAYER = {  # the App look's words for a requirement (web/src/skins/app/lib/tools.ts)
    "matterport.walls": "Wall outline", "matterport.rooms": "Rooms", "matterport.room_labels": "Room names",
    "matterport.openings": "Doors and windows", "matterport.panos": "360° photos", "matterport.panoramas": "360° photos",
    "matterport.defurnished": "Empty-room photos", "matterport.geo": "Scan position", "matterport.index": "Scan index",
    "vexcel.ortho": "Aerial photo", "vexcel.oblique": "Angled aerial photos", "vexcel.property": "Aerial property facts",
    "vexcel.elevation": "Ground heights", "vexcel.dtm": "Ground heights", "vexcel.dsm": "Roof heights",
    "vexcel.footprint": "Building footprint", "costar.property": "Property record", "costar.listing": "Listing",
    "drone.photos": "Drone photos", "drone.splat": "Drone capture", "threshold.facts": "Facts database",
    "threshold.facts.rooms": "Room descriptions", "threshold.measures": "Measures table", "osm.streets": "Street map"}
FROM = {"matterport": "the scan", "vexcel": "aerial photos", "costar": "the property record", "drone": "the drone capture",
        "model": "a model", "phone": "the phone scan"}
OVERLAY = {"lens": "a colour per room", "rule": "doors, walls or rooms coloured by status", "pins": "pins on what it found",
           "route": "a route with its narrow points", "water": "a water level", "box": "a box or 3D model placed in the room"}
GROUPS = {  # who the home page lists each persona under
    "Getting in and around": "wheelchair_user wheelchair_home_search wheelchair_van_owner older_adult_family "
                             "aging_in_place_planner furniture_mover car_owner rv_boat_owner robot_maker",
    "Safety and hazards": "fire_captain fire_training_officer community_risk_officer emergency_manager "
                          "houston_homeowner_storm la_fire_homeowner la_quake_prep home_security_family pool_safety_parent",
    "Home life": "renter_listing renter_checking_claims parent_young_kids family_neighbourhood_check teen_soccer_family "
                 "dog_owner_home senior_dog_owner cat_owner_apartment remote_worker light_sleeper room_chooser "
                 "feng_shui_curious home_gym_builder racket_player solar_homeowner virtual_stager location_scout",
    "Business": "business_site_check office_tenant office_relocation industrial_tenant_rep retail_site_selector "
                "facility_manager apartment_manager daycare_operator cleaning_bidder truck_dispatcher",
    "Research and underwriting": "costar_researcher costar_research_lead commercial_underwriter insurance_underwriter "
                                 "amenity_auditor"}
API_TITLES = {"data": "Scans and buildings", "aerial": "Aerial", "agent": "Agent and workspace", "agent_live": "Agent, live view",
              "capture": "Phone captures", "facts": "Facts database", "history": "Past work", "interior_splat": "Interior splats",
              "layers": "Map layers", "live": "Live sync", "report": "Reports", "search": "Search", "sensors": "Phone sensors",
              "show": "Flood and smoke shows", "site_media": "Site media", "user_scans": "Your own scans",
              "whatif": "What-if renovations", "world": "3D city and terrain"}


def slug(title: str) -> str:
    """The id Astro gives a Markdown heading (github-slugger): lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")


def esc(s) -> str:
    """Text for a Markdown paragraph or table cell."""
    return re.sub(r"\s+", " ", str(s)).replace("|", "\\|").replace("<", "&lt;").replace("{", "&#123;").strip()


def num(v) -> str:
    if v is None:
        return "not measured"
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return esc(v)
    return str(int(v)) if float(v).is_integer() else f"{v:.3f}".rstrip("0").rstrip(".")


def source_words(s: dict) -> str:
    frm = FROM.get(s["layer"], s["layer"])
    return {"geometry": f"Measured from {frm}", "vision": f"Seen in {frm}", "lookup": f"Looked up in {frm}",
            "simulation": "Simulated" if s["layer"] == "model" else f"Simulated from {frm}",
            "sensor": "Read on site by the phone", "manual": "Measured on site by hand"}.get(s["method"], f"From {frm}")


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def page(title: str, description: str, body: str, **front) -> str:
    extra = "".join(f"{k}: {json.dumps(v)}\n" for k, v in front.items())
    return f"---\ntitle: {json.dumps(title)}\ndescription: {json.dumps(description)}\n{extra}---\n\n{body}"


def table(head: list[str], rows: list[list]) -> str:
    if not rows:
        return ""
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]) + "\n"


# ---------- personas ----------
def personas() -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(REPO / "server/threshold/agent/personas/*.json"))):
        p = json.loads(pathlib.Path(f).read_text())
        if isinstance(p, dict) and "tools" in p and "title" in p:
            out.append(p)
    return out


def prefs(people: list[dict]) -> dict:
    """Every preset threshold, first persona wins. This is what fills a tool's `x-pref` inputs in the examples."""
    out, by = {}, {}
    for p in people:
        for k, v in (p.get("thresholds") or {}).items():
            if k not in out:
                out[k], by[k] = v, p["title"]
    return {"values": out, "from": by, "people": people}


# ---------- one example run per tool ----------
class _Timeout(Exception):
    pass


def _alarm(*_):
    raise _Timeout()


def example(tool, pref: dict, persona: dict | None = None) -> dict:
    """Run a tool on a test scan. Returns what happened, never raises."""
    m = tool.manifest
    who = persona or next((p for p in pref["people"] if m.id in p["tools"] and p.get("thresholds")), {"thresholds": {}, "title": ""})
    sid = CAFE if m.id in ON_CAFE else HOME
    props, required = m.inputs.get("properties", {}), m.inputs.get("required", [])
    inputs, said = {}, []
    for k, s in props.items():
        if k in ASKED.get(m.id, {}):
            inputs[k] = ASKED[m.id][k]
            said.append(f"`{k} = {json.dumps(inputs[k])}` (an answer given for this example)")
        elif s.get("x-source") == "selection.scan" or k == "scan":
            inputs[k] = sid
        elif k == "place":
            inputs[k] = {"scan": sid}
        elif s.get("x-pref") in who["thresholds"]:
            inputs[k] = who["thresholds"][s["x-pref"]]
            said.append(f"`{k} = {json.dumps(inputs[k], ensure_ascii=False)}` (preset of the persona \"{who['title']}\")")
        elif k in required and s.get("x-pref") in pref["values"]:
            inputs[k] = pref["values"][s["x-pref"]]
            said.append(f"`{k} = {json.dumps(inputs[k], ensure_ascii=False)}` (preset of the persona \"{pref['from'][s['x-pref']]}\")")
    where = "test cafe" if sid == CAFE else "test home"
    missing = [k for k in required if k not in inputs]
    if missing:
        return {"where": where, "state": "needs", "missing": missing}
    if m.id in SLOW:
        return {"where": where, "state": "slow"}
    ctx = ToolContext(plans=lambda s: PLANS[s] if s in PLANS else (_ for _ in ()).throw(LookupError(s)))
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(20)
    try:
        r = tool.handler(ctx, tool.inputs.model_validate(inputs)).model_dump(mode="json")
        return {"where": where, "state": "ran", "inputs": said, "result": r, "steps": ctx.steps}
    except NotApplicable as e:
        return {"where": where, "state": "cannot", "why": str(e)}
    except ToolError as e:
        return {"where": where, "state": "cannot", "why": str(e)}
    except _Timeout:
        return {"where": where, "state": "slow"}
    except Exception as e:  # noqa: BLE001  a missing key or binary: the tool needs something the generator does not have
        return {"where": where, "state": "cannot", "why": str(e).split("\n")[0][:300]}
    finally:
        signal.alarm(0)


def example_md(ex: dict) -> str:
    place = f"the made-up {ex['where']}"
    head = (f"## On {place}\n\nThis section was written by running the tool when the docs were built, on a hand-made RoomPlan export "
            f"(no real place was scanned), with no sponsor keys and the network switched off.\n\n")
    if ex["state"] == "needs":
        return head + "Not run: it needs " + ", ".join(f"`{k}`" for k in ex["missing"]) + ", which only a person or a phone on site can give.\n"
    if ex["state"] == "slow":
        return head + "Not run when the docs are built: it takes minutes. In the app the agent asks before it starts.\n"
    if ex["state"] == "cannot":
        return head + f"<p class=\"verdict\"><span class=\"st unknown\">Cannot answer here</span> {esc(ex['why'])}</p>\n\nA phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.\n"
    r = ex["result"]
    out = head
    if ex["inputs"]:
        out += "Inputs used: " + "; ".join(ex["inputs"]) + ".\n\n"
    out += f"<p class=\"verdict\"><span class=\"st {r['verdict']['status']}\">{r['verdict']['status'].capitalize()}</span> {esc(r['verdict']['text'])}</p>\n\n"
    out += table(["Value", "Result", "Where it came from", "Reliability"],
                 [[esc(m["label"]), f"<span class=\"num\">{num(m['value'])}{(' ' + esc(m['unit'])) if m['unit'] else ''}</span>",
                   source_words(m["source"]), m["source"]["confidence"]] for m in r["metrics"][:10]])
    if len(r["metrics"]) > 10:
        out += f"\n{len(r['metrics']) - 10} more values are in the full result.\n"
    if r["checks"]:
        shown = r["checks"][:8]
        out += "\n" + table(["Check", "Measured", "Against", "Status"],
                            [[esc(c["rule"]), f"<span class=\"num\">{num(c['measured'])}</span>" if c["measured"] is not None else "not measured",
                              f"<span class=\"num\">{num(c['threshold'])}{(' ' + esc(c['unit'])) if c['unit'] else ''}</span>" if c["threshold"] is not None else "",
                              f"<span class=\"st {c['status']}\">{c['status']}</span>"] for c in shown])
        if len(r["checks"]) > 8:
            out += f"\n{len(r['checks']) - 8} more checks are in the full result.\n"
    counts = collections.Counter(f["status"] for f in r["findings"])
    if counts:
        out += "\nFindings: " + ", ".join(f"{n} {s}" for s, n in counts.items()) + ".\n"
    if ex["steps"]:
        out += "\nWhat it reported while it ran:\n\n" + "".join(f"1. {esc(s)}\n" for s in ex["steps"][:8])
    return out


def sources_of(ex: dict) -> list[dict]:
    if ex["state"] != "ran":
        return []
    seen, out = set(), []
    for item in ex["result"]["metrics"] + ex["result"]["findings"]:
        s = item["source"]
        key = (s["layer"], s["method"], s["confidence"], s.get("note"))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


# ---------- tool pages ----------
def input_rows(schema: dict) -> list[list]:
    rows, defs = [], schema.get("$defs", {})
    for k, s in schema.get("properties", {}).items():
        kinds = [x.get("type") or x.get("$ref", "").split("/")[-1] for x in s.get("anyOf", [s])]
        if "$ref" in s:
            kinds = [s["$ref"].split("/")[-1]]
        kind = " or ".join(x for x in kinds if x and x != "null")
        ref = next((x.split("/")[-1] for x in [s.get("$ref", "")] + [y.get("$ref", "") for y in s.get("anyOf", [])] if x), None)
        notes = [s.get("description") or (defs.get(ref, {}).get("description", "").split("\n")[0] if ref else "")]
        if s.get("x-ask"):
            notes.append(f"Asked as: \"{s['x-ask']}\"")
        if s.get("x-pref"):
            notes.append(f"Saved preference `{s['x-pref']}`.")
        if s.get("x-source"):
            notes.append("Filled from the selected building.")
        lim = [f"{w} {s[key]}" for key, w in (("minimum", "at least"), ("exclusiveMinimum", "more than"), ("maximum", "at most"), ("exclusiveMaximum", "less than")) if key in s]
        if lim:
            notes.append("Range: " + ", ".join(lim) + ".")
        if s.get("enum"):
            notes.append("One of: " + ", ".join(f"`{e}`" for e in s["enum"]) + ".")
        default = f"`{json.dumps(s['default'])}`" if "default" in s and s["default"] is not None else ""
        rows.append([f"`{k}`", esc(kind) + (f" ({esc(s['x-unit'])})" if s.get("x-unit") else ""), "yes" if k in schema.get("required", []) else "",
                     default, esc(" ".join(n if n.endswith((".", "\"")) else n + "." for n in notes if n))])
    return rows


def tool_md(tool, ex: dict, people: list[dict], approve: dict) -> str:
    m = tool.manifest
    who = [p for p in people if m.id in p["tools"] or p["id"] in m.personas]
    out = f"{esc(m.summary)}\n\n"
    if m.examples:
        out += "## What it answers\n\n" + "".join(f"- {esc(e)}\n" for e in m.examples) + "\n"
    out += f"For the agent, the tool is described as: {esc(m.model_description)}\n\n"
    if who:
        out += "## Who it is for\n\n" + ", ".join(f"[{esc(p['title'])}](/docs/reference/personas/#{slug(p['title'])})" for p in who) + ".\n\n"
    out += "## Inputs\n\n" + (table(["Input", "Type", "Required", "Default", "Notes"], input_rows(m.inputs)) or "None.\n") + "\n"
    out += ("An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to "
            "the person. The agent asks only for those.\n\n")
    out += "## Data used\n\n"
    if m.requires:
        out += table(["Layer", "Id", "Needed", "If it is missing"],
                     [[LAYER.get(r.layer, r.layer.split(".", 1)[-1].replace("_", " ").capitalize()), f"`{r.layer}`", r.need,
                       esc(r.fallback or ("The verdict is `unknown`, with the reason." if r.need == "required" else "The tool runs without it."))]
                      for r in m.requires])
    else:
        out += "It declares no data layer: it works from its inputs alone.\n"
    out += "\n## What it returns\n\nA [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.\n\n"
    if m.overlays:
        out += "- Draws on the building: " + "; ".join(OVERLAY.get(o, o) for o in m.overlays) + ".\n"
    if m.blocks:
        out += "- Panel blocks: " + ", ".join(f"`{b}`" for b in m.blocks) + ".\n"
    if m.table:
        out += "- Its own ranked table: " + ", ".join(esc(c.label) for c in m.table) + ".\n"
    out += f"- Speed: {m.annotations.cost}. " + ("Read-only.\n" if m.annotations.read_only else "**Writes** (a plan edit or a saved label), so over MCP it needs `--write`.\n")
    doc = re.sub(r"^Reference tool: ", "", (sys.modules[tool.handler.__module__].__doc__ or "").strip().split("\n\n")[0])
    doc = re.sub(r"[^.]*\b(?:thousand|\d{3,}) scans[^.]*\.\s*", "", doc)  # no dataset counts on the public site
    doc = re.sub(r"`?\$THRESHOLD_DATA_DIR/[\w./<>-]*`?", "the data folder", doc)
    if doc:
        out += "\n## How it works\n\n" + esc(doc[0].upper() + doc[1:]) + "\n"
    out += "\n## Reliability\n\n"
    src = sources_of(ex)
    if src:
        out += f"Sources this tool gave on the {ex['where']}:\n\n" + table(
            ["Where it came from", "Layer", "Method", "Reliability", "Note"],
            [[source_words(s), f"`{s['layer']}`", f"`{s['method']}`", s["confidence"], esc(s.get("note") or "")] for s in src])
        out += ("\nThe tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` "
                "whichever device made the scan, so a phone scan's geometry carries that label too.\n")
    else:
        out += "Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).\n"
    out += "\n## Limits\n\n"
    need = [LAYER.get(r.layer, r.layer) for r in m.requires if r.need == "required"]
    if need:
        out += f"- Needs: {', '.join(need).lower()}. On a scan without {'them' if len(need) > 1 else 'it'}, the verdict is `unknown` and says why.\n"
    if m.id in approve:
        out += f"- The agent asks before running it, because {esc(approve[m.id])}.\n"
    if m.annotations.cost == "slow":
        out += "- It is slow: progress steps reach the workspace while it runs.\n"
    out += "- A result is a planning aid, not an inspection.\n\n"
    out += example_md(ex)
    arg = "--scan <scan-id>" if "scan" in m.inputs.get("properties", {}) else "-i place='{\"scan\": \"<scan-id>\"}'" if "place" in m.inputs.get("properties", {}) else ""
    out += (f"\n## Run it\n\n```sh\nthreshold run {m.id} {arg}".rstrip() + f"\ncurl -X POST http://127.0.0.1:8787/api/tools/{m.id}/run -H 'content-type: application/json' -d '{{...inputs}}'\n```\n\n"
            f"Over MCP the tool is named `{m.id}`. See [MCP server and CLI](/docs/mcp/).\n")
    return page(m.title, m.summary, out, sidebar={"label": m.title})


# ---------- reference pages ----------
def layers_md() -> str:
    by = collections.defaultdict(list)
    for layer in catalog.LAYERS:
        by[layer.group].append(layer)
    order = [g for g in catalog.GROUPS if g in by] + [g for g in by if g not in catalog.GROUPS]
    out = (f"The explorer draws {len(catalog.LAYERS)} layers round a building. Each is served with its source, the date it was fetched "
           "and a reliability label. This table is generated from the layer catalogue in `server/threshold/layers/catalog.py`.\n\n"
           "Layers in the Coverage and Imagery groups that come from Matterport, Vexcel or CoStar need your own access to those sources.\n\n")
    for g in order:
        out += f"## {g}\n\n" + table(["Layer", "Source", "Licence or credit", "Reliability", "What it is and what it leaves out"], [
            [esc(x.title), f"[{esc(x.source)}]({x.source_url})" if x.source_url else esc(x.source), esc(x.attribution or x.licence or ""),
             x.confidence, esc(x.note) + (f" Data date {x.data_date}." if x.data_date else "") + ("" if len(x.cities) > 1 else f" {'Houston' if x.cities[0] == 'hou' else 'Los Angeles'} only.")]
            for x in by[g]]) + "\n"
    return page("Map layers", f"The {len(catalog.LAYERS)} map layers, their sources, licences and reliability.", out)


def personas_md(people: list[dict], tools: dict) -> str:
    out = (f"A persona is a preset: who the person is, the tools that fit their need, and thresholds that fill tool inputs. "
           f"There are {len(people)}. The composer uses them as starting points; a free sentence works too. Generated from "
           "`server/threshold/agent/personas/`.\n\n")
    for p in people:
        out += f"## {esc(p['title'])}\n\n{esc(p['who'])}\n\n"
        out += "Tools: " + ", ".join(f"[{esc(tools[t].manifest.title)}](/docs/tools/{t.replace('_', '-')}/)" if t in tools else f"`{t}`" for t in p["tools"]) + ".\n\n"
        if p.get("thresholds"):
            out += "Presets: " + ", ".join(f"`{k} = {json.dumps(v)}`" for k, v in p["thresholds"].items()) + ".\n\n"
    return page("Personas", f"The {len(people)} persona presets, their tools and thresholds.", out)


def schema_md(name: str, model, defs: dict) -> str:
    s = model.model_json_schema()
    defs.update(s.get("$defs", {}))
    rows = []
    for k, p in s.get("properties", {}).items():
        kinds = [x.get("type") or x.get("$ref", "").split("/")[-1] or x.get("const", "") for x in p.get("anyOf", p.get("oneOf", [p]))]
        if p.get("type") == "array":
            it = p.get("items", {})
            kinds = ["list of " + (it.get("$ref", "").split("/")[-1] or it.get("type") or " or ".join(x.get("$ref", "").split("/")[-1] for x in it.get("anyOf", it.get("oneOf", []))))]
        if p.get("enum"):
            kinds = [" or ".join(f"`{e}`" for e in p["enum"])]
        rows.append([f"`{k}`", esc(" or ".join(str(x) for x in kinds if x)), esc(p.get("description", ""))])
    return f"### {name}\n\n{esc((model.__doc__ or '').strip())}\n\n" + table(["Field", "Type", "Notes"], rows) + "\n"


def result_md() -> str:
    defs: dict = {}
    out = ("Every tool returns the same typed result. A renderer ignores what it does not know, and a typo in a tool fails at the "
           "tool, because every model forbids unknown fields. Generated from `server/threshold/tools/types.py`.\n\n## The result\n\n")
    for name, model in (("ToolResult", T.ToolResult), ("Verdict", T.Verdict), ("Metric", T.Metric), ("Check", T.Check),
                        ("Finding", T.Finding), ("Source", T.Source), ("Media", T.Media), ("Assumption", T.Assumption), ("Action", T.Action)):
        out += schema_md(name, model, defs)
    out += "## Overlays\n\nOne overlay draws in every view that can show it: the 3D building, the plan, a panorama or the map.\n\n"
    for name, model in (("LensOverlay", T.LensOverlay), ("RuleOverlay", T.RuleOverlay), ("PinsOverlay", T.PinsOverlay),
                        ("RouteOverlay", T.RouteOverlay), ("WaterOverlay", T.WaterOverlay), ("BoxOverlay", T.BoxOverlay)):
        out += schema_md(name, model, defs)
    out += "## The manifest\n\nOne per tool. It feeds the agent, the web tool dock, the MCP server and the CLI.\n\n"
    for name, model in (("Manifest", T.Manifest), ("Requirement", T.Requirement), ("Annotations", T.Annotations), ("Place", T.Place)):
        out += schema_md(name, model, defs)
    return page("Result format", "The typed result every tool returns, its overlays, and the tool manifest.", out)


def api_md() -> tuple[dict[str, str], int]:
    import importlib
    import pkgutil

    from threshold import api as api_pkg
    from threshold.api.app import app
    spec = app.openapi()
    comps = spec.get("components", {}).get("schemas", {})
    pages, total = {}, 0
    for mod in sorted(m.name for m in pkgutil.iter_modules(api_pkg.__path__)):
        module = importlib.import_module(f"threshold.api.{mod}")
        router = getattr(module, "router", None)
        if router is None:
            continue
        ops = []
        for r in router.routes:
            for method in sorted(getattr(r, "methods", None) or []):
                op = spec["paths"].get(r.path, {}).get(method.lower())
                if op and method not in ("HEAD", "OPTIONS"):
                    ops.append((method, r.path, op))
        if not ops:
            continue
        title = API_TITLES.get(mod, mod.replace("_", " ").capitalize())
        out = esc((module.__doc__ or "").strip().split("\n\n")[0]) + f"\n\nGenerated from FastAPI's OpenAPI schema for `server/threshold/api/{mod}.py`.\n\n"
        for method, path, op in ops:
            total += 1
            out += f"## `{method} {path}`\n\n"
            if op.get("description"):
                out += esc(op["description"]) + "\n\n"
            params = op.get("parameters", [])
            if params:
                out += table(["Parameter", "In", "Type", "Required", "Default", "Notes"], [
                    [f"`{p['name']}`", p["in"], esc(_kind(p.get("schema", {}))), "yes" if p.get("required") else "",
                     f"`{json.dumps(p['schema']['default'])}`" if p.get("schema", {}).get("default") is not None else "", esc(p.get("description") or p.get("schema", {}).get("description", ""))]
                    for p in params]) + "\n"
            body = (op.get("requestBody") or {}).get("content", {})
            for ctype, b in body.items():
                ref = b.get("schema", {}).get("$ref", "").split("/")[-1]
                out += f"Body (`{ctype}`)" + (f": `{ref}`\n\n" if ref else ": " + esc(_kind(b.get("schema", {}))) + "\n\n")
                if ref in comps:
                    out += table(["Field", "Type", "Required", "Notes"], [
                        [f"`{k}`", esc(_kind(v)), "yes" if k in comps[ref].get("required", []) else "", esc(v.get("description", ""))]
                        for k, v in comps[ref].get("properties", {}).items()]) + "\n"
            ok = op.get("responses", {}).get("200", {}).get("content", {})
            if ok:
                out += "Returns: " + ", ".join(f"`{c}`" for c in ok) + ".\n\n"
        pages[mod] = page(title, f"HTTP API: {title.lower()}.", out, sidebar={"label": title})
    return pages, total


def _kind(s: dict) -> str:
    if "$ref" in s:
        return s["$ref"].split("/")[-1]
    if "anyOf" in s:
        return " or ".join(k for k in (_kind(x) for x in s["anyOf"]) if k != "null")
    if s.get("type") == "array":
        return "list of " + _kind(s.get("items", {}))
    return s.get("type", "any")


def mcp_md(tools: dict) -> str:
    text = (REPO / "docs/MCP.md").read_text()
    text = re.sub(r"^# .*\n", "", text, count=1)
    ro = sum(1 for t in tools.values() if t.manifest.annotations.read_only)
    text = re.sub(r"\(\d+ read-only today", f"({ro} read-only today", text)
    text = text.replace("Threshold's tools", "Cranley's tools").replace("Threshold over MCP", "Cranley over MCP")
    note = ("The code name `threshold` stays on the package, the command and the MCP server. This page is generated from "
            "[`docs/MCP.md`](https://github.com/benz16107/cranley/blob/main/docs/MCP.md).\n\n")
    return page("MCP server and CLI", "Use every Cranley tool from Claude Code, Claude Desktop, Cursor, a LangChain agent or a terminal.", note + text.strip())


def story_tracks() -> list[str]:
    """The `### ` sections under `## Tracks` in docs/story.md, as far as the next `## ` heading or rule. docs/story.md is
    also the team's working file: a paragraph that starts with "Team note:" is for the team and never reaches a page."""
    block = re.split(r"\n(?:---\n|## )", (REPO / "docs/story.md").read_text().split("\n## Tracks\n", 1)[1], maxsplit=1)[0]
    out = []
    for sec in re.split(r"\n(?=### )", block):
        if sec.startswith("### "):
            head, body = sec.split("\n", 1)
            out.append(head + "\n" + "\n\n".join(par for par in body.split("\n\n") if not par.lstrip().startswith(("Team note", "**Team note"))))
    return out


def tracks_md() -> dict[str, str]:
    """One page per sponsor track, from docs/story.md."""
    out = {}
    for sec in story_tracks():
        head, body = sec.split("\n", 1)
        # the story marks its own team notes; anything like one that still gets here stops the build
        assert not re.search(r"Team note|question \d|asked of Ben|THRESHOLD_DATA_DIR|lead's server|\?as=|not merged yet|`reports/", body), head
        slug = next((s for key, s in (("CoStar", "costar"), ("Amazon", "amazon"), ("Peri", "peri"), ("LangChain", "langchain"), ("Photon", "photon"),
                                      ("Tiger", "tiger-data"), ("MongoDB", "mongodb"), ("HackPrinceton", "hackprinceton")) if key in head), None)
        if slug and slug != "hackprinceton":  # the main-track note is a choice still open, not a page
            out[slug] = f"---\ntitle: {json.dumps(head[4:].strip().replace(' (main target)', ''))}\n---\n\n{body.strip()}\n"
    return out


SKIPPED = {
    "langchain": [("`memory=` (AGENTS.md files)", "The person's preferences already go into the prompt, so a static file would repeat it."),
                  ("Background subagents", "They need an Agent Protocol server. Slow tools already run in the background, and subagents run in parallel."),
                  ("Sandboxes and a shell", "The agent runs no shell. Every action is a typed tool, and a shell would only add risk."),
                  ("Per-model harness profiles", "There is one model, so there is nothing to tune per model.")],
    "tiger-data": [("Tiger MCP server", "It runs with the service owner's credentials. The agent's own read-only SQL role, with a 5 second timeout, is stricter."),
                   ("Tiered storage, read replicas, high availability", "Paid or operations features with no use at this size."),
                   ("Gapfill and time-weighted hyperfunctions", "No view plots a gap-filled or time-weighted series yet."),
                   ("Chunk skipping", "The columnstore policies already compress older chunks.")],
    "mongodb": [("Atlas Triggers", "They need App Services keys. Change streams already react to inserts inside the server."),
                ("Stream Processing, Online Archive, Data Federation", "Paid tiers, and no stream or archive need at a weekend's volume."),
                ("Queryable Encryption", "No field is more sensitive than the documents as a whole, and it would need a key service."),
                ("Atlas Charts", "The app draws its own panels from the result objects.")],
}


def sponsor_md() -> str:
    """The feature tables of the three sponsor sections in docs/story.md, with what was left out and why."""
    story = "\n".join(story_tracks())
    out = ("Each sponsor feature below does a job in the product. The rule for this list: a feature is used only where it does one. "
           "The tables are generated from the tracks in `docs/story.md`.\n\n")
    for key, slug, title, lead in (
            ("LangChain", "langchain", "LangChain: deepagents, LangGraph and LangSmith", "The investigator is one deep agent with subagents. See [the agent](/docs/concepts/agent/)."),
            ("Tiger", "tiger-data", "Tiger Cloud", "Tiger Cloud is the building facts database: what was measured, when, and how it changed."),
            ("MongoDB", "mongodb", "MongoDB Atlas", "Atlas holds the people side: workspaces, their operation logs, live sync, memory and search over past work.")):
        sec = next(s for s in re.split(r"\n(?=### )", story) if s.startswith("### ") and key in s.split("\n", 1)[0])
        rows = re.search(r"(\| Feature \|.*?)(?:\n\n|\Z)", sec, re.S).group(1)
        out += f"## {title}\n\n{lead}\n\n{rows.strip()}\n\n### Left out, and why\n\n" + table(["Feature", "Why not"], [[a, b] for a, b in SKIPPED[slug]])
        out += f"\nThe track page: [{title.split(':')[0]}](/tracks/{slug}/).\n\n"
    sec = next(s for s in re.split(r"\n(?=### )", story) if s.startswith("### ") and "Photon" in s.split("\n", 1)[0])
    rows = re.search(r"(\| What a person does \|.*?)(?:\n\n|\Z)", sec, re.S).group(1)
    rules = re.search(r"Rules it keeps:.*?(?:\n\n|\Z)", sec, re.S).group(0).strip()
    state = re.search(r"\*\*State[^\n]*(?:\n[^\n]+)*", sec).group(0).strip()
    out += ("## Photon\n\nOn Photon 2.0 the same agent and the same measuring tools answer in iMessage and on a phone call. "
            f"It runs on the same tool registry and the same workspace document as every other way in.\n\n{rows.strip()}\n\n{rules}\n\n{state}\n\n"
            "The track page: [Photon](/tracks/photon/).\n")
    return page("Sponsor integrations", "What each LangChain, MongoDB Atlas, Tiger Data and Photon feature is used for.", out)


# ---------- the hero drawing ----------
def drawing(sid: str, tools: dict, pref: dict) -> dict:
    """The test home's plan and four real results on it, turned upright and scaled for an SVG."""
    plan = PLANS[sid]
    who = next(p for p in pref["people"] if p["id"] == "wheelchair_user")
    long = max(plan["walls"], key=lambda w: w["length"])
    a = -math.atan2(long["b"][1] - long["a"][1], long["b"][0] - long["a"][0])
    c, s = math.cos(a), math.sin(a)
    turn = lambda p: (p[0] * c - p[1] * s, p[0] * s + p[1] * c)  # noqa: E731
    pts = [turn(w[k]) for w in plan["walls"] for k in ("a", "b")]
    x0, y1 = min(p[0] for p in pts), max(p[1] for p in pts)
    px = lambda p: [round((turn(p)[0] - x0) * 100), round((y1 - turn(p)[1]) * 100)]  # noqa: E731  centimetres, y down
    walls = {w["id"]: w for w in plan["walls"]}
    results = {}
    for tid in ("step_free_route", "door_widths", "turning_space", "bathroom_clearance"):
        ex = example(tools[tid], pref, who)
        assert ex["state"] == "ran", (tid, ex)
        results[tid] = ex["result"]
    door = {c["id"]: c for c in results["door_widths"]["checks"]}
    openings = []
    for o in plan["openings"]:
        w = walls[o["wall"]]
        ux, uy = (w["b"][0] - w["a"][0]) / w["length"], (w["b"][1] - w["a"][1]) / w["length"]
        h = o["width"] / 2
        chk = door.get(o["id"])
        openings.append({"id": o["id"], "type": o["type"], "a": px((o["center"][0] - ux * h, o["center"][1] - uy * h)),
                         "b": px((o["center"][0] + ux * h, o["center"][1] + uy * h)), "c": px(o["center"]), "width": o["width"],
                         "status": chk["status"] if chk else None, "rule": chk["rule"] if chk else None})
    routes = [{"label": o["label"], "points": [px(p) for p in o["points"]],
               "chokes": [{"at": px(k["point"]), "width": k["width"], "status": k["status"]} for k in o["chokes"]]}
              for o in results["step_free_route"]["overlays"] if o["kind"] == "route"]
    size = [max(px(w[k])[0] for w in plan["walls"] for k in ("a", "b")), max(px(w[k])[1] for w in plan["walls"] for k in ("a", "b"))]
    return {"sid": sid, "name": plan["name"], "size": size, "persona": who["title"], "area": round(sum(r["area"] for r in plan["rooms"]), 1),
            "walls": [{"a": px(w["a"]), "b": px(w["b"])} for w in plan["walls"]],
            "rooms": [{"label": r["label"], "c": px(r["center"]), "area": r["area"]} for r in plan["rooms"]],
            "openings": openings, "routes": routes,
            "results": {tid: {"title": tools[tid].manifest.title, "verdict": r["verdict"], "metrics": r["metrics"][:5],
                              "checks": [{k: c[k] for k in ("id", "rule", "measured", "threshold", "unit", "status")} for c in r["checks"]],
                              "source": (r["metrics"] or r["findings"])[0]["source"] if (r["metrics"] or r["findings"]) else None}
                        for tid, r in results.items()},
            "notes": plan["quality"]["notes"]}


MEDIA = {  # source under <shots>/ -> public/media/<slot id>.webp (src/site/slots.ts). Checked by eye: test home and test cafe only.
    "ios/02-scan-plan.png": "iphone-app-1", "ios/03-scan-tools.png": "iphone-app-2", "ios/04-scan-tools-more.png": "iphone-app-3",
    "field/sim/01-home.png": "field-visit-1", "field/sim/04-visit-on-site.png": "field-visit-2"}


def media(shots: pathlib.Path) -> None:
    """`--media <shots folder>`: copy the safe iPhone screenshots in, 660 px wide. Astro has no image step here."""
    import subprocess
    for src, name in MEDIA.items():
        subprocess.run(["cwebp", "-quiet", "-q", "84", "-resize", "660", "0", str(shots / src), "-o", str(SITE / "public/media" / f"{name}.webp")], check=True)


def about_md() -> str:
    """The sections moved off the Devpost page (docs/devpost/about.md), word for word, from its first `## ` on:
    the lines above that are a note to the team."""
    text = (REPO / "docs/devpost/about.md").read_text()
    return text[text.index("\n## ") + 1:]


def asked() -> str:
    """The story's forward-deployed opening, with its own counts, for the home page."""
    m = re.search(r"^Cranley was built forward-deployed\..*?(?=\n\n)", (REPO / "docs/story.md").read_text(), re.S | re.M)
    assert m, "docs/story.md has lost its forward-deployed opening"
    return re.sub(r"\s+", " ", m.group(0).replace(" (Peri section)", ""))


def main() -> None:
    if "--media" in sys.argv:
        media(pathlib.Path(sys.argv[sys.argv.index("--media") + 1]))
    tools = dict(sorted(load().items()))
    people = personas()
    pref = prefs(people)
    from threshold.agent.investigator import APPROVE

    for d in (DOCS / "tools", DOCS / "reference/api", TRACKS):
        shutil.rmtree(d, ignore_errors=True)
    examples, states = {}, collections.Counter()
    for tid, t in tools.items():
        ex = examples[tid] = example(t, pref)
        states[ex["state"] if ex["state"] != "ran" else ex["result"]["verdict"]["status"]] += 1
        write(DOCS / "tools" / f"{tid.replace('_', '-')}.md", tool_md(t, ex, people, APPROVE))

    rows = [[f"[{esc(t.manifest.title)}](/docs/tools/{tid.replace('_', '-')}/)", esc(t.manifest.summary),
             ", ".join(dict.fromkeys(LAYER.get(r.layer, r.layer) for r in t.manifest.requires if r.need == "required")) or "inputs only",
             t.manifest.annotations.cost + ("" if t.manifest.annotations.read_only else ", writes")] for tid, t in tools.items()]
    write(DOCS / "tools/index.md", page("Tool reference", f"All {len(tools)} tools, generated from their manifests.",
          f"Cranley has {len(tools)} tools. Each is a manifest plus a handler, and each page below is generated from the manifest and from a "
          "real run of the tool on a made-up test scan. A tool added to `server/threshold/tools/` appears here, in the web app, over MCP "
          "and in the CLI without further work.\n\n" + table(["Tool", "What it answers", "Needs", "Speed"], rows), sidebar={"label": "All tools", "order": 0}))
    write(DOCS / "reference/personas.md", personas_md(people, tools))
    write(DOCS / "reference/layers.md", layers_md())
    write(DOCS / "reference/result-format.md", result_md())
    write(DOCS / "mcp.md", mcp_md(tools))
    write(SITE / "src/generated/about.md", about_md())
    write(DOCS / "sponsor-integrations.md", sponsor_md())
    api, n_ops = api_md()
    for mod, text in api.items():
        write(DOCS / "reference/api" / f"{mod.replace('_', '-')}.md", text)
    write(DOCS / "reference/api/index.md", page("HTTP API", f"The {n_ops} operations of the FastAPI server, by router.",
          f"The server (`server/threshold/api/app.py`) includes one router per file. These pages are generated from its OpenAPI schema: "
          f"{n_ops} operations in {len(api)} groups. With the server running, the same schema is at `/openapi.json` and an interactive copy at `/docs`.\n\n"
          "The API has no login and serves the data in your data folder, so keep it on your own machine or network. Signed scan links never reach the browser: the server fetches, caches and serves.\n\n"
          + table(["Group", "File", "Operations"], [[f"[{API_TITLES.get(m, m)}](/docs/reference/api/{m.replace('_', '-')}/)", f"`api/{m}.py`", text.count("\n## `")] for m, text in api.items()]),
          sidebar={"label": "Overview", "order": 0}))
    tracks = tracks_md()
    for slug, text in tracks.items():
        write(TRACKS / f"{slug}.md", text)

    by_group = {g: ids.split() for g, ids in GROUPS.items()}
    known = {i for ids in by_group.values() for i in ids}
    by_group["More"] = [p["id"] for p in people if p["id"] not in known]
    index = {p["id"]: p for p in people}
    site = {
        "counts": {"tools": len(tools), "personas": len(people), "layers": len(catalog.LAYERS), "operations": n_ops, "examples": dict(states),
                   "read_only": sum(1 for t in tools.values() if t.manifest.annotations.read_only)},
        "tools": [{"id": tid, "slug": tid.replace("_", "-"), "title": t.manifest.title, "summary": t.manifest.summary} for tid, t in tools.items()],
        "groups": [{"title": g, "personas": [{"id": i, "title": index[i]["title"], "who": index[i]["who"],
                                              "tools": [{"slug": t.replace("_", "-"), "title": tools[t].manifest.title} for t in index[i]["tools"] if t in tools]}
                                             for i in ids if i in index]} for g, ids in by_group.items() if any(i in index for i in ids)],
        "tracks": sorted(tracks),
        "asked": asked(),
        "asked_counts": dict(zip(("minutes", "people", "communities", "emails"), map(int, re.search(
            r"(\d+)-minute phone interview.*?from (\d+) people in (\d+) online communities,? and (\d+) emails", asked()).groups()))),
        "home": drawing(HOME, tools, pref),
    }
    write(SITE / "src/generated/site.json", json.dumps(site, indent=1))

    # self-check: the numbers the pages print, and nothing that looks like a real scan
    assert len(tools) >= 70 and len(people) >= 40 and n_ops >= 80, (len(tools), len(people), n_ops)
    text = "".join(p.read_text() for p in list(SITE.glob("src/content/**/*.md")) + [SITE / "src/generated/site.json"])
    ids = set(re.findall(r"\bu_[0-9a-z]{6,}\b", text))
    assert ids <= {HOME, CAFE}, ids
    assert not re.search(r"(?<![\w.-])/(?:home|Users)/\w", text), "a home path reached the docs"
    print(f"{len(tools)} tools ({dict(states)}), {len(people)} personas, {len(catalog.LAYERS)} layers, {n_ops} API operations in {len(api)} groups, tracks: {sorted(tracks)}")


if __name__ == "__main__":
    main()
