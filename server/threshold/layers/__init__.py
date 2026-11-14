"""Map layers for the world explorer: public data round the scanned buildings (flood zones, high-water marks,
emergency services, schools, transit, parcels, weather), each fetched from a free source with no key, cached on disk
under `$THRESHOLD_DATA_DIR/cache/layers/`, and served with its source and the date it was fetched.

`catalog.LAYERS` is the one list of what exists. The web layer list is drawn from it, so a source or a caveat is
written once, here.
"""
