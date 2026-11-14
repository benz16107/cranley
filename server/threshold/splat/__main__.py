"""uv run python -m threshold.splat <sid> [--steps N] [--res PX] [--holdout K] [--skip-build] [--build-only]"""
import argparse
import json

from . import dataset, train

ap = argparse.ArgumentParser(prog="python -m threshold.splat", description="Train an interior splat for a scan.")
ap.add_argument("sid")
ap.add_argument("--res", type=int, default=1024, help="training face size in pixels")
ap.add_argument("--holdout", type=int, default=8, help="hold out every Kth sweep for scoring (0: train on all)")
ap.add_argument("--steps", type=int, default=10000)
ap.add_argument("--phases", type=int, default=1, help="Brush runs with a free-space carve after each")
ap.add_argument("--sh", type=int, default=2, help="SH degree")
ap.add_argument("--max-splats", type=int, default=1_500_000)
ap.add_argument("--skip-build", action="store_true", help="reuse the dataset already written")
ap.add_argument("--build-only", action="store_true")
a = ap.parse_args()
if not a.skip_build:
    print(json.dumps(dataset.build(a.sid, a.res, a.holdout)), flush=True)
if not a.build_only:
    s = train.run(a.sid, a.steps, a.sh, a.max_splats, a.phases)
    print(json.dumps({k: s[k] for k in ("splats", "files", "trainer")} | {"psnr": s["eval"]["psnr"]}, indent=1))
