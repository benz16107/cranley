"""Contract 3 (ToolResult) and Contract 4 (overlays) from docs/ARCHITECTURE.md, plus the tool manifest.

Every model forbids unknown fields, so a typo in a tool fails at the tool, not in the browser.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Status = Literal["pass", "warn", "fail", "unknown"]
Point2 = tuple[float, float]
Point3 = tuple[float, float, float]


class Source(Strict):
    # "phone": captured by a person on site with the phone app (threshold/capture). "sensor" is a device sensor
    # reading (tilt, compass, GPS, microphone); "manual" is a value the person measured and typed.
    layer: Literal["matterport", "vexcel", "costar", "drone", "model", "phone"]
    method: Literal["geometry", "vision", "lookup", "simulation", "sensor", "manual"]
    confidence: Literal["high", "medium", "low"]
    note: str | None = None


# Anchors. Each shape names the frame it lives in; extra="forbid" lets pydantic tell them apart by fields.
class PointAnchor(Strict):
    sid: str
    point: Point3


class RoomAnchor(Strict):
    sid: str
    room: str


class OpeningAnchor(Strict):
    sid: str
    opening: str


class WallAnchor(Strict):
    sid: str
    wall: str


class PanoAnchor(Strict):
    sid: str
    pano: str
    yaw_deg: float
    pitch_deg: float


class GeoAnchor(Strict):
    geo: tuple[float, float] = Field(description="[lon, lat]")


Anchor = Union[PointAnchor, RoomAnchor, OpeningAnchor, WallAnchor, PanoAnchor, GeoAnchor]


class Metric(Strict):
    id: str
    label: str
    value: float | None
    unit: str
    source: Source


class Check(Strict):
    id: str
    rule: str
    measured: float | None
    threshold: float | None
    unit: str
    status: Status
    standard: str | None = None
    findings: list[str] = []
    kind: Literal["limit", "claim"] = Field("limit", description="claim: `threshold` is what a record or a listing says, not a limit to meet")


class Media(Strict):
    kind: Literal["pano", "ortho", "drone", "phone"]  # phone: ref is a capture id, served at /api/capture/<ref>/file
    ref: str
    box: tuple[float, float, float, float] | None = None


class Finding(Strict):
    id: str
    title: str
    status: Status
    detail: str
    anchor: Anchor | None
    source: Source
    media: list[Media] = []


# Contract 4: overlays. Renderers ignore kinds they do not know.
class Legend(Strict):
    title: str
    unit: str
    min: float
    max: float


class LensOverlay(Strict):
    kind: Literal["lens"] = "lens"
    values: dict[str, float] = Field(description="room id -> value")
    ramp: Literal["sequential", "status"]
    legend: Legend


class SelectRooms(Strict):
    rooms: list[str]


class SelectRoomLabels(Strict):
    room_labels: list[str]


class SelectOpenings(Strict):
    openings: list[str]


class SelectWalls(Strict):
    walls: list[str]


class RuleOverlay(Strict):
    kind: Literal["rule"] = "rule"
    select: SelectRooms | SelectRoomLabels | SelectOpenings | SelectWalls
    style: Literal["solid", "dim", "hide", "highlight", "pass", "warn", "fail"]


class Pin(Strict):
    id: str
    anchor: Anchor
    label: str
    status: Status


class PinsOverlay(Strict):
    kind: Literal["pins"] = "pins"
    pins: list[Pin]


class Choke(Strict):
    point: Point3
    width: float
    status: Status


class RouteOverlay(Strict):
    kind: Literal["route"] = "route"
    floor: str
    points: list[Point3]
    chokes: list[Choke] = []
    label: str


class WaterOverlay(Strict):
    kind: Literal["water"] = "water"
    level_m: float
    datum: Literal["scan_z"] = "scan_z"


class BoxOverlay(Strict):
    kind: Literal["box"] = "box"
    center: Point3
    size: Point3
    yaw_deg: float = 0
    label: str
    status: Status


Overlay = Annotated[LensOverlay | RuleOverlay | PinsOverlay | RouteOverlay | WaterOverlay | BoxOverlay,
                    Field(discriminator="kind")]
OverlayKind = Literal["lens", "rule", "pins", "route", "water", "box"]


class Assumption(Strict):
    id: str = Field(description="For an editable assumption, the preference key (x-pref) that an edit sets")
    label: str
    value: float | str | bool | None
    unit: str | None = None
    editable: bool = False


class Action(Strict):
    id: str
    label: str
    tool: str
    inputs: dict[str, Any] = {}


class Verdict(Strict):
    status: Status
    text: str


class ScanScope(Strict):
    sid: str


class AddressScope(Strict):
    address: str
    geo: Point2 | None = Field(None, description="[lon, lat] the address resolved to")


class ScansScope(Strict):
    sids: list[str]


class PropertyScope(Strict):
    property_id: int = Field(description="CoStar PropertyId")
    sids: list[str] = Field([], description="The property's scans the result covers")


class GeoScope(Strict):
    geo: Point2 = Field(description="[lon, lat]")


Scope = Union[ScanScope, AddressScope, ScansScope, PropertyScope, GeoScope]


class Place(Strict):
    """Where a tool runs when it does not need a scan: a scan id, a CoStar property id (all its scans), an address,
    or a point. Give one; `ctx.site(place)` resolves it to coordinates, address, property and scans."""
    scan: str | None = None
    property_id: int | None = None
    address: str | None = None
    geo: Point2 | None = Field(None, description="[lon, lat]")

    @model_validator(mode="after")
    def _one(self):
        if not any(v is not None for v in (self.scan, self.property_id, self.address, self.geo)):
            raise ValueError("a place needs a scan, property_id, address or geo")
        if self.geo and not (-180 <= self.geo[0] <= 180 and -90 <= self.geo[1] <= 90):
            raise ValueError("geo is [lon, lat]")
        return self

    def key(self) -> str:
        """Stable id for finding ids and panels: scan id, p<property>, a<address words>, or g<lon>,<lat>."""
        if self.scan:
            return self.scan
        if self.property_id is not None:
            return f"p{self.property_id}"
        if self.address:
            return "a" + "-".join(re.findall(r"[a-z0-9]+", self.address.lower()))
        return f"g{self.geo[0]:.5f},{self.geo[1]:.5f}"


class ToolResult(Strict):
    tool: str = ""  # filled by run_tool
    scope: Scope
    verdict: Verdict
    metrics: list[Metric] = []
    checks: list[Check] = []
    findings: list[Finding] = []
    overlays: list[Overlay] = []
    assumptions: list[Assumption] = []
    actions: list[Action] = []


# The manifest. One per tool; it feeds the agent, the web tool dock, and later MCP and a CLI.
PanelBlockType = Literal["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "RankedTable", "MiniChart",
                         "FloorPlanMini", "Controls", "AssumptionChips", "StepLog", "Note", "ActionBar"]


class Requirement(Strict):
    layer: str = Field(description="e.g. matterport.rooms, matterport.openings, vexcel.ortho, costar.property")
    need: Literal["required", "optional"] = "required"
    fallback: str | None = None


class Annotations(Strict):
    read_only: bool = True
    cost: Literal["fast", "slow"] = "fast"


class TableColumn(Strict):
    metric: str
    label: str
    better: Literal["higher", "lower"] = "higher"


class Manifest(Strict):
    id: str
    title: str
    summary: str = Field(description="For the person: tooltip and 'why this tool'")
    model_description: str = Field(description="For the model: when to use it and what it returns")
    icon: str | None = None
    personas: list[str] = []
    requires: list[Requirement] = []
    inputs: dict[str, Any] = Field(default_factory=dict, description="JSON Schema with x-ask, x-pref, x-source, x-unit")
    blocks: list[PanelBlockType] = []
    overlays: list[OverlayKind] = []
    annotations: Annotations = Annotations()
    examples: list[str] = []
    status: Literal["ready", "planned"] = "ready"
    table: list[TableColumn] = Field([], description="Columns of the run's own RankedTable: each row is a key k with "
                                                     "metrics `k/<column.metric>`; the first cell's label names the row")
