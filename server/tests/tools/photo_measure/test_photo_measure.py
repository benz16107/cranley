"""photo_measure: perspective correction from a known rectangle, with an error that knows when it is extrapolating."""
import io

import numpy as np
import pytest
from PIL import Image

from threshold.capture import store
from threshold.tools import ToolContext, ToolError, run_tool
from threshold.tools import photo_measure as pm

W, H = 1600, 1200
# a wall seen at an angle: plane metres -> pixels
VIEW = np.array([[900.0, 60.0, 250.0], [30.0, 880.0, 150.0], [0.08, 0.05, 1.0]])


def px(x, y):
    u, v = pm.to_plane(VIEW, (x, y))
    return (u / W, v / H)


def card_at(x, y, long=0.0856, short=0.05398, upright=False):
    w, h = (short, long) if upright else (long, short)
    return [px(x, y), px(x + w, y), px(x + w, y + h), px(x, y + h)]


@pytest.fixture(autouse=True)
def photo(tmp_path, monkeypatch):
    buf = io.BytesIO()
    Image.new("RGB", (W, H), "white").save(buf, "JPEG")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    return store.save("ws_t", store.Meta(kind="photo"), buf.getvalue())["id"]


def test_a_known_span_comes_back_through_the_perspective():
    pts = pm.Points(corners=card_at(0.40, 0.50), a=px(0.05, 0.52), b=px(0.86, 0.52))
    m = pm.measure(pts, (W, H), 0.0856, 0.05398, 0.0)
    assert m["length_m"] == pytest.approx(0.81, abs=1e-6) and m["err_m"] == 0 and m["ratio"] == pytest.approx(9.46, abs=0.01)
    upright = pm.Points(corners=card_at(0.40, 0.50, upright=True), a=px(0.05, 0.52), b=px(0.86, 0.52))
    assert pm.measure(upright, (W, H), 0.0856, 0.05398, 0.0)["length_m"] == pytest.approx(0.81, abs=1e-6)  # a card held upright


def test_the_error_follows_how_large_the_reference_is_in_the_frame():
    span = dict(a=px(0.05, 0.52), b=px(0.86, 0.52))
    card = pm.measure(pm.Points(corners=card_at(0.40, 0.50), **span), (W, H), 0.0856, 0.05398, 0.003)
    sheet = pm.measure(pm.Points(corners=card_at(0.30, 0.40, 0.2794, 0.2159), **span), (W, H), 0.2794, 0.2159, 0.003)
    door = pm.measure(pm.Points(corners=card_at(0.02, 0.0, 2.032, 0.762), **span), (W, H), 2.032, 0.762, 0.003)
    assert door["err_m"] < sheet["err_m"] < card["err_m"] and 0.02 < sheet["err_m"] < 0.06 and card["err_m"] > 0.1
    # a card is too small in the frame to fix the perspective: it is read as scale only, and says so
    assert (card["model"], sheet["model"], door["model"]) == ("square_on", "perspective", "perspective")
    assert card["length_m"] == pytest.approx(0.81, abs=0.01)       # centred on the span, the scale-only reading holds
    by_vision = pm.measure(pm.Points(corners=card_at(0.30, 0.40, 0.2794, 0.2159), **span), (W, H), 0.2794, 0.2159, 0.006)
    assert by_vision["err_m"] > sheet["err_m"]      # the vision reader places points less well than a person does


def test_scale_only_is_exact_square_on_and_biased_off_centre():
    flat = np.array([[800.0, 0.0, 200.0], [0.0, 800.0, 100.0], [0.0, 0.0, 1.0]])       # a camera facing the wall square on
    f = lambda x, y: tuple(pm.to_plane(flat, (x, y)))  # noqa: E731
    sheet = [f(0.3, 0.4), f(0.5794, 0.4), f(0.5794, 0.6159), f(0.3, 0.6159)]
    assert pm.length_square_on(sheet, f(0.0, 0.5), f(0.9, 0.5), 0.2794, 0.2159) == pytest.approx(0.9, abs=1e-9)
    tilted = [tuple(v * s for v, s in zip(p, (W, H))) for p in card_at(0.02, 0.50, 0.2794, 0.2159)]   # the sheet at one end of the span
    a, b = (tuple(v * s for v, s in zip(px(x, 0.52), (W, H))) for x in (0.05, 0.86))
    off = pm.length_square_on(tilted, a, b, 0.2794, 0.2159)
    assert abs(off - 0.81) > 0.01 and pm.length(tilted, a, b, 0.2794, 0.2159) == pytest.approx(0.81, abs=1e-6)


