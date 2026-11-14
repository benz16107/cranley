"""Map layers for the world explorer: public data round the scanned buildings (flood zones, high-water marks,
emergency services, schools, transit, parcels, weather), each fetched from a free source with no key, cached on disk
under `$THRESHOLD_DATA_DIR/cache/layers/`, and served with its source and the date it was fetched.

`catalog.LAYERS` is the one list of what exists. The web layer list is drawn from it, so a source or a caveat is
written once, here.
"""
# The catalogue first, whatever is imported from this package. It pulls in `sources/` at its own end; were a source
# module imported before it, the catalogue would finish while `sources` was half loaded and miss its layers.
from . import catalog  # noqa: F401
