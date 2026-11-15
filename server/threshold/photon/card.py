"""The picture of an answer, rendered on the server: the floor plan with the result's numbered findings and routes
(the PDF report's own drawing), the verdict and up to three metrics, all from the ToolResult. Never a panorama or a
file from the data folder: only what we draw. Headless Chrome screenshots the HTML, as report/pdf.py prints it."""
from __future__ import annotations

import subprocess
import tempfile
from html import escape
from pathlib import Path

from ..report import anchor_point, value
from ..report.pdf import Unavailable, chrome
from ..report.render import plan_svg
from .words import STATUS_WORD, place_name, title

INK, PAPER, MUTED = "#1f1d1a", "#f6f3ed", "#625d55"
TONE = {"pass": "#2f6b3a", "warn": "#9a5b00", "fail": "#b42318", "unknown": "#625d55"}


def plan_figure(plan: dict, result: dict, portrait: bool = True) -> str:
    """The plan's busiest floor for this result, with numbered findings and any routes."""
    marks_by_floor: dict[str, list] = {}
    n = 0
    for f in result.get("findings") or []:
        if f.get("status") not in ("fail", "warn"):
            continue
        hit = anchor_point(plan, f.get("anchor"))
        if hit:
            n += 1
            marks_by_floor.setdefault(hit[0], []).append((n, f["status"], hit[1][:2]))
    routes: dict[str, list] = {}
    for ov in result.get("overlays") or []:
        if ov.get("kind") == "route" and ov.get("points"):
            routes.setdefault(ov.get("floor"), []).append([p[:2] for p in ov["points"]])
    floors = [f["id"] for f in plan.get("floors") or []] or sorted({w["floor"] for w in plan.get("walls") or []})
    if not floors:
        return ""
    floor = max(floors, key=lambda f: (len(marks_by_floor.get(f, [])), len(routes.get(f, [])), -floors.index(f)))
    return plan_svg(plan, floor, marks_by_floor.get(floor, []), routes.get(floor, []) + routes.get(None, []), portrait)


def card_html(run: dict, plan: dict | None) -> str:
    r = run.get("result") or {}
    v = r.get("verdict") or {"status": "unknown", "text": run.get("error") or ""}
    figure = plan_figure(plan, r) if plan and plan.get("walls") else ""
    metrics = "".join(f'<div class="m"><span>{escape(m["label"])}</span><b>{escape(value(m["value"], m["unit"]))}</b>'
                      f'<i>{escape(m["source"]["confidence"])}</i></div>' for m in (r.get("metrics") or [])[:3])
    fails = [f for f in r.get("findings") or [] if f.get("status") in ("fail", "warn")][:4]
    flist = "".join(f'<li><em style="background:{TONE[f["status"]]}">{i}</em>{escape(f["title"])}</li>'
                    for i, f in enumerate(fails, 1)) if fails else ""
    srcs = sorted({f'{m["source"]["layer"]} {m["source"]["method"]}' for m in r.get("metrics") or []})
    tone = TONE.get(v["status"], MUTED)
    return f"""<!doctype html><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}} body{{width:540px;height:760px;background:{PAPER};color:{INK};
font:15px/1.35 -apple-system,"Inter Tight","Helvetica Neue",Arial,sans-serif;padding:26px 26px 20px;display:flex;flex-direction:column;gap:14px}}
header{{display:flex;justify-content:space-between;align-items:baseline;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED}}}
header b{{color:{INK};letter-spacing:.14em}} h1{{font-size:19px;line-height:1.25;font-weight:650}}
.v{{display:flex;gap:10px;align-items:flex-start}} .pill{{flex:none;background:{tone};color:#fff;border-radius:4px;padding:3px 9px;
font-weight:700;font-size:13px}} .v p{{font-size:14.5px}}
figure{{flex:1;min-height:0;background:#fff;border:1px solid #e4dfd5;border-radius:6px;display:flex;align-items:center;justify-content:center;padding:8px}}
figure svg{{max-width:100%;max-height:100%}} .m{{display:grid;grid-template-columns:1fr auto auto;gap:10px;border-top:1px solid #e4dfd5;padding:6px 0;font-size:13.5px}}
.m b{{font-variant-numeric:tabular-nums}} .m i{{color:{MUTED};font-style:normal;font-size:12px}}
ul{{list-style:none;padding:0;display:grid;gap:4px;font-size:13px}} li{{display:flex;gap:8px;align-items:center}}
li em{{flex:none;width:18px;height:18px;border-radius:50%;color:#fff;font:700 11px/18px sans-serif;text-align:center;font-style:normal}}
footer{{font-size:11px;color:{MUTED}}}</style>
<header><b>Cranley</b><span>{escape(title(run["tool"]))}</span></header>
<h1>{escape(place_name(run.get("sid")))}</h1>
<div class="v"><span class="pill">{escape(STATUS_WORD.get(v["status"], v["status"]))}</span><p>{escape(v["text"])}</p></div>
{f"<figure>{figure}</figure>" if figure else ""}
<section>{metrics}</section>
{f"<ul>{flist}</ul>" if flist and not figure else ""}
<footer>Measured from {escape(", ".join(srcs) or "the tool's inputs")}. Every number comes from the calculation, not from a model.</footer>"""


def background_html(plan: dict, result: dict) -> str:
    """A chat background: the plan alone, faint, phone-shaped."""
    return f"""<!doctype html><meta charset="utf-8"><style>*{{margin:0}} body{{width:390px;height:844px;background:{PAPER};
display:flex;align-items:center;justify-content:center}} svg{{width:92%;max-height:80%;opacity:.55}}</style>{plan_figure(plan, result)}"""


def shoot(html: str, width: int, height: int, scale: float = 2, timeout: float = 60) -> bytes:
    """PNG of an HTML page at width x height CSS pixels."""
    with tempfile.TemporaryDirectory(prefix="cranley-card-") as d:
        src, out = Path(d) / "card.html", Path(d) / "card.png"
        src.write_text(html)
        cmd = [chrome(), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
               f"--user-data-dir={d}/profile", f"--window-size={width},{height}", f"--force-device-scale-factor={scale}",
               f"--screenshot={out}", src.as_uri()]
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as e:
            raise Unavailable("Chrome took too long to draw the card.") from e
        if not out.exists() or out.stat().st_size == 0:
            raise Unavailable("Chrome did not draw the card.")
        return out.read_bytes()


def card(run: dict, plan: dict | None) -> bytes:
    return shoot(card_html(run, plan), 540, 760)


def background(plan: dict, result: dict) -> bytes:
    return shoot(background_html(plan, result), 390, 844, scale=3)
