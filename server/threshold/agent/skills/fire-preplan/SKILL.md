---
name: fire-preplan
description: Pre-incident planning for a fire company or a community risk officer. Use when the person plans a response to a building, trains a crew on it, or checks bedrooms for smoke alarms and survivable air.
---
# Fire pre-plan

Order matters: the cheap geometry first, the slow model runs only where they change the plan.

1. `egress_routes` on each scan: the way out of every room, rooms with one way out, the hose stretch. Fast.
2. `door_widths` if the crew moves a stretcher or a hose line through the building.
3. `fire_preplan`: the one-page plan from the scan, the aerial photo and the record. Run it after egress so its
   panel binds the routes already found.
4. `smoke_clock` only for bedrooms with one way out, or when the person asks how long a room stays survivable. It
   runs NIST's CFAST smoke model and takes minutes per scan, so the person is asked to approve it first. Say which
   bedrooms made you ask.
5. `life_safety_census` reads every bedroom's ceiling panorama with the vision model to look for smoke alarms. It
   is also slow and asks for approval. Treat what it reports as leads to check on site, never as proof that an alarm
   is missing.

For a whole apartment property use the `property` subagent with `run_on_property` instead of one scan at a time.
Point the camera at a bedroom with one way out if there is one.
