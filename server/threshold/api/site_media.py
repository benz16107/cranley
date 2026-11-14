"""Media the site tools point at: oblique crops (evidence for dock doors) and printable sheets (risk_sheet).
Owned by the site tools workstream; app.py includes this router by itself."""
import re

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse

from ..aerial import site
from ..aerial.vexcel import VexcelError
from ..config import DATA

router = APIRouter(prefix="/api/site")
SHEETS = DATA / "media" / "sheets"


@router.get("/oblique")
def oblique(lat: float, lon: float, size_m: float = 120, direction: str = "oblique-north") -> Response:
    if direction not in site.OBLIQUES or not 20 <= size_m <= 400:
        raise HTTPException(400, f"direction must be one of {site.OBLIQUES} and size_m 20-400")
    try:
        ob = next((o for o in site.obliques(lat, lon, size_m) if o["direction"] == direction), None)
    except VexcelError as e:
        raise HTTPException(502, str(e)) from None
    if ob is None:
        raise HTTPException(404, f"No {direction} view over this point")
    return Response(ob["image"], media_type="image/jpeg", headers={
        "X-Capture": ob.get("capture_date") or "", "X-Shows-Face": ob["shows_face"],
        "Access-Control-Expose-Headers": "X-Capture, X-Shows-Face", "Cache-Control": "max-age=86400"})


@router.get("/sheet/{name}.html", response_class=HTMLResponse)
def sheet(name: str) -> HTMLResponse:
    if not re.fullmatch(r"[\w.,-]{1,80}", name):
        raise HTTPException(400, "bad sheet name")
    f = SHEETS / f"{name}.html"
    if not f.exists():
        raise HTTPException(404, "No such sheet; run the tool first")
    return HTMLResponse(f.read_text())
