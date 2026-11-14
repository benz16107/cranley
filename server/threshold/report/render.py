"""The report as print HTML (US Letter): the plan with numbered findings, what to fix first, the evidence by tool, the
occupant load, the phone's measurements, the smoke alarm photos, and what was not checked. Self-contained (images
inline) so it prints the same anywhere."""
from __future__ import annotations

import base64
import datetime as dt
import html
import math
from collections.abc import Callable

from . import ORDER, STATUS_WORD, anchor_point, area, ft_in, value

LAYER = {"matterport": "Scan", "vexcel": "Aerial photo", "costar": "CoStar record", "drone": "Drone photo",
         "model": "Calculated", "phone": "On site"}
METHOD = {"geometry": "measured", "vision": "read from a photo", "lookup": "looked up", "simulation": "simulated",
          "sensor": "phone sensor", "manual": "measured by hand"}
CONF = {"high": "High", "medium": "Medium", "low": "Low"}

CSS = """
@page{size:letter;margin:.5in .55in .55in}
:root{--ink:#1f1d1a;--mute:#625d55;--faint:#8d877c;--line:#dcd6cb;--paper:#fff;--wash:#f6f3ed;
--fail:#b42318;--fail-bg:#fdecea;--warn:#9a5b00;--warn-bg:#fdf3e1;--pass:#2d6a3e;--pass-bg:#e9f3ec;--unk:#5b5f66;--unk-bg:#eef0f2;
--route:#2f5d8a}
*{box-sizing:border-box}
html,body{margin:0;background:var(--paper);color:var(--ink);font:9.4pt/1.42 "Nimbus Sans","Helvetica Neue",Helvetica,"Liberation Sans",Arial,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
h1,h2,h3{font-family:"Bitstream Charter",Charter,"C059",Georgia,serif;font-weight:700;margin:0;letter-spacing:-.005em}
h1{font-size:21pt;line-height:1.12}h2{font-size:13pt;margin:18px 0 6px;padding-top:2px}h3{font-size:10.6pt;margin:12px 0 4px}
p{margin:0 0 6px}.mute{color:var(--mute)}.small{font-size:8.2pt}.num{font-variant-numeric:tabular-nums}
.masthead{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end;border-bottom:2px solid var(--ink);padding-bottom:8px}
.kicker{font-size:8.4pt;text-transform:uppercase;letter-spacing:.08em;color:var(--mute);margin-bottom:3px}
.meta{text-align:right;font-size:8.6pt;color:var(--mute);line-height:1.5}
.tally{display:flex;gap:14px;margin:10px 0 2px;font-size:9.4pt}.tally b{font-size:13pt;margin-right:3px}
.lede{font-size:10.4pt;margin:6px 0 0}
.one{display:grid;grid-template-columns:1.05fr .95fr;gap:16px;margin-top:10px;align-items:start}
.pill{display:inline-block;font-size:7.6pt;font-weight:700;text-transform:uppercase;letter-spacing:.05em;padding:1px 6px;border-radius:3px}
.s-fail{color:var(--fail);background:var(--fail-bg)}.s-warn{color:var(--warn);background:var(--warn-bg)}
.s-pass{color:var(--pass);background:var(--pass-bg)}.s-unknown{color:var(--unk);background:var(--unk-bg)}
ol.fix{list-style:none;margin:0;padding:0}ol.fix li{display:grid;grid-template-columns:22px 1fr;gap:8px;padding:7px 0;
border-bottom:1px solid var(--line);break-inside:avoid}
.n{width:20px;height:20px;border-radius:50%;color:#fff;font-weight:700;font-size:9pt;display:flex;align-items:center;justify-content:center}
.n.fail{background:var(--fail)}.n.warn{background:var(--warn)}
.fix .t{font-weight:700}.fix .d{margin:1px 0 2px}.fix .do{font-size:8.8pt}.fix .do b{font-weight:700}
.src{font-size:7.8pt;color:var(--mute)}.dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin:0 3px 1px 0;vertical-align:middle}
.c-high{background:var(--pass)}.c-medium{background:#c48a1c}.c-low{background:var(--fail)}
figure{margin:0;border:1px solid var(--line);background:#fff;break-inside:avoid}figure svg{display:block;width:100%;height:auto}
figcaption{font-size:7.8pt;color:var(--mute);padding:5px 7px;border-top:1px solid var(--line);line-height:1.35}
table{width:100%;border-collapse:collapse;font-size:8.6pt;margin:2px 0 4px}
th{text-align:left;font-weight:700;color:var(--mute);font-size:7.8pt;text-transform:uppercase;letter-spacing:.04em;
border-bottom:1.5px solid var(--ink);padding:3px 5px}
td{border-bottom:1px solid var(--line);padding:3px 5px;vertical-align:top}tr{break-inside:avoid}
td.r,th.r{text-align:right;white-space:nowrap}td.std{color:var(--mute);font-size:7.8pt;width:30%}
.tool{break-inside:avoid-page;margin-top:6px}.tool .v{margin:2px 0 4px}
.box{background:var(--wash);border-radius:4px;padding:8px 10px;margin:6px 0;break-inside:avoid}
.box.bad{background:var(--fail-bg)}
ul.plain{margin:2px 0 0;padding-left:16px}ul.plain li{margin:1px 0}
.alarms{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.alarms figure img{display:block;width:100%;height:96px;object-fit:cover}
.pagebreak{break-before:page}
footer{margin-top:16px;padding-top:6px;border-top:1px solid var(--line);font-size:7.6pt;color:var(--faint)}
@media screen{body{background:#e9e6df}.sheet{max-width:8.5in;margin:24px auto;background:#fff;padding:.5in .55in;
box-shadow:0 1px 3px rgba(0,0,0,.12)}}
"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _src(source: dict | None, sid: str | None) -> str:
    if not source:
        return ""
    layer = source.get("layer")
    word = ("iPhone LiDAR scan" if (sid or "").startswith("u_") else "Matterport scan") if layer == "matterport" else LAYER.get(layer, layer)
    c = source.get("confidence") or "low"
    return (f'<span class="src"><span class="dot c-{_e(c)}"></span>{_e(word)}, {_e(METHOD.get(source.get("method"), source.get("method")))}'
            f' · {_e(CONF.get(c, c))} reliability</span>')


def _pill(status: str, word: str | None = None) -> str:
    return f'<span class="pill s-{_e(status)}">{_e(word or STATUS_WORD.get(status, status))}</span>'


# ---- the plan drawing ----

def _frame(plan: dict) -> tuple[float, str]:
    """Rotation (degrees) that draws the plan upright, and what the caption says about north."""
    g = plan.get("geo") or {}
    if g.get("yaw_deg") is not None:
        return float(g["yaw_deg"]), "North is up (from the phone's compass)."
    # no compass: turn the longest walls square to the page
    hist: dict[int, float] = {}
    for w in plan["walls"]:
        ang = math.degrees(math.atan2(w["b"][1] - w["a"][1], w["b"][0] - w["a"][0])) % 90
        hist[round(ang) % 90] = hist.get(round(ang) % 90, 0) + w["length"]
    best = max(hist, key=hist.get) if hist else 0
    return -float(best), "Not drawn to north: the scan has no compass reading."


def plan_svg(plan: dict, floor: str, marks: list[tuple[int, str, list[float]]], routes: list[list[list[float]]],
             portrait: bool = True) -> str:
    """One floor: rooms with name and area, walls with door and window gaps and door widths, the routes out, and
    numbered markers for findings. `marks` are (number, status, [x, y])."""
    rot, _ = _frame(plan)
    c0, s0 = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    walls = [w for w in plan["walls"] if w["floor"] == floor]
    pts = [p for w in walls for p in (w["a"], w["b"])]
    if not pts:
        return ""
    R = lambda p: (p[0] * c0 - p[1] * s0, p[0] * s0 + p[1] * c0)
    rp = [R(p) for p in pts]
    w_m = max(x for x, _ in rp) - min(x for x, _ in rp)
    h_m = max(y for _, y in rp) - min(y for _, y in rp)
    if (w_m > h_m) == portrait:  # a quarter turn so the long side runs the way the slot does
        rot += 90
        c0, s0 = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        rp = [R(p) for p in pts]
    x0, x1 = min(x for x, _ in rp), max(x for x, _ in rp)
    y0, y1 = min(y for _, y in rp), max(y for _, y in rp)
    S, pad = min(max(380 / max(x1 - x0, 1), 12.0), 60.0), 46.0  # px per metre: about 380 px across, so the text prints near 9 pt
    W, H = (x1 - x0) * S + 2 * pad, (y1 - y0) * S + 2 * pad + 18

    def P(p):
        x, y = R(p)
        return (x - x0) * S + pad, (y1 - y) * S + pad

    out = []
    for r in plan["rooms"]:
        if r["floor"] != floor or len(r.get("polygon") or []) < 3 or r.get("label") == "Void":
            continue
        d = " ".join(f"{a:.1f},{b:.1f}" for a, b in map(P, r["polygon"]))
        out.append(f'<polygon points="{d}" fill="#f6f3ed" stroke="none"/>')
    for o in plan.get("objects") or []:
        if o["floor"] != floor:
            continue
        cx, cy = o["center"][:2]
        a = math.radians(o.get("yaw_deg") or 0)
        hw, hd = o["size"][0] / 2, o["size"][1] / 2
        ux, uy, vx, vy = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
        corners = [(cx + sx * hw * ux + sy * hd * vx, cy + sx * hw * uy + sy * hd * vy) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        d = " ".join(f"{a_:.1f},{b_:.1f}" for a_, b_ in map(P, corners))
        out.append(f'<polygon points="{d}" fill="none" stroke="#b9b2a5" stroke-width="1.2"/>')
    for w in walls:
        (ax, ay), (bx, by) = P(w["a"]), P(w["b"])
        out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#1f1d1a" stroke-width="5" '
                   'stroke-linecap="square"/>')
    wall_by = {w["id"]: w for w in walls}
    for o in plan["openings"]:
        w = wall_by.get(o.get("wall") or "")
        if o["floor"] != floor or w is None or not o.get("width"):
            continue
        dx, dy = w["b"][0] - w["a"][0], w["b"][1] - w["a"][1]
        n = math.hypot(dx, dy) or 1
        ux, uy = dx / n * o["width"] / 2, dy / n * o["width"] / 2
        (ax, ay), (bx, by) = P((o["center"][0] - ux, o["center"][1] - uy)), P((o["center"][0] + ux, o["center"][1] + uy))
        if o["type"] == "window":
            out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#fff" stroke-width="3.4"/>'
                       f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#4d7fa8" stroke-width="1.4"/>')
            continue
        out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#fff" stroke-width="7"/>')
        for x, y in ((ax, ay), (bx, by)):
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#1f1d1a"/>')
        mx, my = (ax + bx) / 2, (ay + by) / 2
        # door width beside the gap, pushed off the wall toward the drawing's outside edge
        nx, ny = -(by - ay), (bx - ax)
        nn = math.hypot(nx, ny) or 1
        cxm, cym = W / 2, H / 2
        sgn = 1 if (mx + nx / nn - cxm) ** 2 + (my + ny / nn - cym) ** 2 > (mx - cxm) ** 2 + (my - cym) ** 2 else -1
        tx, ty = mx + sgn * nx / nn * 13, my + sgn * ny / nn * 13 + 3.5
        exit_ = o.get("exterior") or len(o.get("rooms") or []) == 1
        label = f'{o["width"] / 0.0254:.0f} in' + (" EXIT" if exit_ else "")
        out.append(f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="10.5" text-anchor="middle" fill="{"#b42318" if exit_ else "#625d55"}" '
                   f'font-weight="{700 if exit_ else 400}" paint-order="stroke" stroke="#fff" stroke-width="3">{_e(label)}</text>')
    for pts_ in routes:
        d = " ".join(f"{a:.1f},{b:.1f}" for a, b in (P(p) for p in pts_))
        out.append(f'<polyline points="{d}" fill="none" stroke="#2f5d8a" stroke-width="2" stroke-dasharray="6 4" opacity=".7"/>')
    for r in plan["rooms"]:
        if r["floor"] != floor or not r.get("center") or r.get("label") == "Void":
            continue
        x, y = P(r["center"])
        out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="13" font-weight="700" text-anchor="middle" fill="#1f1d1a" '
                   f'paint-order="stroke" stroke="#f6f3ed" stroke-width="4">{_e(r.get("label") or "Room")}</text>')
        if r.get("area"):
            out.append(f'<text x="{x:.1f}" y="{y + 14:.1f}" font-size="10.5" text-anchor="middle" fill="#625d55" '
                       f'paint-order="stroke" stroke="#f6f3ed" stroke-width="4">{r["area"]:.1f} m² · {r["area"] / 0.09290304:,.0f} ft²</text>')
    labels = [P(r["center"]) for r in plan["rooms"] if r["floor"] == floor and r.get("center") and r.get("label") != "Void"]
    placed: list[tuple[float, float]] = []
    for n, status, p in marks:
        x, y = P(p)
        if any(abs(x - lx) < 40 and abs(y - ly) < 22 for lx, ly in labels):  # a room's own finding: above its name, not on it
            y -= 30
        while any(math.dist((x, y), q) < 22 for q in placed):  # two findings at one door: set the second beside it
            x += 22
        placed.append((x, y))
        col = "#b42318" if status == "fail" else "#9a5b00"
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{col}" stroke="#fff" stroke-width="2.5"/>'
                   f'<text x="{x:.1f}" y="{y + 4.3:.1f}" font-size="12" font-weight="700" fill="#fff" text-anchor="middle">{n}</text>')
    bar = 2 * S  # 2 m scale bar
    out.append(f'<g transform="translate({pad:.0f},{H - 16:.0f})"><rect width="{bar:.0f}" height="5" fill="#1f1d1a"/>'
               f'<text x="{bar + 6:.0f}" y="6" font-size="10" fill="#625d55">2 m (6 ft 7 in)</text></g>')
    g = plan.get("geo") or {}
    if g.get("yaw_deg") is not None:  # north arrow: north is +y in ENU, which the rotation put straight up
        a = math.radians(rot - float(g["yaw_deg"]))
        nx, ny = -math.sin(a), -math.cos(a)
        cx, cy = W - 26, 30
        out.append(f'<g><line x1="{cx:.0f}" y1="{cy:.0f}" x2="{cx + nx * 16:.1f}" y2="{cy + ny * 16:.1f}" stroke="#1f1d1a" stroke-width="2"/>'
                   f'<text x="{cx + nx * 24:.1f}" y="{cy + ny * 24 + 4:.1f}" font-size="11" font-weight="700" text-anchor="middle">N</text></g>')
    return (f'<svg viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="Floor plan with numbered findings">'
            + "".join(out) + "</svg>")


def _routes(report: dict, sid: str, floor: str) -> list[list[list[float]]]:
    out = []
    for sec in report["sections"]:
        if sec["tool"] != "egress_routes" or sec["sid"] != sid:
            continue
        for ov in sec["overlays"]:
            if ov.get("kind") == "route" and ov.get("floor") in (floor, None):
                out.append([p[:2] for p in ov["points"]])
    return out


# ---- the page ----

def html_doc(report: dict, photo: Callable[[str], bytes] | None = None) -> str:
    plans = {s: p for s, p in report["plans"].items() if p}
    fix = report["fix_first"]
    n_fail = sum(f["status"] == "fail" for f in fix)
    n_warn = sum(f["status"] == "warn" for f in fix)
    passed = report["counts"].get("pass", 0)
    unknown = len(report["not_checked"])

    figs = []
    for sid, plan in plans.items():
        for f in sorted(plan["floors"], key=lambda f: f.get("sequence") or 0):
            marks = []
            for n, it in enumerate(fix, 1):
                ap = anchor_point(plan, it.get("anchor"))
                if ap and ap[0] == f["id"]:
                    marks.append((n, it["status"], ap[1]))
            svg = plan_svg(plan, f["id"], marks, [])  # the routes' straight door-to-door legs read as crossing walls
            if svg:
                label = f"{plan.get('name') or sid}" + (f", {f.get('label')}" if len(plan["floors"]) > 1 else "")
                figs.append(f'<figure>{svg}<figcaption><b>{_e(label)}.</b> Drawn from the iPhone LiDAR scan. Numbers match '
                            f'"What to fix first". Door widths are the opening in the wall; red marks a way out. {_e(_frame(plan)[1])}</figcaption></figure>')

    fix_html = []
    for n, it in enumerate(fix, 1):
        also = "".join(f'<div class="src">Also found by {_e(_tool_title(report, a["tool"]))}: {_e(a["title"])}.</div>' for a in it["also"])
        chk = it.get("check")
        need = ""
        if chk and chk.get("measured") is not None and chk.get("threshold") is not None:
            need = (f'<div class="small num">Measured {_e(value(chk["measured"], chk["unit"]))}; needs '
                    f'{_e(value(chk["threshold"], chk["unit"]))}{" · " + _e(chk["standard"]) if chk.get("standard") else ""}</div>')
        fix_html.append(f'<li><span class="n {it["status"]}">{n}</span><div><div class="t">{_e(it["title"])} '
                        f'{_pill(it["status"])}</div><div class="d">{_e(it["detail"])}</div>{need}'
                        f'<div class="do"><b>What to do:</b> {_e(it["fix"])}</div>{_src(it.get("source"), it.get("sid"))}{also}</div></li>')
    if not fix_html:
        fix_html.append('<li><span></span><div>Nothing failed or came close on what the scan could measure. See "What we did '
                        'not check" before relying on that.</div></li>')

    head = f"""
