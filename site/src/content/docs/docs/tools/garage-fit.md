---
title: "Garage fit"
description: "Checks whether your car, truck, van or trailer fits in a scanned garage: how many side by side, the room to open doors, headroom for a lift or roof box, and room for a bench or charger."
sidebar: {"label": "Garage fit"}
---

Checks whether your car, truck, van or trailer fits in a scanned garage: how many side by side, the room to open doors, headroom for a lift or roof box, and room for a bench or charger.

## What it answers

- Will my F-150 fit in this garage?
- Can I park two cars and still have a workbench?
- Houses in Houston whose garage fits two F-150s
- Is there headroom for my lifted Jeep with a roof box?

For the agent, the tool is described as: Park a vehicle (about 60 common models from a built-in table, or custom sizes) in the garage of one scan: finds the garage (room label, or a ground-floor room with a car-wide door), measures its door width and height, inside width, depth and ceiling, and answers fits / tight / does not fit, how many fit side by side, clearance on each side and in front, headroom for a lifted truck or roof box, and room for a workbench, EV charger, motorcycle, bikes or a squat rack. Draws the vehicles parked as boxes. With search_city, searches every scanned house in Houston or Los Angeles for a garage that fits `count` of the vehicle.

## Who it is for

[Car owner checking a garage](/docs/reference/personas/#car-owner-checking-a-garage), [Home gym in the garage](/docs/reference/personas/#home-gym-in-the-garage), [RV or boat owner](/docs/reference/personas/#rv-or-boat-owner), [Wheelchair van owner](/docs/reference/personas/#wheelchair-van-owner).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id (leave empty with search_city). Filled from the selected building. |
| `vehicle` | string |  | `"ford_f150"` | A vehicle from the built-in table; its sizes are editable assumptions. Asked as: "Which vehicle? ford_f150: Ford F-150 SuperCrew, 5.5 ft bed; ford_f150_long: Ford F-150 SuperCrew, 6.5 ft bed; ford_f150_lightning: Ford F-150 Lightning; ford_f250: Ford F-250 Super Duty Crew Cab; chevy_silverado: Chevrolet Silverado 1500 Crew Cab; gmc_sierra: GMC Sierra 1500 Crew Cab; ram_1500: Ram 1500 Crew Cab, 5.7 ft bed; toyota_tundra: Toyota Tundra CrewMax; toyota_tacoma: Toyota Tacoma Double Cab; ford_ranger: Ford Ranger SuperCrew; ford_maverick: Ford Maverick; honda_ridgeline: Honda Ridgeline; rivian_r1t: Rivian R1T; tesla_cybertruck: Tesla Cybertruck; chevy_suburban: Chevrolet Suburban; chevy_tahoe: Chevrolet Tahoe; cadillac_escalade: Cadillac Escalade; ford_expedition: Ford Expedition; ford_explorer: Ford Explorer; jeep_grand_cherokee: Jeep Grand Cherokee; jeep_wrangler: Jeep Wrangler Unlimited; toyota_4runner: Toyota 4Runner; toyota_highlander: Toyota Highlander; toyota_rav4: Toyota RAV4; honda_crv: Honda CR-V; kia_telluride: Kia Telluride; tesla_model_y: Tesla Model Y; rivian_r1s: Rivian R1S; land_rover_defender: Land Rover Defender 110; subaru_outback: Subaru Outback; tesla_model_3: Tesla Model 3; toyota_camry: Toyota Camry; toyota_corolla: Toyota Corolla; honda_civic: Honda Civic sedan; honda_accord: Honda Accord; bmw_3: BMW 3 Series; mini_cooper: Mini Cooper hardtop; ford_mustang: Ford Mustang coupe; chevy_corvette: Chevrolet Corvette; porsche_911: Porsche 911; mazda_mx5: Mazda MX-5 Miata; honda_odyssey: Honda Odyssey; toyota_sienna: Toyota Sienna; chrysler_pacifica: Chrysler Pacifica; wheelchair_van: Side-entry wheelchair van (Sienna or Pacifica conversion); ford_transit_low: Ford Transit 130 in low roof; sprinter_high: Mercedes Sprinter 144 in high roof; motorcycle_touring: Touring motorcycle (Harley Road Glide); motorcycle_sport: Sport motorcycle; golf_cart: Golf cart; utility_trailer: Utility trailer, 5 x 10 ft, with tongue; teardrop_trailer: Teardrop camper trailer; boat_20ft: 20 ft bowrider on its trailer; jet_ski: Jet ski on its trailer; travel_trailer_25ft: 25 ft travel trailer; class_b_rv: Class B camper van (Sprinter 144 in 4x4); class_c_rv: Class C motorhome, 24 ft; class_a_rv: Class A motorhome, 35 ft" Saved preference `garage.vehicle`. One of: `ford_f150`, `ford_f150_long`, `ford_f150_lightning`, `ford_f250`, `chevy_silverado`, `gmc_sierra`, `ram_1500`, `toyota_tundra`, `toyota_tacoma`, `ford_ranger`, `ford_maverick`, `honda_ridgeline`, `rivian_r1t`, `tesla_cybertruck`, `chevy_suburban`, `chevy_tahoe`, `cadillac_escalade`, `ford_expedition`, `ford_explorer`, `jeep_grand_cherokee`, `jeep_wrangler`, `toyota_4runner`, `toyota_highlander`, `toyota_rav4`, `honda_crv`, `kia_telluride`, `tesla_model_y`, `rivian_r1s`, `land_rover_defender`, `subaru_outback`, `tesla_model_3`, `toyota_camry`, `toyota_corolla`, `honda_civic`, `honda_accord`, `bmw_3`, `mini_cooper`, `ford_mustang`, `chevy_corvette`, `porsche_911`, `mazda_mx5`, `honda_odyssey`, `toyota_sienna`, `chrysler_pacifica`, `wheelchair_van`, `ford_transit_low`, `sprinter_high`, `motorcycle_touring`, `motorcycle_sport`, `golf_cart`, `utility_trailer`, `teardrop_trailer`, `boat_20ft`, `jet_ski`, `travel_trailer_25ft`, `class_b_rv`, `class_c_rv`, `class_a_rv`. |
| `second_vehicle` | string |  |  | A second, different vehicle to park beside the first (an F-150 and a Highlander); checks both, each with its own doors. Saved preference `garage.second_vehicle`. |
| `count` | integer |  |  | How many of the vehicle must fit side by side; empty for as many as fit, 0 for none (an empty garage for a gym or workshop). Saved preference `garage.count`. |
| `length_m` | number (m) |  |  | Custom length. Saved preference `garage.length_m`. |
| `storage_length_m` | number (m) |  |  | Boats and trailers: the maker's storage length (motor trimmed up, tongue swung or off), used instead of the overall length. Saved preference `garage.storage_length_m`. |
| `width_m` | number (m) |  |  | Custom body width, mirrors folded. Saved preference `garage.width_m`. |
| `mirror_width_m` | number (m) |  |  | Custom width with mirrors out. Saved preference `garage.mirror_width_m`. |
| `height_m` | number (m) |  |  | Custom height. Saved preference `garage.height_m`. |
| `lift_in` | number (in) |  | `0` | Suspension lift plus bigger tyres, inches added to the height. Saved preference `garage.lift_in`. Range: at least 0, at most 12. |
| `roof_load_m` | number (m) |  | `0` | Roof box, rack or bikes: metres above the roof (a cargo box is about 0.45). Saved preference `garage.roof_load_m`. Range: at least 0, at most 1.5. |
| `uses` | array |  | `["workbench", "ev_charger"]` | Also find room for: workbench, ev_charger, motorcycle, bikes, squat_rack (home gym: an 8 x 8 ft platform and overhead-press headroom). Saved preference `garage.uses`. |
| `charge_cord_m` | number (m) |  | `6.1` | Charging cord length, for the outlet's distance (20 ft is common). Saved preference `garage.charge_cord_m`. Range: more than 0.5, at most 30. |
| `lifter_height_m` | number (m) |  | `1.78` | Height of the person pressing overhead, for the home gym check. Saved preference `garage.lifter_height_m`. Range: more than 1.2, at most 2.2. |
| `room` | string |  |  | Room id of the garage, if not the one found. |
| `which_fit` | boolean |  | `false` | Turn it round: try every vehicle in the table in this garage and list the ones that fit, with the room to spare. |
| `search_city` | string |  |  | Search every scanned house in this city for a garage that fits `count` of the vehicle (default two) instead of checking one scan. |
| `limit` | integer |  | `20` | Search: homes to return. Range: at least 1, at most 100. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a box or 3D model placed in the room; doors, walls or rooms coloured by status.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `RankedTable`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: fast. Read-only.

## How it works

Garage fit: does a vehicle fit in this garage? The garage is found from room labels or a ground-floor room with a car-wide door; its door, inside width, depth and ceiling come from the wall graph; the vehicle comes from a table of common models or custom sizes. Answers fits / tight / does not fit, how many fit side by side, the room on each side to open doors and walk round, headroom under the door for a lift or a roof box, and room left for a bench, a charger, a motorcycle or a rack. The vehicles are drawn parked as Contract 4 boxes, coloured by their clearance. With `search_city` it searches every scanned house in a city instead (search.py).

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: wall outline, rooms. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `vehicle = "ford_f150"` (preset of the persona "Car owner checking a garage"); `uses = ["workbench", "ev_charger"]` (preset of the persona "Car owner checking a garage").

<p class="verdict"><span class="st unknown">Unknown</span> This scan has no garage: no room is labelled Garage or Carport, and no ground-floor room has a door wide enough for a car. The aerial photos could not be checked: Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found.</p>


## Run it

```sh
threshold run garage_fit --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/garage_fit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `garage_fit`. See [MCP server and CLI](/docs/mcp/).
