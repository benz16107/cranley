---
title: Phone and iPhone app
description: A phone companion that pairs with a workspace by QR, and a native iPhone app that scans your own space with LiDAR.
---

A scan answers what was true on the day it was made. A person standing in the building can close what the scan left open. Cranley has two ways to do that.

## The phone companion

The phone companion is a web page at `/m`. It pairs with a desktop workspace and sends what the phone can sense.

1. On the desktop, open the workspace's Phone tab. It shows a QR code.
2. Scan the code with the phone. The page opens over HTTPS, because the camera, motion and location need a secure origin.
3. Do a task, or use an instrument. Each one sends one capture, and the result lands in the workspace the desktop is showing.

A door width typed on the phone reaches the desktop in about a second.

| Instrument | What it gives a tool |
|---|---|
| Measure | A length you measured and typed, such as a door's clear width |
| Photo measure | A length worked out from a photo |
| Level | The slope of a ramp or a floor, from the phone's tilt |
| Sound | The noise level in a room, from the microphone |
| Floor height | The height of the floor above the street, from the barometer or a count of steps |
| Window | Which way a window faces, from the compass |
| Where | Where you are, from GPS |
| Alarm | A photo of a ceiling for the smoke alarm census |
| Walk-through | A recorded pass through the rooms |
| Note | Words for the record |

Each capture is labelled with the layer `phone` and the method `sensor` or `manual`, so a result shows that a value came from the site and how. A phone reading can confirm the scan, contradict it, or be the first measurement.

The tools the phone feeds are in the tool reference: [field check](/docs/tools/field-check/), [photo measure](/docs/tools/photo-measure/), [slope check](/docs/tools/slope-check/), [noise level](/docs/tools/noise-level/), [floor height](/docs/tools/floor-height/), [window check](/docs/tools/window-check/), [where am I](/docs/tools/where-am-i/) and [walk-through](/docs/tools/walkthrough/). The routes are under [phone captures](/docs/reference/api/capture/) and [phone sensors](/docs/reference/api/sensors/).

## The iPhone app

The iPhone app is a SwiftUI app in `ios/Threshold`. Its name on the phone is Cranley.

- **Scan.** It scans a room or a whole floor with LiDAR, using Apple RoomPlan, and uploads the export to `POST /api/scans/user`. The server converts it to the same plan format as any other scan, so every geometry tool runs on a home or a shop that is in no dataset.
- **Measure.** A LiDAR tape measure, the barometer for the floor's height above the street, and the compass for a window's facing.
- **Site visit.** Pick a report (an accessibility audit, a fire safety pre-plan, or fit-out and occupancy), name the business, and the checks run on the scan. The result is a PDF with numbered fixes and a list of what was not checked.
- **Workspace.** Link the phone to a desktop workspace, so scans and measurements show up there.

### What a phone scan can and cannot tell

A RoomPlan scan measures walls, doors, windows and objects. Wall thickness is not measured, so 0.12 m is assumed. The scan has no panoramas, no mesh and no location. Tools that read photos or aerial imagery return `unknown` and say why. The app shows this under "What the scan cannot tell".

### State

The app builds and runs in the iOS simulator, with a demo mode that uses the two made-up test scans. It has not been installed on a phone yet.

### Build it

```sh
cd ios/Threshold
xcodegen
```

Then open the generated project in Xcode.

`ios/scripts/install.sh` covers installs over USB and through TestFlight.

## Reports

Any workspace can become a PDF site report: the plan with numbered fixes, the evidence, the occupant load from the measured floor area, the smoke alarm census, and what was not checked. The routes are under [reports](/docs/reference/api/report/).