<header class="masthead"><div><div class="kicker">{_e(report['title'])}</div>
<h1>{_e(report['business'] or report['place'] or 'Site report')}</h1>
<div class="mute">{_e(' · '.join(x for x in [report['place'] if report['business'] else '', report['address']] if x))}</div></div>
<div class="meta">Visit on {_e(_long_date(report['date']))}<br>Prepared with Threshold<br>{'Scan ' + _e(', '.join(report['sids'])) if report['sids'] else ''}</div></header>
<div class="tally num"><span><b style="color:var(--fail)">{n_fail}</b>to fix</span><span><b style="color:var(--warn)">{n_warn}</b>to check</span>
<span><b style="color:var(--pass)">{passed}</b>checks passed</span><span><b style="color:var(--unk)">{unknown}</b>things we could not check</span></div>
<p class="lede">{_e(report['lede'])}</p>"""

    glance = []
    for sid, o in report["occupancy"].items():
        glance.append(("Occupant load", f"{o['total']} people", "Calculated from room areas, IBC Table 1004.5"))
        glance.append(("Ways out", f"{o['exits']} (needs {o['exits_needed']})", "Doorways to outside in the scan"))
    for sec in report["sections"]:
        if sec["verdict"]["status"] == "unknown" and sec["tool"] != "fire_preplan":
            continue  # a tool that could not answer here: its zeros say nothing
        for m in [m for m in sec["metrics"] if m.get("value") is not None][:3]:
            glance.append((m["label"], value(m["value"], m["unit"]), sec["title"]))
    rows_g = "".join(f'<tr><td>{_e(a)}</td><td class="r num"><b>{_e(b)}</b></td><td class="std">{_e(c)}</td></tr>' for a, b, c in glance[:12])
    glance_html = f'<h2>At a glance</h2><table><tbody>{rows_g}</tbody></table>' if rows_g else ""
    page1 = (f'{head}<div class="one"><section><h2 style="margin-top:4px">What to fix first</h2><ol class="fix">{"".join(fix_html)}</ol>'
             f'{glance_html}</section><section>{"".join(figs[:1]) or "<p class=mute>No plan drawing: no scan in this report has walls.</p>"}</section></div>'
             + "".join(f'<div style="margin-top:10px">{f}</div>' for f in figs[1:]))

    body = [page1]
    occ = report["occupancy"]
    if occ:
        rows = []
        for sid, o in occ.items():
            for r in o["rows"]:
                rows.append(f'<tr><td>{_e(r["room"])}</td><td class="r num">{_e(area(r["area"]))}</td><td>{_e(r["use"])}</td>'
                            f'<td class="num">{_e(r["factor"] or "–")}</td><td class="r num">{"–" if r["load"] is None else r["load"]}</td></tr>')
            widths = ", ".join(ft_in(w) for w in o["exit_widths"]) or "none found"
            body.append(f"""<section class="pagebreak"><h2>How many people the space holds</h2>
