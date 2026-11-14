"""Phone captures: photos, short videos, audio clips and sensor readings a person takes on site, attached to a
workspace and optionally to a scan, room, opening or finding. A capture is evidence a tool can cite: Contract 3
`media` with `kind: "phone"` (ref is the capture id) and `source` with `layer: "phone"`.

store.py   files and their records under $THRESHOLD_DATA_DIR/captures/ (never in git), with size and type checks
pair.py    the short-lived token that lets a phone add captures to one workspace and nothing else
tasks.py   other tools' "measure on site" and "not seen" findings as phone tasks
apply.py   what a capture does when it arrives: the tool it feeds, the finding it updates
frames.py  still frames from a walk-through video
The routes are in threshold/api/capture.py; both the mobile web app (/m) and the native app use them."""