def test_the_tool_judges_with_the_error(photo):
    sheet = {"corners": card_at(0.30, 0.40, 0.2794, 0.2159), "a": px(0.05, 0.52), "b": px(0.86, 0.52)}
    r = run_tool("photo_measure", {"capture": photo, "reference": "letter", "points": sheet, "points_from": "manual",
                                   "threshold_m": 0.76, "scan": "home", "opening": "RB"}, ToolContext())
    assert next(m for m in r.metrics if m.id == "length").value == pytest.approx(0.81, abs=0.001)
    assert r.verdict.status == "pass" and r.findings[0].source.layer == "phone" and r.findings[0].source.method == "manual"   # 0.81 - 0.04 clears 0.76
    assert r.findings[0].media[0].kind == "phone" and r.findings[0].media[0].ref == photo and r.findings[0].anchor.opening == "RB"
    x0, y0, x1, y1 = r.findings[0].media[0].box
    assert x0 < px(0.05, 0.52)[0] < px(0.86, 0.52)[0] < x1              # the box frames the measured line
    close = run_tool("photo_measure", {"capture": photo, "reference": "letter", "points": sheet, "points_from": "manual",
                                       "threshold_m": 0.815}, ToolContext())
    assert close.verdict.status == "warn" and "use a tape" in close.verdict.text       # 0.81 +/- err straddles 0.815
    card = {"corners": card_at(0.40, 0.50), "a": px(0.05, 0.52), "b": px(0.86, 0.52)}
    far = run_tool("photo_measure", {"capture": photo, "reference": "card", "points": card, "points_from": "manual"}, ToolContext())
    assert far.findings[0].source.confidence == "low" and "small next to what was measured" in far.verdict.text
    assert next(x for x in far.assumptions if x.id == "square_on").label.startswith("Camera taken as facing the plane square on")
    seen = run_tool("photo_measure", {"capture": photo, "reference": "card", "points": card, "points_from": "vision"}, ToolContext())
    assert seen.verdict.status == "unknown" and "too small in this photo" in seen.verdict.text and seen.metrics == []   # no number given


def test_the_vision_reader_gives_pixels_only_and_can_say_it_does_not_see(photo, monkeypatch):
    def seen(images, prompt, schema, key):
        assert "1600 x 1200" in prompt and key == f"photo_measure/{photo}/letter"
        c = [(round(x * W), round(y * H)) for x, y in card_at(0.30, 0.40, 0.2794, 0.2159)]
        a, b = px(0.05, 0.52), px(0.86, 0.52)
        assert all(v.get("minItems", 0) <= 1 for v in schema["properties"].values())   # the model API refuses longer fixed arrays
        return {"reference_found": True, **{k: {"x": x, "y": y} for k, (x, y) in zip(pm.CORNERS, c)}, "ends_found": True,
                "a": {"x": round(a[0] * W), "y": round(a[1] * H)}, "b": {"x": round(b[0] * W), "y": round(b[1] * H)},
                "same_plane": "yes", "confidence": "high", "seen": "The two door stops."}
    found = pm.find_points(photo, "letter", "the clear width of the doorway", ask=seen)
    assert found["size"] == (W, H) and found["points"].a == pytest.approx(px(0.05, 0.52), abs=1e-3)
    monkeypatch.setattr(pm, "find_points", lambda *a, **k: {**found, "points": None, "reference_found": False})
    r = run_tool("photo_measure", {"capture": photo, "reference": "letter"}, ToolContext())
    assert r.verdict.status == "unknown" and "does not show the reference" in r.verdict.text and r.metrics == []
    monkeypatch.setattr(pm, "find_points", lambda *a, **k: found)
    r = run_tool("photo_measure", {"capture": photo, "reference": "letter"}, ToolContext())
    assert r.findings[0].source.method == "vision" and "The two door stops." in r.findings[0].detail
    assert next(m for m in r.metrics if m.id == "length").value == pytest.approx(0.81, abs=0.005)   # pixel rounding only


def test_a_door_reference_needs_its_width(photo):
    with pytest.raises(ToolError, match="leaf's width"):
        run_tool("photo_measure", {"capture": photo, "reference": "door"}, ToolContext())
    with pytest.raises(ToolError, match="no capture"):
        run_tool("photo_measure", {"capture": "cap_missing", "reference": "card",
                                   "points": {"corners": card_at(0.4, 0.5), "a": px(0, 0.5), "b": px(0.8, 0.5)}}, ToolContext())
