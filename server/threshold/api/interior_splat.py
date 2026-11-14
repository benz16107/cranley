"""Interior Gaussian splats trained from a scan's panoramas (threshold.splat). 404 until one has been trained.

GET /api/scan/{sid}/interior-splat            interior.spz (format=ply for the .ply), byte ranges supported
GET /api/scan/{sid}/interior-splat.json       sidecar: transform into the ScanPlan frame, sizes, trainer, held-out PSNR
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..sources.upstream import check
from ..splat import ROOT
from .data import _byte_range

router = APIRouter(prefix="/api")
CHUNK = 1 << 20


def _file(sid: str, name: str):
    try:
        check(sid, "sid")
    except LookupError as e:
        raise HTTPException(404, str(e))
    f = ROOT / sid / name
    if not f.is_file():
        raise HTTPException(404, "no interior splat for this scan yet")
    return f


@router.get("/scan/{sid}/interior-splat.json")
def interior_splat_json(sid: str) -> JSONResponse:
    return JSONResponse(json.loads(_file(sid, "interior.json").read_text()), headers={"Cache-Control": "no-cache"})


@router.api_route("/scan/{sid}/interior-splat", methods=["GET", "HEAD"])
def interior_splat(sid: str, request: Request, format: str = "spz") -> Response:
    if format not in ("spz", "ply"):
        raise HTTPException(400, "format is spz or ply")
    f = _file(sid, f"interior.{format}")
    total = f.stat().st_size
    heads = {"Accept-Ranges": "bytes", "Cache-Control": "no-cache", "Content-Type": "application/octet-stream",
             "Content-Disposition": f'inline; filename="{sid}-interior.{format}"'}
    try:
        span = _byte_range(request.headers.get("range"), total)
    except ValueError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
    start, end = span or (0, total - 1)
    heads["Content-Length"] = str(end - start + 1)
    if span:
        heads["Content-Range"] = f"bytes {start}-{end}/{total}"
    status = 206 if span else 200
    if request.method == "HEAD":
        return Response(status_code=status, headers=heads)

    def body():
        with open(f, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                b = fh.read(min(CHUNK, left))
                if not b:
                    return
                left -= len(b)
                yield b

    return StreamingResponse(body(), status_code=status, headers=heads)
