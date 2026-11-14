"""Geometry engine: measured facts from a ScanPlan (Contract 1). Pure Python, deterministic, no network.

Every function takes the ScanPlan dict and returns a JSON-ready dict with `available: bool`. When the scan
cannot answer (no wall graph, no outline, no geocoordinates) the dict has `available: False` and a plain
`reason`; nothing here raises on missing data. Distances are metres in the scan frame, z up.

    room_graph(plan)                         rooms, doors, open edges, entrances, components
    route(plan, start, end, min_width=)      walkable route, doors crossed, chokes, Contract 4 route overlay
    reach(plan, min_width)                   which rooms a body that wide can reach from an entrance
    turning_space(plan, room) / turning_spaces(plan)    largest circle in a room (wheelchair turn 1.525 m)
    carry(plan, start, end, box, flat=)      can a w x d x h box be carried along the route
    free_wall_runs(plan, room)               straight wall stretches with no openings, longest first
    list_packs() / evaluate_pack(plan, pack, params)    rule packs -> Contract 3 checks and findings
    takeoff(plan)                            areas, wall area net of openings, doors, windows, glazing
    to_latlon / from_latlon / to_enu / from_enu         scan frame <-> geography (convention unverified)
    facing(plan) / sun_on_windows(plan, date)           compass direction of windows, hours of direct sun
    water(plan, level) / flood_levels(plan)             depth per room, wetted areas, flood order
"""
from .fit import (
    WHEELCHAIR_TURN_M,
    carry,
    corner_max_length,
    free_wall_runs,
    turning_space,
    turning_spaces,
)
from .georef import (
    facing,
    from_enu,
    from_latlon,
    sun_on_windows,
    sun_position,
    to_enu,
    to_latlon,
)
from .graph import room_graph
from .routes import ADA_DOOR_CLEAR_M, reach, route
from .rules import evaluate_pack, list_packs, load_pack
from .takeoff import takeoff
from .water import flood_levels, water

__all__ = [
    "ADA_DOOR_CLEAR_M",
    "WHEELCHAIR_TURN_M",
    "carry",
    "corner_max_length",
    "evaluate_pack",
    "facing",
    "flood_levels",
    "free_wall_runs",
    "from_enu",
    "from_latlon",
    "list_packs",
    "load_pack",
    "reach",
    "room_graph",
    "route",
    "sun_on_windows",
    "sun_position",
    "takeoff",
    "to_enu",
    "to_latlon",
    "turning_space",
    "turning_spaces",
    "water",
]
