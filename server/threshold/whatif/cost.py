"""Cost of each edit: quantities from the diff and from geometry.takeoff, times unit costs that are labelled
assumptions with the source they came from. Every price here is low reliability: national averages from cost guides,
not a quote, and no local labour rate."""
from __future__ import annotations

from ..geometry import takeoff

FT = 3.28084
FT2 = FT * FT

# id: (label, value, unit, source, reliability)
PRICES: dict[str, tuple[str, float, str, str, str]] = {
    "widen_door": ("Widen a doorway: reframe, new header, prehung door", 1200, "$ each",
                   "Angi, widen doorway cost (2026 data): national average $1,200, range $700 to $2,500 per doorway",
                   "low"),
    "offset_hinges": ("Offset (swing-clear) hinges on an existing door", 250, "$ each",
                      "Angi, widen doorway cost (2026 data): offset hinges $150 to $350 per door", "low"),
    "pocket_door": ("Pocket door in place of a hinged door", 1200, "$ each",
                    "Assumed equal to widening a doorway (Angi average, $1,200); no separate source found", "low"),
    "rehang_door": ("Rehang a door to swing the other way", 250, "$ each",
                    "Assumed equal to offset hinges (Angi, $150 to $350); no separate source found", "low"),
    "remove_wall": ("Take out a non-load-bearing partition, patch and finish", 80, "$ per linear ft",
                    "Danbury Renovation (2026) $25 to $75 and CurrentCost.org (2026) $60 to $130 per linear ft "
                    "for a non-bearing wall", "low"),
    "new_partition": ("New partition, framed and finished", 95, "$ per linear ft",
                      "takeoff_bid fit-out default (bid.fit.partition), the project's existing price book", "low"),
    "floor_patch": ("Floor patched where a wall stood or moved", 4.5, "$ per ft²",
                    "takeoff_bid fit-out default (bid.fit.floor): carpet tile or LVT installed", "low"),
    "paint": ("Repaint the rooms whose walls change, two coats", 0.95, "$ per wall ft²",
              "takeoff_bid unit-turn default (bid.turn.paint)", "low"),
    "ramp": ("Ramp at 1:12, installed", 185, "$ per linear ft",
             "HomeCostCalc (Sep 2026) about $185 per linear ft typical; HomeAdvisor (2025) $55 to $275", "low"),
    "grab_bar": ("Grab bar with blocking, installed", 200, "$ each",
                 "Thrive Homes: $50 to $200 per bar; the top of the range, since blocking means opening the wall",
                 "low"),
}
LOAD_BEARING_NOTE = ("Assumes the wall is not load-bearing. A bearing wall needs a beam and an engineer: guides quote "
                     "$100 to $450 or more per linear ft (Danbury Renovation, 2026). The scan cannot tell which walls "
                     "carry load. Pipes and wiring in the wall are not counted.")


def prices(overrides: dict[str, float] | None = None) -> dict[str, float]:
    return {k: v[1] for k, v in PRICES.items()} | (overrides or {})


def assumptions(used: set[str], overrides: dict[str, float] | None = None) -> list[dict]:
    p = prices(overrides)
    return [{"id": f"whatif.price.{k}", "label": PRICES[k][0], "value": p[k], "unit": PRICES[k][2],
             "source": PRICES[k][3], "reliability": PRICES[k][4], "editable": True} for k in PRICES if k in used]


def _paint_ft2(after: dict, rooms: list[str]) -> float:
    t = takeoff(after)
    if not t.get("available"):
        return 0.0
    return sum((x["wall_area_net"] or 0) for x in t["rooms"] if x["room"] in rooms) * FT2


def line(change: dict, after: dict, overrides: dict[str, float] | None = None) -> dict:
    """One edit's cost: items of (price id, quantity, unit, amount) and the total, in dollars."""
    p = prices(overrides)
    items: list[tuple[str, float, str]] = []
    note = None
    op = change["op"]
    if op == "widen_door":
        items.append(("widen_door", 1, "door"))
    elif op == "door_swing":
        items.append(({"offset_hinges": "offset_hinges", "pocket": "pocket_door", "swing_out": "rehang_door"}[change["swing"]], 1, "door"))
    elif op == "remove_wall":
        lf = change["length"] * FT
        items += [("remove_wall", lf, "ft"), ("floor_patch", lf * 0.5, "ft²"),
                  ("paint", _paint_ft2(after, [change["merged_into"]]), "ft²")]
        note = LOAD_BEARING_NOTE
    elif op == "move_wall":
        lf = change["length"] * FT
        items += [("remove_wall", lf, "ft"), ("new_partition", lf, "ft"),
                  ("floor_patch", change["swept_m2"] * FT2 + lf * 0.5, "ft²"),
                  ("paint", _paint_ft2(after, change["rooms"]), "ft²")]
        note = LOAD_BEARING_NOTE
    elif op == "add_ramp":
        items.append(("ramp", max(1.0, change["run_m"] * FT), "ft"))
    elif op == "grab_bars":
        items.append(("grab_bar", change["bars"], "bar"))
    rows = [{"price": k, "label": PRICES[k][0], "quantity": round(q, 1), "unit": u, "rate": p[k],
             "amount": round(q * p[k])} for k, q, u in items]
    return {"items": rows, "total": sum(r["amount"] for r in rows), "reliability": "low", "note": note,
            "quantities_from": "geometry.takeoff (net wall area) and the edit's own lengths"}