<p>The occupant load is what the building code expects a space of this size and use to hold. It sets how many ways out it
needs and how wide they must be. Areas are measured inside the walls; the code uses <i>net</i> area for seating (less the
counter and fixed equipment), so the real seating limit is a little lower than the figure here.</p>
<table><thead><tr><th>Room</th><th class="r">Area</th><th>Use</th><th>Floor area per person</th><th class="r">People</th></tr></thead>
<tbody>{''.join(rows)}</tbody><tfoot><tr><td colspan="4"><b>Occupant load</b></td><td class="r num"><b>{o['total']}</b></td></tr></tfoot></table>
<div class="box{' bad' if o['status'] == 'fail' else ''}"><b>{o['exits']} way{'s' if o['exits'] != 1 else ''} out found</b> ({_e(widths)}).
{o['total']} people need {o['exits_needed']} {'(over 49 in an assembly space)' if o['exits_needed'] > 1 else '(49 or fewer may use one)'}.
The doors out give about {o['door_capacity']} people of exit width at 0.2 in per person. {_pill(o['status'], 'Enough exits' if o['status'] == 'pass' else 'Too few exits')}
<div class="src">Calculated from the scan's room areas · {_e(o['standard'])}. The fire official sets the posted number.</div></div>
</section>""")

    sec_html = []
    for sec in report["sections"]:
        if sec["tool"] == "fire_preplan":
            lines = [f for f in report["items"] if f["tool"] == "fire_preplan" and f["sid"] == sec["sid"] and not f["id"].endswith(":sheet")]
            rows = "".join(f'<tr><td>{_e(f["title"])}</td><td>{_e(f["detail"])}</td><td>{_pill(f["status"], "Confirm" if f["status"] == "unknown" else None)}</td>'
                           f'<td>{_src(f.get("source"), f.get("sid"))}</td></tr>' for f in lines)
            sec_html.append(f'<div class="tool"><h3>{_e(sec["title"])}</h3><p class="v">{_e(sec["verdict"]["text"])} Sections follow '
                            f'NFPA 1620; "Confirm" lines are for the walk-round.</p><table><thead><tr><th>Item</th><th>What the data says</th>'
                            f'<th>Result</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table></div>')
            continue
        if not sec["checks"]:
            continue
        rows = []
        for c in sorted(sec["checks"], key=lambda c: ORDER.get(c["status"], 9)):
            n = next((report["numbered"][f] for f in c.get("findings") or [] if f in report["numbered"]), None)
            claim = c.get("kind") == "claim"
            rows.append(f'<tr><td>{f"<b>{n}.</b> " if n else ""}{_e(c["rule"])}</td><td class="r num">{_e(value(c["measured"], c["unit"]))}</td>'
                        f'<td class="r num">{"" if claim or c["threshold"] is None else "needs "}{_e(value(c["threshold"], c["unit"]))}</td><td>{_pill(c["status"])}</td>'
                        f'<td class="std">{_e(c.get("standard") or "")}</td></tr>')
        src = next((f.get("source") for f in report["items"] if f["tool"] == sec["tool"]), None)
        sec_html.append(f'<div class="tool"><h3>{_e(sec["title"])}</h3><p class="v">{_pill(sec["verdict"]["status"])} {_e(sec["verdict"]["text"])}</p>'
                        f'<table><thead><tr><th>What was checked</th><th class="r">Measured</th><th class="r">Limit</th><th>Result</th>'
                        f'<th>Standard</th></tr></thead><tbody>{"".join(rows)}</tbody></table>{_src(src, sec["sid"])}</div>')
    if sec_html:
        body.append(f'<section class="{"" if occ else "pagebreak"}"><h2>The evidence, check by check</h2>'
                    f'<p class="mute small">Each line is one measurement against one limit. Reliability says how far to trust '
                    f'the measurement: <span class="dot c-high"></span>high, <span class="dot c-medium"></span>medium (confirm '
                    f'if the result is close), <span class="dot c-low"></span>low (a lead, not a finding).</p>{"".join(sec_html)}</section>')

    if report["alarms"]:
        cards = []
        for a in report["alarms"]:
            img = ""
            if a["capture"] and photo:
                try:
                    img = f'<img alt="Ceiling, {_e(a["room_name"])}" src="data:image/jpeg;base64,{base64.b64encode(photo(a["capture"])).decode()}">'
                except Exception:  # noqa: BLE001 - a missing photo file leaves the line without its picture
                    img = ""
            word = {"pass": "Alarm seen", "warn": "None seen", "unknown": "Not known"}[a["status"]]
            cards.append(f'<figure>{img}<figcaption><b>{_e(a["room_name"])}</b> {_pill(a["status"], word)}<br>{_e(a["what"])}'
                         f'</figcaption></figure>')
        body.append(f'<section style="break-inside:avoid"><h2>Smoke alarms, from ceiling photos</h2><p class="small mute">One photo per room, read by a vision '
                    f'model. "None seen" means the photo shows no alarm, not that there is none: check the room.</p>'
                    f'<div class="alarms">{"".join(cards)}</div></section>')

    if report["measured"] or report["phone_notes"]:
        rows = []
        for m in report["measured"]:
            err = f" ± {m['err_m'] * 100:.1f} cm" if m.get("err_m") else ""
            rows.append(f'<tr><td>{_e(m["what"])}</td><td>{_e(m["where"])}</td><td class="r num">{_e(value(m["value"], m["unit"]))}{_e(err)}</td>'
                        f'<td>{_e(m["method"] or "")}</td>'
                        f'<td>{_e(m["result"] or "")}</td></tr>')
        for f in report["phone_notes"]:
            rows.append(f'<tr><td>{_e(f["title"])}</td><td></td><td></td><td>{_e("photo" if f.get("media") else "note")}</td>'
                        f'<td>{_e(f["detail"])}</td></tr>')
        body.append(f'<section><h2>Measured on site with the phone</h2><table><thead><tr><th>What</th><th>Where</th>'
                    f'<th class="r">Value</th><th>How</th><th>What it changed</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>')

    nc = "".join(f"<li>{_e(x)}</li>" for x in report["not_checked"])
    body.append(f'<section><h2>What we did not check</h2><p class="small">A scan measures the shape of the space: walls, doors, '
                f'windows and large furniture. It cannot see behind walls, test equipment, or read signs and labels. These were '
                f'outside this visit or the data could not answer them:</p><ul class="plain small">{nc}</ul></section>')
    body.append(f'<footer>This report is a measured survey to help plan work. It is not a code inspection, a permit review or a '
                f'fire inspection; the building and fire officials decide what applies. Measurements: Apple RoomPlan on an iPhone '
                f'with LiDAR, typically within a few centimetres; door widths are the opening in the wall, and a hung door clears '
                f'about 5 cm less. Investigation {_e(report["workspace"])}, made {_e(dt.datetime.now().strftime("%Y-%m-%d %H:%M"))}.</footer>')

    title = f"{report['title']}, {report['business'] or report['place']}"
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>{_e(title)}</title><style>{CSS}</style></head><body><main class="sheet">'
            + "".join(body) + "</main></body></html>")


def _tool_title(report: dict, tool: str) -> str:
    return next((s["title"] for s in report["sections"] if s["tool"] == tool), tool.replace("_", " "))


def _long_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}, {d.year}"
