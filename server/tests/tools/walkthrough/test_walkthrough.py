"""walkthrough: a census from video frames. The frames and the vision reader are faked; ffmpeg is tried when installed."""
import shutil
import subprocess

import pytest

from threshold.capture import frames, store
from threshold.tools import ToolContext
from threshold.tools import walkthrough as wt


def frame(room, alarm="ceiling not in view", ceiling=False, hazards=("none seen",), belongings=(), confidence="high"):
    return {"index": 0, "room": room, "ceiling_in_view": ceiling, "smoke_alarm": alarm, "hazards": list(hazards),
            "belongings": [{"label": b, "value": v} for b, v in belongings], "confidence": confidence}


READ = [frame("Living Room", belongings=[("television", "high")]), frame("Hallway", "seen", True),
        frame("Bedroom", "not seen", True), frame("Bedroom", "not seen", True, hazards=["loose rug or cord across a walkway"]),
        frame("Kitchen"), frame("Bedroom", "seen", True, confidence="medium"), frame("Outdoors")]


def run(read=READ, geo=None):
    shots = [(i * 4.0, b"jpeg") for i in range(len(read))]
    ask = lambda images, prompt, schema, key: {"frames": read[int(key.rsplit("/", 1)[1].split("-")[0]):][:len(images)]}  # noqa: E731
    return wt.run(ToolContext(), wt.Inputs(capture="cap_v", geo=geo), shots=shots, ask=ask)


def test_frames_become_rooms_and_only_a_confident_sighting_counts():
    rooms = wt.census([{**f, "index": i} for i, f in enumerate(READ)])
    assert [(r["room"], r["n"], len(r["frames"])) for r in rooms] == [("Living Room", 1, 1), ("Hallway", 1, 1), ("Bedroom", 1, 2),
                                                                      ("Kitchen", 1, 1), ("Bedroom", 2, 1), ("Outdoors", 1, 1)]
    assert [r["alarm"] for r in rooms][:5] == ["could not see", "seen", "not seen", "could not see", "could not see"]


def test_the_census():
    r = run(geo=(-95.37, 29.76))
    assert r.verdict.status == "warn" and r.verdict.text.startswith("5 rooms seen in the video. Of 3 bedrooms and hallways, a smoke "
                                                                    "alarm was seen in 1, not seen in 1, and 1 could not be checked.")
    assert "first look from a video, not a scan" in r.verdict.text and r.scope.geo == (-95.37, 29.76)
    assert {m.id: m.value for m in r.metrics} == {"rooms": 5, "alarms_seen": 1, "alarms_not_seen": 1, "hazards": 1, "belongings_high": 1}
    bed = next(f for f in r.findings if f.id == "walkthrough:cap_v:alarm:bedroom_1")
    assert bed.status == "warn" and "not a finding of absence" in bed.detail and [m.ref for m in bed.media] == ["cap_v#2", "cap_v#3"]
    assert bed.source.layer == "phone" and bed.source.method == "vision" and "R314.3" in r.checks[0].standard
    assert any(f.title == "Bedroom 1: loose rug or cord across a walkway" for f in r.findings)
    assert next(c for c in r.checks if c.id == "alarm.bedroom_2").status == "unknown"    # a medium-confidence sighting


def test_no_bedroom_recognised_and_no_frames():
    r = run([frame("Kitchen"), frame("Living Room")])
    assert r.verdict.status == "unknown" and "could not be checked" in r.verdict.text and r.scope.sids == []
    assert wt.run(ToolContext(), wt.Inputs(capture="cap_v"), shots=[], ask=None).verdict.status == "unknown"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_ffmpeg_takes_evenly_spaced_frames_from_a_real_file(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path)
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=10", "-pix_fmt", "yuv420p", str(clip)], check=True)
    cap = store.save("ws_v", store.Meta(kind="video"), clip.read_bytes())
    shots = frames.extract(cap["id"], 4)
    assert [t for t, _ in shots] == [0.5, 1.5, 2.5, 3.5] and all(b[:3] == b"\xff\xd8\xff" for _, b in shots)
    assert frames.frame(cap["id"], 2) == shots[2][1] and frames.extract(cap["id"], 4) == shots       # cached the second time
    with pytest.raises(LookupError):
        frames.frame(cap["id"], 9)
