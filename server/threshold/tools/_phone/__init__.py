"""Shared by the phone-fed tools (field_check, photo_measure, slope_check, noise_level, where_am_i, window_check,
floor_height, walkthrough). Not a tool. A phone result cites its capture as Contract 3 media (`kind: "phone"`) and
names `layer: "phone"` as its source, with the method that produced the number: a device sensor, a value the
person typed, or the vision reader looking at their photo."""
from __future__ import annotations

from .. import OpeningAnchor, RoomAnchor, ScanScope, Source
from ..types import GeoAnchor, GeoScope, Media, ScansScope


def source(method: str, confidence: str, note: str) -> Source:
    return Source(layer="phone", method=method, confidence=confidence, note=note)


def scope(scan: str | None, geo=None):
    """A scan when the reading belongs to one, the fix when it has one, else no scan at all."""
    return ScanScope(sid=scan) if scan else GeoScope(geo=tuple(geo)) if geo else ScansScope(sids=[])


def anchor(scan: str | None, room: str | None = None, opening: str | None = None, geo=None):
    if scan and opening:
        return OpeningAnchor(sid=scan, opening=opening)
    if scan and room:
        return RoomAnchor(sid=scan, room=room)
    return GeoAnchor(geo=tuple(geo)) if geo else None


def media(capture: str | None, box=None) -> list[Media]:
    return [Media(kind="phone", ref=capture, box=box)] if capture else []


def key(scan: str | None, *parts: str | None) -> str:
    """The middle of a finding id: `<tool>:<key>`."""
    return ":".join(p for p in (scan or "site", *parts) if p)
