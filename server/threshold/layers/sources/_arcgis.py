"""One ArcGIS service layer as a map layer: the entry plus a fetcher that keeps a name, a line of detail and the few
values a style reads. Shared by the per-source modules here; it exports no layers itself."""
from __future__ import annotations

from collections.abc import Callable

from ..catalog import Layer, arcgis


def layer(id: str, title: str, group: str, shape: str, url: str | list[str] | dict[str, str], *, fields: str = "",
          name: Callable[[dict], str] | str = "", detail: Callable[[dict], str] | None = None,
          props: Callable[[dict], dict] | None = None, offset: float | None = None, where: str = "1=1",
          scope: str = "grid", clip: bool = False, **entry) -> tuple[Layer, Callable]:
    """`url` is one service layer, several to merge, or {city: url} where each city has its own. `name` is a field, a fixed string
    or a function of the feature's attributes. `clip` cuts each shape to the tile, for services whose shapes span a
    county (a fire zone arrives whole in every tile it touches)."""
    def fetch(box, city):
        urls = [url.get(city)] if isinstance(url, dict) else url if isinstance(url, list) else [url]
        feats, cut = [], False
        for u in filter(None, urls):
            got, c = arcgis(u if u.endswith("/query") else u.rstrip("/") + "/query", box, fields, offset, where)
            feats, cut = feats + got, cut or c
        out = []
        for f in feats:
            if not f.get("geometry"):
                continue
            a = f.get("properties") or {}
            nm = name(a) if callable(name) else (str(a.get(name) or "").strip() if name in a else name)
            p = {"name": nm or title}
            if detail:
                p["detail"] = detail(a)
            if props:
                p |= props(a)
            g = _clipped(f["geometry"], box) if clip else f["geometry"]
            if g:
                out.append({"type": "Feature", "geometry": g, "properties": p})
        return out, cut
    cities = entry.pop("cities", tuple(url) if isinstance(url, dict) else ("hou", "la"))
    return Layer(id, title, group, shape, scope, cities=cities, **entry), fetch


def _clipped(geom: dict, box) -> dict | None:
    from shapely.geometry import box as bbox
    from shapely.geometry import mapping, shape
    g = shape(geom)
    if not g.is_valid:
        g = g.buffer(0)
    cut = g.intersection(bbox(*box))
    return None if cut.is_empty else mapping(cut)


def collect(*pairs: tuple[Layer, Callable]) -> tuple[tuple[Layer, ...], dict[str, Callable]]:
    return tuple(l for l, _ in pairs), {l.id: f for l, f in pairs}


def join(*parts) -> str:
    return ", ".join(str(p).strip() for p in parts if p not in (None, "") and str(p).strip())
