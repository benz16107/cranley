"""The printable one-page pre-plan: aerial with sides A to D and the engine spot, a north-up plan drawing, and the facts
table with each line's source. Self-contained HTML (images inline) so it prints and opens offline."""
from __future__ import annotations

import base64
import datetime as dt
import html

from ...geometry import to_enu
from ...geometry._plan import polygons
from .common import BEDROOM, floor_label, name

SYM = {"smoke alarm": "S", "sprinkler head": "SP", "fire extinguisher": "FE", "electrical panel": "EP",
       "water heater": "WH", "gas stove": "G", "exit sign": "X", "stairs": "ST", "kitchen hood": "H"}
LAYER = {"matterport": "Scan", "vexcel": "Aerial", "costar": "CoStar", "drone": "Drone", "model": "Model"}
METHOD = {"geometry": "measured", "vision": "photo read", "lookup": "record", "simulation": "simulated"}
CSS = """
:root{--ink:#1d1b18;--mute:#6b665d;--line:#d8d2c6;--paper:#fbf9f4;--red:#b3261e;--amber:#a86200;--bed:#f3dcc6;
--room:#ece7dc;--blue:#235a8c}
*{box-sizing:border-box}html,body{margin:0;background:var(--paper);color:var(--ink);
font:8pt/1.28 "Helvetica Neue",Helvetica,Arial,sans-serif}
.page{width:8.5in;margin:0 auto;padding:.36in .4in}
header{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid var(--ink);
padding-bottom:6px;margin-bottom:8px}
h1{font-size:15pt;margin:0;letter-spacing:-.01em}h2{font-size:8.6pt;text-transform:uppercase;letter-spacing:.06em;
margin:8px 0 4px;color:var(--mute)}.sub{color:var(--mute)}.draft{color:var(--red);font-weight:700;text-align:right}
.top{display:grid;grid-template-columns:1fr 1fr;gap:10px}\n.row3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px}.row3 svg{max-height:1.7in}
figure{margin:0;border:1px solid var(--line);background:#fff;position:relative}
figure svg{display:block;width:100%;height:auto;max-height:2.55in}figcaption{font-size:7.4pt;color:var(--mute);padding:3px 5px;
border-top:1px solid var(--line)}
table{width:100%;border-collapse:collapse;font-size:7.3pt}th{text-align:left;color:var(--mute);font-weight:600;
border-bottom:1px solid var(--ink);padding:2px 4px}td{border-bottom:1px solid var(--line);padding:1px 4px;
vertical-align:top}td.sec{white-space:nowrap;color:var(--mute);width:5.5em}td.item{font-weight:600;width:12.5em;white-space:nowrap}
td.src{color:var(--mute);width:10.5em;font-size:7pt;white-space:nowrap}.warn td.val{color:var(--amber)}.unknown td.val{color:var(--mute);
font-style:italic}.dot{display:inline-block;width:.55em;height:.55em;border-radius:50%;margin-right:3px}
.c-high{background:#2f6f3e}.c-medium{background:#c48a1c}.c-low{background:#b3261e}
.legend{display:flex;flex-wrap:wrap;gap:8px;font-size:7.2pt;color:var(--mute);margin-top:3px}
footer{margin-top:8px;font-size:7pt;color:var(--mute)}
@media print{@page{size:letter;margin:0}.page{padding:.3in .38in;zoom:.92}}
"""


def _e(x) -> str:
    return html.escape(str(x))


