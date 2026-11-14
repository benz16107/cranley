---
name: storm-prep
description: Getting a house or its owner ready for a flood or a hurricane. Use when the person mentions a storm, flood water, a hurricane, evacuation or moving belongings upstairs.
---
# Storm preparation

1. `flood_rehearsal` first: water depth per room as the level rises, which doors and windows go under. Level 0 is
   the lowest scanned floor, not the street; say so when the person asks about street flooding.
2. `floor_height` when a phone capture exists for the house: it narrows the floor's height above the ground, the
   largest uncertainty in the flood result.
3. `valuables_height` reads the panoramas of the rooms that flood to find belongings, appliances and outlets and how
   high each sits. It uses the vision model on many panoramas and asks for approval first.
4. `storm_plan` last: the ordered plan for the hours before the storm, built from the runs above.

Never state a water depth or a height yourself. The flood and storm panels show them; point to their finding ids.
