"""Interior Gaussian splats trained from a scan's panoramas.

`dataset` turns every sweep into six pinhole cube-face views with exact poses (a COLMAP text model), `seed` starts
the points on Matterport's scanned mesh coloured from the sweeps, `train` runs Brush, `spz` packs the result for the
web. Everything is written under `$THRESHOLD_DATA_DIR/splat/<sid>/`; none of it goes in git.

Frames. Splat positions are the scan frame of the ScanPlan (metres, z up), with no axis change anywhere: the
COLMAP world is the scan frame, Brush keeps it, and the .spz is written from the .ply as is.
"""
from ..config import DATA

ROOT = DATA / "splat"