def _aerial(acc: dict | None) -> str:
    if not acc:
        return "<figure><figcaption>No aerial photo for this location.</figcaption></figure>"
    o = acc["ortho"]
    img = base64.b64encode(o.image).decode()
    W, H = o.width, o.height
    parts = [f'<image href="data:image/jpeg;base64,{img}" width="{W}" height="{H}"/>']
    fp = acc["footprint"]
    if fp is not None:
        for g in getattr(fp, "geoms", [fp]):
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (o.to_px(*c) for c in g.exterior.coords))
            parts.append(f'<polygon points="{pts}" fill="none" stroke="#ffde59" stroke-width="5"/>')
        minx, miny, maxx, maxy = fp.bounds
        cx, cy = fp.centroid.x, fp.centroid.y
        pad = 4 / 111320.0
        spots = {"N": (cx, maxy + pad * 1.6), "S": (cx, miny - pad * 1.6),
                 "E": (maxx + pad * 1.9, cy), "W": (minx - pad * 1.9, cy)}
        for letter, comp in acc["sides"].items():
            x, y = o.to_px(*spots[comp])
            x, y = min(max(x, 40), W - 40), min(max(y, 40), H - 40)
            parts.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="34" fill="#1d1b18" stroke="#fff" stroke-width="4"/>'
                         f'<text x="{x:.0f}" y="{y + 15:.0f}" font-size="44" font-weight="700" fill="#fff" '
                         f'text-anchor="middle">{letter}</text>')
    for d in acc["driveways"]:
        x, y = o.to_px(*d)
        parts.append(f'<rect x="{x - 18:.0f}" y="{y - 18:.0f}" width="36" height="36" fill="none" stroke="#fff" '
                     f'stroke-width="5" stroke-dasharray="8 6"/>')
    for ob in acc["barriers"] + acc["overhead"]:
        x, y = o.to_px(*ob["lonlat"])
        parts.append(f'<path d="M{x - 20:.0f},{y + 18:.0f} L{x:.0f},{y - 22:.0f} L{x + 20:.0f},{y + 18:.0f} Z" '
                     f'fill="#a86200" stroke="#fff" stroke-width="4"/>')
    x, y = o.to_px(*acc["engine"]["lonlat"])
    parts.append(f'<rect x="{x - 46:.0f}" y="{y - 24:.0f}" width="92" height="48" rx="4" fill="#b3261e" stroke="#fff" '
                 f'stroke-width="4"/><text x="{x:.0f}" y="{y + 12:.0f}" font-size="32" font-weight="700" fill="#fff" '
                 f'text-anchor="middle">E1</text>')
    parts.append(f'<g transform="translate({W - 70},80)"><path d="M0,-50 L18,10 L0,0 L-18,10 Z" fill="#fff" '
                 f'stroke="#1d1b18" stroke-width="3"/><text y="45" font-size="34" font-weight="700" fill="#fff" '
                 f'stroke="#1d1b18" stroke-width="1" text-anchor="middle">N</text></g>')
    m = o.metres_per_px
    bar = 20 / m
    parts.append(f'<g transform="translate(30,{H - 40})"><rect width="{bar:.0f}" height="12" fill="#fff" '
                 f'stroke="#1d1b18" stroke-width="2"/><text y="-8" font-size="26" fill="#fff" stroke="#1d1b18" '
                 f'stroke-width=".8">20 m</text></g>')
    cap = (f"Vexcel orthophoto, captured {_e(str(o.meta.get('last-capture-date') or '')[:10])}. Yellow: building "
           "footprint. A to D: sides, A on the address street. E1: first engine. Dashed: driveways. Triangles: "
           f"gates, fences or overhead obstacles. Positions chosen by a vision model ({_e(acc['confidence'])} "
           "confidence).")
    return (f'<figure><svg viewBox="0 0 {W} {H}" role="img" aria-label="Aerial photo with sides and engine position">'
            + "".join(parts) + f"</svg><figcaption>{cap}</figcaption></figure>")


def _plan_svg(plan: dict, a: dict, seen: dict, small: bool = False) -> str:
    """North-up drawing of every floor of one scan, side by side."""
    polys = polygons(plan)
    geo = bool(plan.get("geo"))
    tf = (lambda x, y: to_enu(plan, x, y)) if geo else (lambda x, y: (x, y))
    floors = sorted(plan.get("floors") or [], key=lambda f: f.get("sequence") or 0)
    floor_ids = [f["id"] for f in floors if any(r["floor"] == f["id"] and polys.get(r["id"]) is not None
                                                for r in plan["rooms"])]
    if not floor_ids:
        return ""
    shapes = {}
    for f in floor_ids:
        rs = [(r, [tf(*c) for c in polys[r["id"]].exterior.coords]) for r in plan["rooms"]
              if r["floor"] == f and polys.get(r["id"]) is not None and r.get("label") != "Void"]
        shapes[f] = rs
    allpts = [p for rs in shapes.values() for _, pts in rs for p in pts]
    w = max(p[0] for p in allpts) - min(p[0] for p in allpts)
    h = max(p[1] for p in allpts) - min(p[1] for p in allpts)
    gap = 2.5
    out, xoff = [], 0.0
    S = 20.0  # px per metre in the viewBox
    for f in floor_ids:
        rs = shapes[f]
        xs = [p[0] for _, pts in rs for p in pts]
        ys = [p[1] for _, pts in rs for p in pts]
        x0, y1 = min(xs), max(ys)
        px = lambda e, n: ((e - x0 + xoff) * S, (y1 - n) * S + 30)  # noqa: E731
        g = [f'<text x="{xoff * S:.0f}" y="18" font-size="16" font-weight="700" fill="#1d1b18">'
             f'{_e(floor_label(plan, f).capitalize())}</text>']
        for r, pts in rs:
            fill = "var(--bed)" if r.get("label") == BEDROOM else "var(--room)"
            d = " ".join(f"{a_:.1f},{b_:.1f}" for a_, b_ in (px(*p) for p in pts))
            g.append(f'<polygon points="{d}" fill="{fill}" stroke="#1d1b18" stroke-width="1.6"/>')
            c = polys[r["id"]].representative_point()
            cx, cy = px(*tf(c.x, c.y))
            if not small and polys[r["id"]].area > 4:
                g.append(f'<text x="{cx:.0f}" y="{cy:.0f}" font-size="10" fill="#4a463f" text-anchor="middle">'
                         f'{_e(name(r))}</text>')
        for hh in a.get("hose") or []:
            for leg in hh["walk"]["legs"]:
                if not leg.get("stairs") and leg["floor"] == f:
                    d = " ".join(f"{a_:.1f},{b_:.1f}" for a_, b_ in (px(*tf(p[0], p[1])) for p in leg["points"]))
                    g.append(f'<polyline points="{d}" fill="none" stroke="var(--blue)" stroke-width="3" '
                             f'stroke-dasharray="7 4"/>')
        for e in a.get("exits") or []:
            if e["floor"] == f:
                ex, ey = px(*tf(*e["center"]))
                g.append(f'<path d="M{ex - 9:.0f},{ey + 8:.0f} L{ex:.0f},{ey - 9:.0f} L{ex + 9:.0f},{ey + 8:.0f} Z" '
                         f'fill="var(--red)" stroke="#fff" stroke-width="1.5"/>')
        for label, hits in seen.items():
            for p_, d in hits:
                pt = (d["finding"]["anchor"] or {}).get("point")
                if p_["sid"] != plan["sid"] or not pt or label not in SYM:
                    continue
                room = next((r for r in plan["rooms"] if r["id"] == d.get("in_room")), None)
                if room is None or room["floor"] != f:
                    continue
                ox, oy = px(*tf(pt[0], pt[1]))
                g.append(f'<circle cx="{ox:.0f}" cy="{oy:.0f}" r="8" fill="#fff" stroke="var(--ink)" stroke-width="1.4"/>'
                         f'<text x="{ox:.0f}" y="{oy + 3.5:.0f}" font-size="8" font-weight="700" text-anchor="middle">'
                         f'{SYM[label]}</text>')
        out.append("".join(g))
        xoff += (max(xs) - x0) + gap
    W = xoff * S
    H = h * S + 40
    north = ('<g transform="translate({:.0f},22)"><path d="M0,-12 L6,6 L0,2 L-6,6 Z" fill="#1d1b18"/>'
             '<text x="10" y="4" font-size="11">N</text></g>').format(W - 20) if geo else ""
    return f'<svg viewBox="-4 0 {W + 8:.0f} {H:.0f}" role="img" aria-label="Plan drawing">{"".join(out)}{north}</svg>'


