"""Photo measure: a width or a height from one photo with an object of known size in frame.

The reference (a bank card, a sheet of letter or A4 paper, or a door leaf of known size) is a rectangle whose four
corners fix the camera's perspective onto the plane it lies in. Any two points in that same plane can then be
measured. The vision reader finds the corners and the two ends; the person can move them. The arithmetic is here.

What it cannot do: measure anything that is not in the reference's plane. A card held against the door stop
measures the opening at the stop; it does not measure the room behind it."""
from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from ...capture import store
from .. import Assumption, Check, Finding, Metric, ToolError, ToolResult, Verdict, field, tool
from .._phone import anchor, key, media, scope, source

IN = 0.0254
# (long side, short side) in metres. Card: ISO/IEC 7810 ID-1. Letter: ANSI A. A4: ISO 216.
REFERENCES = {"card": (0.08560, 0.05398, "a bank card (ISO/IEC 7810 ID-1, 85.60 x 53.98 mm)"),
              "letter": (0.2794, 0.2159, "a sheet of US letter paper (8.5 x 11 in)"),
              "a4": (0.297, 0.210, "a sheet of A4 paper (210 x 297 mm)")}
DOOR_HEIGHT_M = 80 * IN   # a stock US door leaf is 6 ft 8 in tall; its width is the person's to give
PX = 1600                 # the photo is read at this many pixels on its long side
POINT_ERR = {"vision": 0.006, "manual": 0.003}   # how well a corner is placed, as a fraction of the long side
USELESS = 0.25            # an error this large against the length is not a measurement; no number is given
FAR_RATIO = 8.0           # the target this many times the reference's long side: the result is an extrapolation
TRIALS = 300

P2 = tuple[float, float]


class Points(BaseModel):
    """Fractions of the image, x right and y down. `corners` go round the reference from its top left as seen."""
    corners: list[P2] = Field(min_length=4, max_length=4)
    a: P2
    b: P2


class Inputs(BaseModel):
    capture: str = field(description="Capture id of the photo")
    reference: Literal["card", "letter", "a4", "door"] = field("card", description="What of known size is in frame")
    door_width_m: float | None = field(None, gt=0.3, le=1.5, description="For reference door: the leaf's width")
    what: str = field("the clear width of the doorway", max_length=200, description="What to measure, in words")
    points: Points | None = field(None, description="Where the reference's corners and the two ends are; found by "
                                                    "the vision reader when missing")
    points_from: Literal["vision", "manual"] = "vision"
    threshold_m: float | None = field(None, gt=0, description="A minimum to judge the result against")
    standard: str | None = None
    scan: str | None = None
    room: str | None = None
    opening: str | None = None


def homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """The 3 x 3 map taking four image points onto four plane points."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(src, dst):
        rows += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        rhs += [u, v]
    return np.append(np.linalg.solve(np.array(rows, float), np.array(rhs, float)), 1.0).reshape(3, 3)


def to_plane(h: np.ndarray, p) -> np.ndarray:
    x, y, w = h @ np.array([p[0], p[1], 1.0])
    return np.array([x / w, y / w])


def length(corners, a, b, long_m: float, short_m: float) -> float:
    """Distance from a to b in the reference's plane, metres. Points in pixels; corners clockwise from the top left
    as seen. The reference's longer side in the picture is taken as its long side."""
    c = np.array(corners, float)
    top, side = np.linalg.norm(c[1] - c[0]) + np.linalg.norm(c[2] - c[3]), np.linalg.norm(c[2] - c[1]) + np.linalg.norm(c[3] - c[0])
    w, h = (long_m, short_m) if top >= side else (short_m, long_m)
    hm = homography(c, np.array([[0, 0], [w, 0], [w, h], [0, h]], float))
    return float(np.linalg.norm(to_plane(hm, a) - to_plane(hm, b)))


def measure(points: Points, size: tuple[int, int], long_m: float, short_m: float, point_err: float) -> dict:
    """{length_m, err_m, ratio}. The error is half the width of the middle 95% of lengths when every point is moved
    by the placement error, so it grows as the reference gets small in the frame or far from what is measured.
    (Percentiles, not a standard deviation: a few trials where the jittered corners nearly fold give huge lengths.)"""
    wpx, hpx = size
    px = lambda p: (p[0] * wpx, p[1] * hpx)  # noqa: E731
    corners, a, b = [px(p) for p in points.corners], px(points.a), px(points.b)
    value = length(corners, a, b, long_m, short_m)
    rng = np.random.default_rng(0)
    sigma = point_err * max(wpx, hpx)
    trials = []
    for _ in range(TRIALS):
        j = rng.normal(0, sigma, (6, 2))
        try:
            trials.append(length([np.add(c, j[i]) for i, c in enumerate(corners)], np.add(a, j[4]), np.add(b, j[5]),
                                 long_m, short_m))
        except np.linalg.LinAlgError:
            continue
    lo, hi = np.percentile(trials, [2.5, 97.5]) if trials else (0.0, float("inf"))
    return {"length_m": value, "err_m": float(hi - lo) / 2, "ratio": value / long_m}


