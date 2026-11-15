"""Indoor Wi-Fi signal through the wall graph: COST 231 multi-wall model.

    L = FSPL(d) + sum(walls crossed x loss per wall type) + n_f ** ((n_f + 2) / (n_f + 1) - b) x L_f

COST 231, "Digital mobile radio towards future generation systems", Final Report (1999), section 4.7.2, the
multi-wall model: free-space loss over the straight-line distance plus a loss for every wall and floor the
straight line crosses. Its fitted constants (1.8 GHz): light wall 3.4 dB, heavy wall 6.9 dB, floor 18.3 dB, b 0.46.
The 2.4 GHz values below keep those; the 5 GHz values are assumed higher (about 1.5x per wall, 22 dB per floor),
because loss through building materials grows with frequency. Every constant is an assumption the result lists."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ...geometry._plan import floor_z
from ...signals.plan2d import Segs, cross_t, floor_order, segments

COST231 = "COST 231 Final Report (1999), 4.7.2, multi-wall model"
HEAVY_WALL_M = 0.20       # thicker than a 2x4 stud wall with drywall both sides (about 0.12 m): assumed masonry
FLOOR_B = 0.46            # COST 231 empirical floor exponent
ROUTER_H_M, CLIENT_H_M = 1.5, 1.0   # router on a shelf, laptop on a desk, above the floor

BANDS = {
    "2.4": {"label": "2.4 GHz", "mhz": 2437.0, "light": 3.4, "heavy": 6.9, "window": 2.0, "floor": 18.3},
    "5": {"label": "5 GHz", "mhz": 5500.0, "light": 5.0, "heavy": 11.0, "window": 3.0, "floor": 22.0},
}
# Materials the wall graph cannot tell from thickness, set by the person per wall or room. Assumed losses, dB per
# crossing (assumptions the result lists; low-E coated glass and sheet metal are far worse than they look).
MATERIALS = {
    "metal ductwork": {"2.4": 15.0, "5": 20.0},
    "coated glass": {"2.4": 25.0, "5": 30.0},
    "clear glass": {"2.4": 2.0, "5": 3.0},
    "masonry": {"2.4": 6.9, "5": 11.0},
    "drywall": {"2.4": 3.4, "5": 5.0},
}

# EIRP: a typical home router transmits near 20 dBm on 2.4 GHz and 23 dBm on 5 GHz; long-range models up to 4 dB more
ROUTERS = {"typical": {"2.4": 20.0, "5": 23.0}, "long_range": {"2.4": 24.0, "5": 27.0}}

# Received signal (dBm) a client needs. -67: video calls and voice (Cisco and Apple Wi-Fi design guidance);
# -72: streaming and browsing; -80: the floor for a stable connection. Below -80 is a dead zone.
GOOD, FAIR, WEAK = -67.0, -72.0, -80.0


def grade(dbm: float) -> str:
    return "good" if dbm >= GOOD else "fair" if dbm >= FAIR else "weak" if dbm >= WEAK else "dead"


def fspl_1m(mhz: float) -> float:
    return 20 * math.log10(mhz) - 27.55  # free-space path loss at 1 m, dB


@dataclass
class House:
    """The wall graph cut into per-floor wall pieces, floor heights and storey order, built once per plan."""
    plan: dict
    segs: dict[str, Segs] = field(default_factory=dict)
    z: dict[str, float] = field(default_factory=dict)
    storey: dict[str, int] = field(default_factory=dict)
    materials: dict[str, str] = field(default_factory=dict)  # wall id -> a MATERIALS key

    def __post_init__(self):
        self.z = floor_z(self.plan)
        self.storey = floor_order(self.plan)
        self.segs = {f: segments(self.plan, f) for f in self.z}

    def loss_per_piece(self, floor: str, band: str) -> np.ndarray:
        s, b = self.segs[floor], BANDS[band]
        out = np.where(s.kind == "window", b["window"], np.where(s.thickness >= HEAVY_WALL_M, b["heavy"], b["light"]))
        for i, w in enumerate(s.wall):
            if w in self.materials:
                out[i] = MATERIALS[self.materials[w]][band]
        return out

    def signal(self, src: tuple[float, float, str], pts: np.ndarray, floor: str, band: str, eirp: float) -> np.ndarray:
        """dBm at each point (on `floor`) from a router at src (x, y, floor)."""
        sx, sy, sf = src
        pts = np.asarray(pts, float).reshape(-1, 2)
        dz = (self.z[floor] + CLIENT_H_M) - (self.z[sf] + ROUTER_H_M)
        d = np.maximum(np.sqrt((pts[:, 0] - sx) ** 2 + (pts[:, 1] - sy) ** 2 + dz ** 2), 1.0)
        b = BANDS[band]
        loss = fspl_1m(b["mhz"]) + 20 * np.log10(d)
        if sf == floor:
            t = cross_t((sx, sy), pts, self.segs[floor])
            loss += (~np.isnan(t)) @ self.loss_per_piece(floor, band)
        else:  # the line climbs through the ceiling: walls on the router's floor near it, the client's near the client
            t_src = cross_t((sx, sy), pts, self.segs[sf])
            t_dst = cross_t((sx, sy), pts, self.segs[floor])
            loss += (t_src < 0.5).astype(float) @ self.loss_per_piece(sf, band)
            loss += (t_dst >= 0.5).astype(float) @ self.loss_per_piece(floor, band)
            nf = abs(self.storey[floor] - self.storey[sf])
            loss += nf ** ((nf + 2) / (nf + 1) - FLOOR_B) * b["floor"]
        return eirp - loss


def outbuilding(eirp: float, band: str, to_edge_m: float, gap_m: float, wall: str = "masonry") -> float:
    """dBm inside a detached building `gap_m` beyond the house wall nearest the router (`to_edge_m` away): free space
    over the whole distance, the house's outside wall (heavy) and the outbuilding's wall (`wall`, a MATERIALS key)."""
    b = BANDS[band]
    d = max(to_edge_m + gap_m + 1.0, 1.0)  # 1 m inside the outbuilding
    return eirp - (fspl_1m(b["mhz"]) + 20 * math.log10(d) + b["heavy"] + MATERIALS[wall][band])
