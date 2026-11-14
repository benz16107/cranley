---
name: step-free-home
description: Checking whether a home works for a wheelchair, a walker or an older person, or finding homes that do. Use when the person names a wheelchair, mobility aid, turning circle, stairs or an ageing parent.
---
# Step-free home

Finding candidates: with no buildings given, prefer `find_by_measure` (bathroom route door width, turning space,
step-free bathroom) over words in a listing. `consider` reports whether each new scan has doorways; a scan without
doorways cannot answer a door question, so swap it.

Per home, in this order:
1. `door_widths`, then `step_free_route` from the entrance to the rooms the person needs (bathroom, bedroom,
   kitchen). The route's narrowest door is usually the answer.
2. `turning_space`, then `bathroom_clearance` for the bathroom on the route.
3. `curb_to_door` only when the person asks about getting in from the street; it reads the aerial photo.

The person's chair width and turning circle come from their answers; never assume one. A door the plan marks as
implausible is a data error to check on site, not a pass or a fail.