POINT = {"type": "object", "additionalProperties": False, "required": ["x", "y"],
         "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}}
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["reference_found", "corners", "ends_found", "a", "b", "same_plane", "confidence", "seen"],
          "properties": {"reference_found": {"type": "boolean"},
                         "corners": {"type": "array", "items": POINT, "minItems": 4, "maxItems": 4},
                         "ends_found": {"type": "boolean"}, "a": POINT, "b": POINT,
                         "same_plane": {"type": "string", "enum": ["yes", "no", "unsure"]},
                         "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                         "seen": {"type": "string", "description": "One sentence: what the two ends are on"}}}


def find_points(capture: str, reference: str, what: str, ask=None, image=None) -> dict:
    """Ask the vision reader where the reference's corners and the two ends are.
    {points: Points | None, same_plane, confidence, seen, size: (w, h)}. The model gives pixel positions only."""
    import io

    from PIL import Image
    if ask is None:
        from ...vision.model import ask
    data = (image or store.image)(capture, PX)
    w, h = Image.open(io.BytesIO(data)).size
    thing = REFERENCES[reference][2] if reference in REFERENCES else "a door leaf (the moving panel, not the frame)"
    out = ask([data], (
        f"This photo is {w} x {h} pixels. It should show {thing}, used as a size reference, and {what}.\n"
        "1. Give the four corners of the reference in pixels, going round it clockwise starting from its top left "
        "corner as it appears in the photo.\n"
        f"2. Give the two end points, a and b, of {what}, in pixels, at the height of the reference where that is "
        "possible. For a doorway's clear width these are the two inner faces a person passes between.\n"
        "3. same_plane: is the reference lying in the same flat plane as the line from a to b (for example held "
        "flat against the door stop, or taped to the wall the opening is in)?\n"
        "Set reference_found or ends_found false when you cannot see them; do not guess positions."),
        SCHEMA, key=f"photo_measure/{capture}/{reference}")
    ok = out["reference_found"] and out["ends_found"]
    frac = lambda p: (min(max(p["x"] / w, 0.0), 1.0), min(max(p["y"] / h, 0.0), 1.0))  # noqa: E731
    return {"points": Points(corners=[frac(p) for p in out["corners"]], a=frac(out["a"]), b=frac(out["b"])) if ok else None,
            "same_plane": out["same_plane"], "confidence": out["confidence"], "seen": out["seen"], "size": (w, h),
            "reference_found": out["reference_found"], "ends_found": out["ends_found"]}


def _size(capture: str) -> tuple[int, int]:
    import io

    from PIL import Image
    return Image.open(io.BytesIO(store.image(capture, PX))).size


@tool(id="photo_measure", title="Photo measure", icon="ruler",
      summary="Measures a width or a height from one photo that has a bank card, a sheet of paper or a door of known "
              "size in it.",
      model_description="Measure a length from a phone photo with a reference of known size in frame (card, letter, "
                        "a4, or a door leaf), by perspective correction onto the reference's plane. Returns the "
                        "length with an error that grows as the reference gets small or far. Needs a photo capture.",
      personas=["wheelchair_user", "furniture_mover"], requires=[{"layer": "phone.photo"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog"],
      examples=["Measure this doorway from my photo"])
def run(ctx, inputs: Inputs) -> ToolResult:
    if inputs.reference == "door":
        if not inputs.door_width_m:
            raise ToolError("A door as the reference needs the leaf's width.")
        long_m, short_m = max(DOOR_HEIGHT_M, inputs.door_width_m), min(DOOR_HEIGHT_M, inputs.door_width_m)
        ref_name = f"a door leaf {inputs.door_width_m:.3f} m wide and {DOOR_HEIGHT_M:.3f} m tall"
    else:
        long_m, short_m, ref_name = REFERENCES[inputs.reference]
    sc = scope(inputs.scan)
    plane, seen, who = "unsure", "", inputs.points_from
    pts = inputs.points
    if pts is None:
        ctx.step("Asking the vision reader for the reference's corners and the two ends")
        try:
            found = find_points(inputs.capture, inputs.reference, inputs.what)
        except LookupError as e:
            raise ToolError(str(e)) from None
        pts, plane, seen, who = found["points"], found["same_plane"], found["seen"], "vision"
        if pts is None:
            miss = "the reference" if not found["reference_found"] else "the two ends of what to measure"
            return ToolResult(scope=sc, verdict=Verdict(status="unknown", text=(
                f"The photo does not show {miss} clearly enough to measure. Retake it square on, with the reference "
                "flat against what you are measuring, or place the points by hand.")))
    try:
        m = measure(pts, _size(inputs.capture), long_m, short_m, POINT_ERR[who])
    except (np.linalg.LinAlgError, LookupError) as e:
        raise ToolError(f"Those points do not make a measurable picture: {e}") from None
    value, err = m["length_m"], m["err_m"]
    rel = err / value if value else 1.0
    if rel >= USELESS:
        return ToolResult(scope=sc, verdict=Verdict(status="unknown", text=(
            f"The reference is too small in this photo to measure {inputs.what}: the result would be good to no better "
            f"than {100 * USELESS:.0f}%. Move closer so the reference fills more of the frame, or use a larger one: a "
            "sheet of paper or the door itself for a doorway, a card only for a step or a threshold close up.")),
            assumptions=[Assumption(id="reference_px", label="Times the reference", value=round(m["ratio"], 1), unit="x")])
    conf = "low" if rel > 0.06 or m["ratio"] > FAR_RATIO or plane == "no" else "high" if rel <= 0.02 and plane != "unsure" else "medium"
    ctx.step(f"Perspective corrected onto the plane of {ref_name}; points placed by "
             f"{'the vision reader' if who == 'vision' else 'hand'}")
    src = source("vision" if who == "vision" else "manual", conf,
                 f"One photo, scaled from {ref_name}; ends placed by {'the vision reader' if who == 'vision' else 'the person'}"
                 + (f" ({seen})" if seen else ""))
    k = key(inputs.scan, inputs.opening or inputs.room, inputs.capture)
    fid = f"photo_measure:{k}"
    need = inputs.threshold_m
    status = ("unknown" if need is None else "pass" if value - err >= need else "fail" if value + err < need else "warn")
    xs, ys = [pts.a[0], pts.b[0]], [pts.a[1], pts.b[1]]
    box = (max(0.0, min(xs) - 0.02), max(0.0, min(ys) - 0.02), min(1.0, max(xs) + 0.02), min(1.0, max(ys) + 0.02))
    text = {"unknown": "Measured from the photo.", "pass": "Measured from the photo: wide enough, error allowed for.",
            "fail": "Measured from the photo: too narrow, error allowed for.",
            "warn": "Measured from the photo: within its error of your limit, so use a tape."}[status]
    if plane == "no":
        text += " The reference does not look to be in the same plane as what was measured, so treat this as rough."
    elif m["ratio"] > FAR_RATIO:
        text += " The reference is small next to what was measured, so the error is wide."
    return ToolResult(
        scope=sc, verdict=Verdict(status=status if conf != "low" or status == "unknown" else "warn", text=text),
        metrics=[Metric(id="length", label="Measured", value=round(value, 3), unit="m", source=src),
                 Metric(id="error", label="Give or take", value=round(err, 3), unit="m", source=src),
                 Metric(id="ratio", label="Times the reference", value=round(m["ratio"], 1), unit="x", source=src)],
        checks=[Check(id="length", rule=f"Photo measure: {inputs.what}", measured=round(value, 3), threshold=need, unit="m",
                      status=status, standard=inputs.standard, findings=[fid])],
        findings=[Finding(id=fid, title=f"Measured from a photo: {inputs.what}", status=status, source=src,
                          anchor=anchor(inputs.scan, inputs.room, inputs.opening), media=media(inputs.capture, box),
                          detail=f"{value:.3f} m, give or take {err:.3f} m, scaled from {ref_name}."
                                 + (f" {seen}" if seen else ""))],
        assumptions=[Assumption(id="same_plane", label="The reference lies in the same plane as what is measured",
                                value={"yes": "looks so", "no": "does not look so", "unsure": "not checked"}[plane]),
                     Assumption(id="points_from", label="Points placed by", value="vision reader" if who == "vision" else "you"),
                     Assumption(id="lens", label="Lens distortion is not corrected; keep the subject near the middle",
                                value=True)])