def render(result, data: dict) -> str:
    acc = data["acc"]
    plans_html = []
    LEGEND = ("Drawn north up from the wall graph. Red triangles: doorways out (may lead to unscanned rooms). Blue "
              "dashes: hose stretch to the farthest point. Tan: bedrooms (search first). Circles: S smoke alarm, SP "
              "sprinkler, FE extinguisher, EP electrical panel, WH water heater, G gas, ST stairs.")
    walled = data["walled"]
    if data["multi"]:  # unit plans with bedrooms first; amenity rooms drawn as one polygon say little
        walled = sorted((pa for pa in walled if len(pa[0]["rooms"]) >= 4),
                        key=lambda pa: -sum(r.get("label") == BEDROOM for r in pa[0]["rooms"]))
    for i, (plan, a) in enumerate(walled[: (4 if data["multi"] else 1)]):
        svg = _plan_svg(plan, a, data["seen"], small=data["multi"])
        if svg:
            unit = _e((plan.get("name") or plan["sid"])[:40])
            cap = (f"{unit}. {LEGEND}" if i == 0 else unit) if data["multi"] else LEGEND
            plans_html.append(f"<figure>{svg}<figcaption>{cap}</figcaption></figure>")
    if not plans_html:
        plans_html.append("<figure><figcaption>No unit scan here has a wall graph, so no plan drawing. Use the floor plan "
                          "images from the scans.</figcaption></figure>")
    rows = []
    for x in sorted(data["lines"], key=lambda x: [int(p) if p.isdigit() else 0 for p in x["section"].split(".")]):
        s = x["source"]
        rows.append(f'<tr class="{x["status"]}"><td class="sec">§{_e(x["section"])}</td><td class="item">'
                    f'{_e(x["item"])}</td><td class="val">{_e(x["value"])}</td><td class="src"><span class="dot '
                    f'c-{s.confidence}"></span>{LAYER[s.layer]}, {METHOD[s.method]} · {_e(s.confidence)}</td></tr>')
    todo = sum(x["status"] == "unknown" for x in data["lines"])
    today = dt.date.today().isoformat()
    second = "".join(plans_html[1:]) if data["multi"] else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>Pre-plan {_e(data['title'])}</title><style>{CSS}</style></head>
<body><div class="page"><header><div><h1>{_e(data['title'])}</h1><div class="sub">{_e(data['kind'])}. Pre-incident
plan, sections from NFPA 1620 (2015), now part of NFPA 1660.</div></div><div class="draft">DRAFT FROM DATA<br>
<span class="sub">{todo} items to confirm on site · {today}</span></div></header>
<div class="top">{_aerial(acc)}{plans_html[0]}</div>{f'<div class="row3">{second}</div>' if second else ''}
<h2>Facts</h2><table><thead><tr><th>§</th><th>Item</th><th>What the data says</th><th>Source</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<div class="legend"><span><span class="dot c-high"></span>high confidence</span><span><span class="dot c-medium">
</span>medium</span><span><span class="dot c-low"></span>low: confirm</span><span>Amber: hazard or obstacle.
Italic: not in the data. "Not seen" in photos is not "absent". Measurements come from geometry; the vision model only
names and places things.</span></div></div></body></html>"""

