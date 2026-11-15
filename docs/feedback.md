# Feedback from real users, and what it changed

Each row is one thing a person told us, where it came from, and what we did with it: a change the scan can measure
(with the tool and commit), a line the result now shows under "Not in the scan", or a reason we skipped it.
Every new number comes from geometry on the scan, never from model text. Each change has a test on a small
hand-made plan in `server/tests/tools/`.

## A call with a disability rights organisation's president (NYC), call 14 Nov

She uses a powered wheelchair and also owns a travel chair. Her words are paraphrased here until she agrees to be
quoted.

| What she said (paraphrased) | What changed |
|---|---|
| Steps are the hard limit, not door width. She does not ask "is it accessible", she asks "are there any steps". | `step_free_route`: the verdict now opens with "Steps from the entrance:" and one answer per destination, and each destination gets a steps check before any width check (`steps.<room>`: the highest sill step measured, against ADA 303's 1/2 in). A step at the entrance door is named as such. Commits 80becdd, 1259b9e |
| Being told "accessible" by email or phone is unreliable; she arrives and finds a step. | `step_free_route`, `bathroom_clearance`: a "Not in the scan" line says the ADA has no certification or inspection, so "accessible" is the owner's word. 80becdd, 1690b38 |
| Steps inside, a few metres past an accessible front door (a bookstore where she got in but could not reach the books). | `step_free_route`: every doorway sill on the route is measured, and a step, stair or ramp the panorama reader sees in a room the route passes through now counts against that route (it turns a pass into "measure on site"), not only as a pin. 80becdd |
| In NYC apartment buildings, lobby steps between the desk and the elevators. | Not in the scan (an apartment unit scan starts at the unit door): `step_free_route` says so and points to `curb_to_door`. 80becdd |
| Many people own more than one chair and do not know their widths; her travel chair is narrower. | New preference `access.chairs` (each chair: name, door width it needs, turning circle). `step_free_route` routes each chair and lists which rooms each one reaches; `bathroom_clearance` checks each chair at the bathroom door and turning circle; `turning_space` checks each chair's circle. A chair with no size uses the person's default. The profile shows each chair. 80becdd, 87a0f05, 4d36cd6 |
| A stall door that opens in usually blocks the chair. | `bathroom_clearance`: a check per bathroom door on which way it opens: from the scan if it records it, else read from the panorama (a label, not a size), else "not in the scan" with low reliability. Opening in with no 30 x 48 in space clear of the swing fails. 1690b38 |
| A big bin next to the toilet made an accessible stall unusable; front versus side transfer needs clear floor in front of or beside the toilet. | `bathroom_clearance`: clear floor in front of the toilet (30 in strip, needs 48 in) and beside it (48 in deep, needs 30 in), measured from the wall behind the toilet, with objects a phone scan measured (bins, storage, vanities) taken out of the floor and named when they are in the way. The toilet's own position comes from the phone scan when it measured one. On wall-graph scans, which record no objects, a line says every clear space is the most there can be. 1690b38 |
| Toilet height and grab bars matter. | Grab bar wall space was already checked. Toilet seat height and whether walls can hold bars are now a "Not in the scan" line. 1690b38 |
| Small stores with one narrow aisle and boxes on the floor, nowhere to turn around. | `turning_space`: on scans with measured objects, the turning circle is fitted to the floor less the objects, and a new aisle check gives the widest body that can get from the doorway to the turning spot between them (against ADA 403.5.1's 36 in). Boxes or stock left out on the day are a "Not in the scan" line. 1baf92b |
| A bookstore's elevator was out, so a floor was out of reach; pharmacies on other floors. | `step_free_route`: a room on another floor reads "elevator only" when the scan has a room labelled elevator or lift, otherwise "stairs only, no elevator in the scan"; a new check lists the rooms on the entrance floor reached with no step at any doorway, the ones that need a step, and the other floors. Whether the elevator is in service is a "Not in the scan" line. 80becdd |
| Temporary obstructions: cardboard bales, cleaning supplies kept in elevators, fitting rooms used for storage. | "Not in the scan" line in `step_free_route` and `turning_space`. 80becdd, 1baf92b |
| A platform gap works like a step. | Skipped: the scans are buildings, not transit platforms. |
| Door width matters more outside NYC. | No change: `door_widths` and `step_free_route` already measure every doorway. |
| Needs change over time (she could not walk for three months after foot surgery). | No change: every size is an editable preference, so a person can change it. |

## Reddit answers (quoted by handle)

| Quote | Source | What changed |
|---|---|---|
| Subdivision garages after 1999 are often 19.5 to 20 ft deep, "some less than 20 based on HVAC fittings in the walls"; a 2015 F-150 SuperCrew 5.5 ft bed does not fit. | r/f150, u/WhtHppnd2Brndn | `garage_fit`: depth from the door line to the back wall is its own check, measured clear of objects a phone scan found (shelves, fittings), against the vehicle length plus room for the door and to walk round. On wall-graph scans a "Not in the scan" line names water heaters, furnaces, HVAC fittings and steps into the house. Test: an F-150 in a 6.1 m (20 ft) garage is tight on depth, and fails with 0.3 m of fittings along the back wall. The catalog keeps the maker's published 5.89 m for a recent model year; the comment's "just over 20 ft" is not used as a number. 56a9a1c |
| A Yamaha 212X fit a 24 ft garage "only 1/4 in under the top of the opening with the tower flat". Measure the door opening, not the ceiling. | r/boating, u/SubjectMatter | Already separate before this branch: `garage_fit` checks headroom under the door opening and the ceiling as two checks. New test: a 2.40 m boat under a 2.44 m opening is tight while the 2.9 m ceiling passes. 56a9a1c |
| Use the maker's "storage length" (motor trimmed, tongue swung), not overall length. | r/boating, u/bri_c3p | `garage_fit`: new input `storage_length_m` (preference `garage.storage_length_m`) replaces the overall length and is shown as an editable assumption. 56a9a1c |
| An 8 ft trailer's side lights won't fit a one-car door. | r/boating, u/danielt1263 | `garage_fit`: for trailers and boats the door check is at the widest point, "fenders and side lights", and the assumption is labelled that way. Test: an 8 ft trailer fails an 8 ft door. 56a9a1c |
| Garage built around the boat: 24 x 25 ft, 9.5 ft ceiling, 18 x 8 ft doors front and rear. | r/boating, u/jljue | Used as a test plan for `garage_fit`: a 20 ft bowrider is tight on depth at its overall length and passes at a 6.4 m storage length. The verdict for boats no longer talks about squeezing out of doors. 56a9a1c |
| Cart, hand truck and rolling rack access and egress. | r/Chefit, u/DaRealBangoSkank (chef) | `facility_audit`: carries a loaded rack (default a full-size sheet-pan rack, 20 x 26 x 70 in, editable as `facility.cart_m`) from the main entrance to every storage room and kitchen, with each door's margin and the route's bends. a2a5552 |
| Dry storage, cooler and freezer space. | same | `facility_audit`: storage room floor area is a metric. Walk-in cooler and freezer capacity is a "Not in the scan" line unless those rooms are labelled storage. a2a5552 |
| 3-phase power; filtration for the ice machine and steamer. | same | "Not in the scan" lines in `facility_audit`. a2a5552 |
| Prep and plating space. | same | Skipped: it depends on the equipment layout, which no scan records. |
| "My old store unloaded at a 90 degree angle. Stuff fell off the corner constantly." | r/walmart, u/leelee1976 (receiving) | `facility_audit`: each cart route reports its bends, the total turning and the sharpest bend, as measured on the route (the route engine cuts a hallway's right angle into two bends, so we report the angles rather than count "90 degree" turns). The route starts at the main entrance, which may not be the receiving door. a2a5552 |
| Hot water didn't reach the sinks: too far from the water heater. | r/restaurant, u/South_Repair1596 (operator) | `facility_audit`: the straight-line distance from the water heater to the farthest sink, both located by the panorama reader, against IPC 2021 607.2's 50 ft (15.2 m) before hot water must be kept hot. The straight line is the least the pipe can be. When no water heater is seen, a "Not in the scan" line says so. a2a5552 |
| Soundproofing for service noise. | same | "Not in the scan" line in `facility_audit` and `office_fit`. a2a5552, 1319b46 |
| "Make sure the office is not beneath a bathroom." | r/AskManagers, u/False-Blacksmith2919 | `office_fit`: on multi-floor scans, offices, meeting rooms and reception with a restroom over at least 0.5 m² of them on the floor above. On one-floor scans a "Not in the scan" line says what is above cannot be ruled out. 1319b46 |

## Notes for the lead

- `openings[].swing` ("in" or "out") is read when present. No source fills it today (Matterport and RoomPlan
  record no swing), so the panorama reader answers. Adding it to Contract 1 would let a phone capture task fill it.
- `access.chairs` is a list of objects. The composer only asks numeric questions, so the list comes from a
  `pref.set` (or a future form). It does not ask "how many chairs do you have".
- The vision reader's `find_objects` cache key ignores the label list, and its labels have no bin or trash can, so
  bins are counted only from phone scans. A "trash can" label (perception's lane) would let wall-graph scans count
  them.
- The "Not in the scan" lines are checks with status `unknown` and ids starting `cannot.`. They do not change a
  verdict. A renderer may want to group them.
- `tests/report/test_report.py` (report's lane) now expects three fails on the test cafe instead of two:
  `bathroom_clearance` uses the toilet the phone scan measured, which sits 1.1 m from the side wall, so there is
  no wall for a grab bar.
