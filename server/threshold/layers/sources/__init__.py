"""More map layers, one module per outside source. Adding a layer is adding a file here: nothing else changes, and
the web layer list shows it under its group the next time it loads.

A source module exports two names:

    LAYERS: tuple[Layer, ...]      # `threshold.layers.catalog.Layer`, one entry per layer (the fields are below)
    FETCH:  dict[str, Callable]    # layer id -> fn(box, city) -> (features, truncated)

`box` is (west, south, east, north) in degrees and `city` is "hou" or "la". The function is called once for a whole
city (`scope="city"`) or once per map tile of `grid_z` (`scope="grid"`), and its answer is kept on disk, so it need
not cache. It returns GeoJSON features in WGS84 already tidied to what the map shows:

    properties.name      the feature's name, shown on hover (optional for lines and areas)
    properties.detail    one more line for the hover (optional)
    properties.level     0 to 5, for an area coloured by value: drawn on the look's six-step ramp (optional)

An entry (`Layer`):

    id, title            a short id (also the cache folder) and the name in the list
    group                one of catalog.GROUPS; an unknown group is listed after them
    shape                point | line | area | raster | readout
    scope                city | grid (served by this server from FETCH), tiles (an XYZ raster the browser loads
                         from `tiles`), client (drawn by the page from what it has)
    source, source_url   who publishes it, and where; `licence` and `attribution` when the source asks for a credit line
    confidence, note     high | medium | low, and what the layer is and leaves out: both are shown to the person
    data_date            the date the source gives for its data; without it the day our copy was fetched is shown
    cities               where it exists ("hou", "la")
    minzoom, maxzoom     the map zooms between which it is drawn; grid_z is the tile zoom one cached file covers
    extra                {"hue": "--tool-2"} a design token for its colour (else a neutral);
                         {"legend": {"title", "unit", "stops": [[level, label], ...]}} for an area coloured by level;
                         {"tile_maxzoom": 12} the finest zoom a raster's own tiles exist at

Everything starts switched off (`on=False`). Stay well under ten requests a second to any source and never loop over
a city tile by tile at import time: a layer is fetched when someone looks at it.
"""
from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

MORE: tuple = ()
FETCH: dict[str, Callable] = {}
for _m in pkgutil.iter_modules(__path__):
    _mod = importlib.import_module(f"{__name__}.{_m.name}")
    MORE += tuple(getattr(_mod, "LAYERS", ()))
    FETCH.update(getattr(_mod, "FETCH", {}))
