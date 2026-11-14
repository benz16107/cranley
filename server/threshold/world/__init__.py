"""The world around a scan: where the scan frame sits in east/north metres, Vexcel's 3D city mesh and surface
model for the surroundings, Matterport's own scanned mesh, and the drone splat's placement.

Everything is expressed about one anchor, `plan.geo` (lat, lon): east and north in metres, up in metres above the
ground at the building. The web scene (`web/src/world/`) turns that into the scan frame with `frame.scan_to_enu`.
"""
