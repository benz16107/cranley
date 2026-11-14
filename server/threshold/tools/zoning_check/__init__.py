"""Zoning check: the zone on a lot and what it allows, as the city's own map and code say.

Los Angeles: the zone string from ZIMAS (City Planning), read into its class and height district, the class's uses
from a summary of the zoning code's use lists (LAMC chapter 1, article 2), the height district's floor
area ratio and height from LAMC 12.21.1, and the General Plan land use. The summary is a guide, not a determination:
conditions ([Q], [T]), D limitations, specific plans and overlays can narrow it, and ZIMAS's parcel profile lists them.

Houston has no zoning. The city maps what Chapter 42 adds (special minimum lot sizes, special building lines) and its
historic districts; private deed restrictions set most use limits and are not mapped by anyone.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from ...layers import lookup
from ...layers.sources import houston, los_angeles
from .. import (
    Check,
    Finding,
    GeoAnchor,
    Metric,
    NotApplicable,
    Place,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)

LAMC = "Los Angeles Municipal Code, chapter 1"
# zone class -> (what it is, its main uses), summarised from the use lists of LAMC chapter 1, article 2
LA_ZONES = {
    "A1": ("Agricultural", "farming, one-family homes on large lots"),
    "A2": ("Agricultural", "farming, one-family homes on large lots"),
    "RA": ("Suburban", "one-family homes, limited farming"),
    "RE": ("Residential estate", "one-family homes"),
    "RS": ("Suburban", "one-family homes"),
    "R1": ("One-family", "one-family homes"),
    "RU": ("Residential urban", "one-family homes on small lots"),
    "RZ": ("Residential zero side yard", "one-family homes"),
    "RW1": ("Residential waterways", "one-family homes"),
    "R2": ("Two-family", "one- and two-family homes"),
    "RW2": ("Residential waterways", "one- and two-family homes"),
    "RD": ("Restricted density multiple dwelling", "homes and apartments at limited density"),
    "RMP": ("Mobile home park", "mobile home parks"),
    "R3": ("Multiple dwelling", "apartments"),
    "RAS3": ("Residential/accessory services", "apartments with limited ground-floor shops"),
    "R4": ("Multiple dwelling", "apartments, also schools and churches"),
    "RAS4": ("Residential/accessory services", "apartments with limited ground-floor shops"),
    "R5": ("Multiple dwelling", "apartments, hotels"),
    "CR": ("Limited commercial", "offices, banks, limited shops; apartments"),
    "C1": ("Limited commercial", "local shops, offices, restaurants; apartments"),
    "C1.5": ("Limited commercial", "C1 uses plus some larger shops and hotels; apartments"),
    "C2": ("Commercial", "shops, restaurants, offices, hotels, limited repair; apartments"),
    "C4": ("Commercial", "C2 uses less some auto and amusement uses; apartments"),
    "C5": ("Commercial", "C2 uses plus limited manufacturing; apartments"),
    "CM": ("Commercial manufacturing", "wholesale, light manufacturing, commercial uses"),
    "MR1": ("Restricted industrial", "light industry and offices, no housing"),
    "M1": ("Limited industrial", "light industry, warehouses, most commercial uses"),
    "MR2": ("Restricted light industrial", "light industry, no housing"),
    "M2": ("Light industrial", "industry, warehouses"),
    "M3": ("Heavy industrial", "heavy industry"),
    "P": ("Automobile parking", "surface parking"),
    "PB": ("Parking building", "parking structures"),
    "OS": ("Open space", "parks and open land"),
    "PF": ("Public facilities", "public buildings and facilities"),
}
# a person's use -> zone classes that list it, and classes where it needs a discretionary approval or is limited
ONE_FAMILY = {"A1", "A2", "RA", "RE", "RS", "R1", "RU", "RZ", "RW1", "R2", "RW2", "RD", "R3", "R4", "R5"}
APARTMENT_ZONES = {"RD", "R3", "RAS3", "R4", "RAS4", "R5", "CR", "C1", "C1.5", "C2", "C4", "C5", "CM"}
SHOP_ZONES = {"C1", "C1.5", "C2", "C4", "C5", "CM", "M1", "M2", "M3"}
USES = {
    "home": ("a one-family home", ONE_FAMILY, set()),
    "adu": ("an accessory dwelling unit", ONE_FAMILY | APARTMENT_ZONES, set()),
    "apartments": ("apartments", APARTMENT_ZONES, set()),
    "shop": ("a shop", SHOP_ZONES, {"CR", "RAS3", "RAS4", "MR1"}),
    "restaurant": ("a restaurant", SHOP_ZONES, {"CR", "RAS3", "RAS4"}),
    "office": ("an office", SHOP_ZONES | {"CR", "MR1"}, {"RAS3", "RAS4"}),
    "hotel": ("a hotel", {"R5", "C1.5", "C2", "C4", "C5", "CM"}, set()),
    "daycare": ("a child care centre", {"C1", "C1.5", "C2", "C4", "C5", "CM"}, ONE_FAMILY | APARTMENT_ZONES),
    "industry": ("light industry or a warehouse", {"CM", "MR1", "M1", "MR2", "M2", "M3"}, {"C5"}),
    "heavy_industry": ("heavy industry", {"M3"}, {"M2"}),
}
WORDS = {"home": r"single.?family|house|one.?family", "adu": r"\badu\b|granny|accessory dwelling|backyard (home|unit)",
         "apartments": r"apartment|multi.?family|condo|duplex|fourplex|housing", "restaurant": r"restaurant|caf[eé]|coffee|bar\b|food",
         "shop": r"shop|store|retail|salon|boutique|gym|studio", "office": r"office|clinic|co.?work",
         "hotel": r"hotel|motel|hostel", "daycare": r"day.?care|child.?care|preschool|nursery",
         "heavy_industry": r"heavy industr|refiner|foundry", "industry": r"industr|warehouse|manufactur|workshop|factory|storage"}
# LAMC 12.21.1: floor area ratio by height district, and the height and story limits of the 1L, 1VL and 1XL districts
HD_FAR = {"1": 3.0, "2": 6.0, "3": 10.0, "4": 13.0}
HD_HEIGHT = {"1L": (75, 6), "1VL": (45, 3), "1XL": (30, 2)}
# zone suffixes that add an overlay district's own rules
OVERLAYS = {"HPOZ": "Historic Preservation Overlay Zone: exterior changes need the HPOZ board's review",
            "CPIO": "Community Plan Implementation Overlay: the community plan adds its own standards",
            "SN": "Sign district: its own sign rules", "O": "Oil drilling district", "CDO": "Community Design Overlay",
            "POD": "Pedestrian Oriented District", "RIO": "River Improvement Overlay", "RFA": "Residential Floor Area district",
            "CUGU": "Clean Up Green Up district", "SP": "Specific plan"}
DEED = ("Houston has no zoning. Most limits on what a lot may be used for come from the subdivision's deed "
        "restrictions, recorded with the plat at the Harris County Clerk; no public map of them exists, so read the "
        "restrictions for the subdivision before relying on a use.")


class Inputs(BaseModel):
    place: Place = field(source="selection.place")
    use: str | None = field(None, description="What the person wants to do there, in their words (a cafe, a daycare, apartments)")


def source(note: str, confidence: str = "high") -> Source:
    return Source(layer="model", method="lookup", confidence=confidence, note=note)


def parse_zone(zone: str) -> dict:
    """'[Q]C2-1VL-O' -> conditions ['Q'], class 'C2', height district '1VL', suffixes ['O']."""
    s = (zone or "").strip().upper()
    conditions = re.findall(r"[\[(]\s*([A-Z]+)\s*[\])]", s.split("-")[0])
    body = re.sub(r"^([\[(][A-Z]+[\])])+", "", s)
    parts = [p for p in body.split("-") if p]
    cls = parts[0] if parts else ""
    hd = next((p for p in parts[1:] if re.fullmatch(r"\d[A-Z]{0,2}", p)), "")
    rest = [p for p in parts[1:] if p != hd]
    return {"zone": zone, "conditions": conditions, "class": cls, "height_district": hd, "suffixes": rest,
            "chapter_1a": s.startswith("[") and "][" in s}


def use_key(use: str | None) -> str | None:
    return next((k for k, pat in WORDS.items() if use and re.search(pat, use, re.IGNORECASE)), None)


def judge_use(key: str, cls: str) -> tuple[str, str]:
    what, ok, limited = USES[key]
    if cls in ok:
        return "pass", f"The {cls} zone's use list includes {what}."
    if cls in limited:
        return "warn", f"In the {cls} zone {what} is limited or needs a discretionary approval."
    return "fail", f"The {cls} zone's use list does not include {what}."


def _la(ctx, site, inputs) -> ToolResult:
    lon, lat = site.lon, site.lat
    # ZIMAS answers point queries with nothing; a 40 m box round the point, then the shape holding it (or the nearest)
    rows = [r["properties"] for u in los_angeles.ZONING for r in lookup.arcgis_at(u, lon, lat, "ZONE_CMPLT", via_box=40)]
    plan = [r["properties"] for u in los_angeles.GENPLAN for r in lookup.arcgis_at(u, lon, lat, "*", via_box=40)]
    ctx.step(f"Read the zone and General Plan land use at the point from ZIMAS ({len(rows)} zone shape{'s' if len(rows) != 1 else ''})")
    anchor, src = GeoAnchor(geo=(lon, lat)), source("ZIMAS zoning layer, City of Los Angeles Planning")
    if not rows:
        raise NotApplicable("ZIMAS has no zone at this point: it is outside the City of Los Angeles (another city or the "
                            "county sets its zoning) or on a street.")
    z = parse_zone(rows[0].get("ZONE_CMPLT") or "")
    plan_use = next((p.get("POLYS.DESCRIPTION") or p.get("GPLU_LUT.DESCRIPTION") for p in plan if p), None)
    findings = [Finding(id=f"zoning_check:{site.key}:zone", title="Zone on the lot", status="unknown", anchor=anchor, source=src,
                        detail=f"{z['zone']}" + (f"; General Plan land use: {plan_use}" if plan_use else ""))]
    checks, metrics = [], []
    if z["chapter_1a"]:
        findings.append(Finding(id=f"zoning_check:{site.key}:chapter1a", title="New zoning code (Chapter 1A)", status="unknown",
                                anchor=anchor, source=src, detail="This lot is under the city's new zoning code (Chapter 1A), "
                                "written as [form-frontage-standards][use-density][district]. This tool does not read the new "
                                "code's use tables; ZIMAS's parcel profile links them."))
        return ToolResult(scope=site.scope(), verdict=Verdict(status="unknown", text=f"Zone {z['zone']} (new Chapter 1A code); "
                          "uses not read by this tool."), findings=findings)
    info = LA_ZONES.get(z["class"])
    csrc = source(f"{LAMC}, article 2 use lists, summarised", "medium")
    if info:
        findings.append(Finding(id=f"zoning_check:{site.key}:class", title=f"{info[0]} zone ({z['class']})", status="unknown",
                                anchor=anchor, source=csrc, detail=f"Main uses: {info[1]}."))
    hd = z["height_district"]
    if hd:
        far = HD_FAR.get(hd[0])
        if hd[0] == "1" and far and z["class"][:1] in ("C", "M"):
            far = 1.5  # height district 1 in the commercial and industrial zones
        hsrc = source("LAMC 12.21.1, height districts", "medium")
        if far:
            metrics.append(Metric(id="far", label="Floor area ratio limit", value=far, unit=":1", source=hsrc))
        if hd in HD_HEIGHT:
            ft, stories = HD_HEIGHT[hd]
            metrics += [Metric(id="height_ft", label="Height limit", value=ft, unit="ft", source=hsrc),
                        Metric(id="stories", label="Story limit", value=stories, unit="stories", source=hsrc)]
        findings.append(Finding(id=f"zoning_check:{site.key}:height", title=f"Height district {hd}", status="unknown", anchor=anchor,
                                source=hsrc, detail="Floor area ratio and height from LAMC 12.21.1. A D limitation or a specific "
                                "plan can set lower limits; one-family zones also have their own height rules."))
    if hd.endswith("D"):
        findings.append(Finding(id=f"zoning_check:{site.key}:d_limit", title="D limitation on height or floor area", status="warn",
                                anchor=anchor, source=src, detail="The D after the height district means the ordinance set lower "
                                "limits than the district's; the number is in the ordinance linked from ZIMAS, not in this map."))
    for sfx in z["suffixes"]:
        findings.append(Finding(id=f"zoning_check:{site.key}:overlay.{sfx}", title=f"Overlay: {sfx}", status="warn", anchor=anchor,
                                source=src, detail=OVERLAYS.get(sfx, "A supplemental district suffix") + "; ZIMAS links its rules."))
    if z["conditions"]:
        findings.append(Finding(id=f"zoning_check:{site.key}:conditions", title="Conditions on the zone", status="warn", anchor=anchor,
                                source=src, detail=f"[{'], ['.join(z['conditions'])}]: the ordinance that zoned this lot added "
                                "conditions (Q: qualified, T: tentative) that can limit uses or require improvements. Read the "
                                "ordinance linked in ZIMAS."))
    key = use_key(inputs.use)
    status, text = "unknown", f"Zone {z['zone']}" + (f", {info[0].lower()}" if info else "")
    if inputs.use and not key:
        text += f"; this tool has no rule for \"{inputs.use}\""
    if key and info:
        st, why = judge_use(key, z["class"])
        checks.append(Check(id=f"use.{key}", rule=f"Use: {USES[key][0]}", measured=None, threshold=None, unit="", status=st,
                            standard="LAMC chapter 1, article 2, summarised", findings=[f"zoning_check:{site.key}:use"]))
        findings.append(Finding(id=f"zoning_check:{site.key}:use", title=f"Use: {USES[key][0]}", status=st, anchor=anchor,
                                source=csrc, detail=why + " This is a summary of the code's use list, not a determination; "
                                "confirm with City Planning or LADBS."))
        status = "warn" if (z["conditions"] or hd.endswith("D")) and st == "pass" else st
        text += {"pass": f": {USES[key][0]} is on the zone's use list", "warn": f": {USES[key][0]} is limited or needs approval",
                 "fail": f": {USES[key][0]} is not on the zone's use list"}[st]
    return ToolResult(scope=site.scope(), verdict=Verdict(status=status, text=text + "."), metrics=metrics, checks=checks,
                      findings=findings)


def _houston(ctx, site, inputs) -> ToolResult:
    lon, lat = site.lon, site.lat
    anchor = GeoAnchor(geo=(lon, lat))
    lot = [r["properties"] for r in lookup.arcgis_at(houston.MIN_LOT, lon, lat, "LOTSIZE,ORDINANCE,Status,Expiration_Date")]
    line = [r["properties"] for r in lookup.arcgis_at(houston.BUILD_LINE, lon, lat, "BLD__LINE,ORDINANCE_,Status", radius_m=30)]
    hist = [r["properties"] for r in lookup.arcgis_at(houston.HISTORIC, lon, lat, "NAME")]
    use = [r["properties"] for r in lookup.arcgis_at(houston.LAND_USE, lon, lat, "GROUP_DSCR,LANDUSE_DSCR,YR_IMPR")]
    ctx.step("Read Houston's Chapter 42 lot-size and building-line areas, historic districts and the parcel's land use")
    src = source("City of Houston GIS (Planning and Development)")
    findings = [Finding(id=f"zoning_check:{site.key}:no_zoning", title="Houston has no zoning", status="unknown", anchor=anchor,
                        source=source("City of Houston; Harris County Clerk", "high"), detail=DEED)]
    checks, metrics = [], []
    for r in lot:
        if r.get("LOTSIZE"):
            metrics.append(Metric(id="min_lot_sqft", label="Special minimum lot size", value=r["LOTSIZE"], unit="sq ft", source=src))
        findings.append(Finding(id=f"zoning_check:{site.key}:min_lot", title="In a special minimum lot size area", status="warn",
                                anchor=anchor, source=src, detail=f"Lots here may not be split below {r.get('LOTSIZE') or 'the set'} "
                                f"square feet (ordinance {r.get('ORDINANCE') or 'not given'}, {r.get('Status') or 'status not given'})."))
    for r in line:
        if r.get("BLD__LINE"):
            metrics.append(Metric(id="building_line_ft", label="Special building line", value=r["BLD__LINE"], unit="ft", source=src))
        findings.append(Finding(id=f"zoning_check:{site.key}:build_line", title="On a special minimum building line", status="warn",
                                anchor=anchor, source=src, detail=f"Buildings on this blockface stand back at least {r.get('BLD__LINE')} ft "
                                f"from the street (ordinance {r.get('ORDINANCE_') or 'not given'})."))
    for r in hist:
        findings.append(Finding(id=f"zoning_check:{site.key}:historic", title="In a city historic district", status="warn", anchor=anchor,
                                source=src, detail=f"{r.get('NAME')}: exterior changes, new building and demolition need a "
                                "certificate of appropriateness from the Houston Archaeological and Historical Commission."))
    if use:
        u = use[0]
        findings.append(Finding(id=f"zoning_check:{site.key}:land_use", title="Present use of the parcel", status="unknown", anchor=anchor,
                                source=source("Harris Central Appraisal District land use, via City of Houston GIS", "medium"),
                                detail=f"{(u.get('GROUP_DSCR') or '').strip()}; {(u.get('LANDUSE_DSCR') or '').strip().title()}"
                                + (f"; built {u['YR_IMPR']}" if u.get("YR_IMPR") and str(u["YR_IMPR"]) != "0" else "")))
    if inputs.use:
        checks.append(Check(id="use.deed", rule=f"Use: {inputs.use}", measured=None, threshold=None, unit="", status="unknown",
                            standard="Deed restrictions (not mapped)", findings=[f"zoning_check:{site.key}:no_zoning"]))
    rules = len(lot) + len(line) + len(hist)
    text = ("Houston has no zoning; " + (f"{rules} city rule{'s' if rules > 1 else ''} mapped here (lot size, building line or "
            "historic district)" if rules else "no city lot-size, building-line or historic rule is mapped here")
            + "; deed restrictions are not mapped.")
    return ToolResult(scope=site.scope(), verdict=Verdict(status="unknown", text=text), metrics=metrics, checks=checks,
                      findings=findings)


@tool(id="zoning_check", title="Zoning check", icon="landmark",
      summary="What the zoning allows on a lot: the zone, its main uses and height or density limits in Los Angeles; in "
              "Houston, which has no zoning, the city's lot-size, building-line and historic rules.",
      model_description="Zoning at a place. Los Angeles: zone string from ZIMAS, its class and main uses (summary of LAMC "
                        "chapter 1), height district floor area ratio and height (LAMC 12.21.1), General Plan land use, "
                        "and whether a stated use is on the zone's use list. Houston: explains there is no zoning and "
                        "reports special minimum lot size, building lines, historic districts and the parcel's present "
                        "use; deed restrictions are not mapped. Give `use` in the person's words when they name one.",
      requires=[{"layer": "public.zoning"}], blocks=["VerdictHeader", "MetricRow", "CheckList", "Note", "StepLog"],
      examples=["Can I open a cafe here?", "Is this lot zoned for apartments?", "How tall can I build?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    site = lookup.locate(ctx, inputs.place)
    if site.lat is None:
        raise NotApplicable("This place has no location, so there is no zone to read.")
    ctx.step(f"Found {site.address or site.key} ({site.located_by})")
    city = lookup.city_at(site.lon, site.lat)
    if city == "la":
        return _la(ctx, site, inputs)
    if city == "hou":
        return _houston(ctx, site, inputs)
    raise NotApplicable("Zoning is read for Los Angeles and Houston only.")
