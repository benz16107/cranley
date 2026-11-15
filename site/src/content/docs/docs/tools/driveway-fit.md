---
title: "Driveway fit"
description: "Estimates the driveway's length and width from the aerial photo, how many cars park on it, and whether a trailer, RV or boat fits off the street."
sidebar: {"label": "Driveway fit"}
---

Estimates the driveway's length and width from the aerial photo, how many cars park on it, and whether a trailer, RV or boat fits off the street.

## What it answers

- How many cars fit on the driveway?
- Can I park my boat trailer off the street here?

For the agent, the tool is described as: For any house in Houston or Los Angeles (a scan, or a point): driveway length from the garage door or house to the parcel line, paved width on the orthophoto, how many cars park on it (5.2 x 2.5 m each), and whether a long vehicle from the garage_fit table (trailer, boat, RV, truck) fits on it without sticking into the sidewalk. Aerial estimates, labelled medium or low.

## Who it is for

[Car owner checking a garage](/docs/reference/personas/#car-owner-checking-a-garage), [RV or boat owner](/docs/reference/personas/#rv-or-boat-owner), [Wheelchair van owner](/docs/reference/personas/#wheelchair-van-owner).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `vehicle` | string |  | `"boat_20ft"` | A vehicle that must park on the driveway, off the street (trailer, RV, boat, truck). Asked as: "What long vehicle must fit off the street? ford_f150: Ford F-150 SuperCrew, 5.5 ft bed; ford_f150_long: Ford F-150 SuperCrew, 6.5 ft bed; ford_f150_lightning: Ford F-150 Lightning; ford_f250: Ford F-250 Super Duty Crew Cab; chevy_silverado: Chevrolet Silverado 1500 Crew Cab; gmc_sierra: GMC Sierra 1500 Crew Cab; ram_1500: Ram 1500 Crew Cab, 5.7 ft bed; toyota_tundra: Toyota Tundra CrewMax; toyota_tacoma: Toyota Tacoma Double Cab; ford_ranger: Ford Ranger SuperCrew; ford_maverick: Ford Maverick; honda_ridgeline: Honda Ridgeline; rivian_r1t: Rivian R1T; tesla_cybertruck: Tesla Cybertruck; chevy_suburban: Chevrolet Suburban; chevy_tahoe: Chevrolet Tahoe; cadillac_escalade: Cadillac Escalade; ford_expedition: Ford Expedition; ford_explorer: Ford Explorer; jeep_grand_cherokee: Jeep Grand Cherokee; jeep_wrangler: Jeep Wrangler Unlimited; toyota_4runner: Toyota 4Runner; toyota_highlander: Toyota Highlander; toyota_rav4: Toyota RAV4; honda_crv: Honda CR-V; kia_telluride: Kia Telluride; tesla_model_y: Tesla Model Y; rivian_r1s: Rivian R1S; land_rover_defender: Land Rover Defender 110; subaru_outback: Subaru Outback; tesla_model_3: Tesla Model 3; toyota_camry: Toyota Camry; toyota_corolla: Toyota Corolla; honda_civic: Honda Civic sedan; honda_accord: Honda Accord; bmw_3: BMW 3 Series; mini_cooper: Mini Cooper hardtop; ford_mustang: Ford Mustang coupe; chevy_corvette: Chevrolet Corvette; porsche_911: Porsche 911; mazda_mx5: Mazda MX-5 Miata; honda_odyssey: Honda Odyssey; toyota_sienna: Toyota Sienna; chrysler_pacifica: Chrysler Pacifica; wheelchair_van: Side-entry wheelchair van (Sienna or Pacifica conversion); ford_transit_low: Ford Transit 130 in low roof; sprinter_high: Mercedes Sprinter 144 in high roof; motorcycle_touring: Touring motorcycle (Harley Road Glide); motorcycle_sport: Sport motorcycle; golf_cart: Golf cart; utility_trailer: Utility trailer, 5 x 10 ft, with tongue; teardrop_trailer: Teardrop camper trailer; boat_20ft: 20 ft bowrider on its trailer; jet_ski: Jet ski on its trailer; travel_trailer_25ft: 25 ft travel trailer; class_b_rv: Class B camper van (Sprinter 144 in 4x4); class_c_rv: Class C motorhome, 24 ft; class_a_rv: Class A motorhome, 35 ft" Saved preference `driveway.vehicle`. One of: `ford_f150`, `ford_f150_long`, `ford_f150_lightning`, `ford_f250`, `chevy_silverado`, `gmc_sierra`, `ram_1500`, `toyota_tundra`, `toyota_tacoma`, `ford_ranger`, `ford_maverick`, `honda_ridgeline`, `rivian_r1t`, `tesla_cybertruck`, `chevy_suburban`, `chevy_tahoe`, `cadillac_escalade`, `ford_expedition`, `ford_explorer`, `jeep_grand_cherokee`, `jeep_wrangler`, `toyota_4runner`, `toyota_highlander`, `toyota_rav4`, `honda_crv`, `kia_telluride`, `tesla_model_y`, `rivian_r1s`, `land_rover_defender`, `subaru_outback`, `tesla_model_3`, `toyota_camry`, `toyota_corolla`, `honda_civic`, `honda_accord`, `bmw_3`, `mini_cooper`, `ford_mustang`, `chevy_corvette`, `porsche_911`, `mazda_mx5`, `honda_odyssey`, `toyota_sienna`, `chrysler_pacifica`, `wheelchair_van`, `ford_transit_low`, `sprinter_high`, `motorcycle_touring`, `motorcycle_sport`, `golf_cart`, `utility_trailer`, `teardrop_trailer`, `boat_20ft`, `jet_ski`, `travel_trailer_25ft`, `class_b_rv`, `class_c_rv`, `class_a_rv`. |
| `length_m` | number (m) |  |  | Custom vehicle length, with tongue or hitch. Saved preference `driveway.length_m`. |
| `width_m` | number (m) |  |  | Custom width. Saved preference `driveway.width_m`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Aerial photo | `vexcel.ortho` | required | The verdict is `unknown`, with the reason. |
| Aerial property facts | `vexcel.property` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found; a route with its narrow points; a box or 3D model placed in the room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Driveway fit: how long and wide the driveway is, how many cars park on it, and whether a long vehicle (trailer, RV, boat) fits off the street. From above: Vexcel's detector boxes the driveway, the parcel line ends it at the street, and the orthophoto's paved colour gives its width at stations along it. With a scan whose garage door was recorded, the driveway starts at that door and runs out from it; otherwise it runs from the house toward the driveway box. Aerial estimates: medium for length (parcel lines and the scan's placement are good to a couple of metres), low for width (colour edges, shade and parked cars).

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: aerial photo, aerial property facts. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run driveway_fit --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/driveway_fit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `driveway_fit`. See [MCP server and CLI](/docs/mcp/).
