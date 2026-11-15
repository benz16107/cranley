---
title: "Personas"
description: "The 50 persona presets, their tools and thresholds."
---

A persona is a preset: who the person is, the tools that fit their need, and thresholds that fill tool inputs. There are 50. The composer uses them as starting points; a free sentence works too. Generated from `server/threshold/agent/personas/`.

## Planning for an older parent

Is checking whether a home is safe for an older parent to live in: trips, stairs, the night path to the bathroom, grab bars, and whether paramedics could reach them.

Tools: [Aging in place](/docs/tools/aging-in-place/), [Stairs](/docs/tools/stairs-count/), [Step-free route](/docs/tools/step-free-route/), [Bathroom clearance](/docs/tools/bathroom-clearance/), [Stretcher route](/docs/tools/stretcher-route/), [Curb to door](/docs/tools/curb-to-door/).

Presets: `access.door_width_m = 0.815`, `access.riser_m = 0.178`.

## Amenity auditor

Checks what an apartment community really offers against its listing, unit by unit and amenity by amenity.

Tools: [Amenity census](/docs/tools/amenity-census/), [Unit compare](/docs/tools/unit-compare/), [Storage space](/docs/tools/storage-space/), [Room labeller](/docs/tools/room-labeller/).

## Apartment manager

Runs a building and compares units, accessibility and what the listing claims.

Tools: [Room census](/docs/tools/room-census/), [Door widths](/docs/tools/door-widths/), [Property coverage](/docs/tools/property-coverage/), [Unit compare](/docs/tools/unit-compare/), [Record versus reality](/docs/tools/record-vs-reality/).

Presets: `access.door_width_m = 0.813`.

## Business checking a site

Wants to open or move a business and needs to know whether the use is allowed, what was permitted there, who lives around it and how people get there.

Tools: [Zoning check](/docs/tools/zoning-check/), [Permit history](/docs/tools/permit-history/), [Area profile](/docs/tools/area-profile/), [Connectivity](/docs/tools/connectivity/).

## Car owner checking a garage

Wants to know whether their car or truck fits in the garage, with room to open the doors, and how many cars the driveway holds.

Tools: [Garage fit](/docs/tools/garage-fit/), [Driveway fit](/docs/tools/driveway-fit/), [Measure search](/docs/tools/measure-search/).

Presets: `garage.vehicle = "ford_f150"`, `garage.uses = ["workbench", "ev_charger"]`, `driveway.vehicle = "ford_f150"`.

## Cat owner in an apartment

Rents an apartment with an indoor cat: the community's pet policy and fees, windows and a balcony a cat could fall from, a litter box spot away from the kitchen, and a vet nearby.

Tools: [Pet fit](/docs/tools/pet-fit/), [Nearby](/docs/tools/nearby/), [Home search for pets and kids](/docs/tools/home-search/), [Amenity census](/docs/tools/amenity-census/).

Presets: `pets.profile = [{"kind": "cat", "outdoor": false}]`, `nearby.profile = "pets"`, `search.kind = "apartment_unit"`, `pets.cat = "indoor"`.

## Commercial cleaning bidder

Prices janitorial work from a scan: cleanable area by floor finish, restroom fixtures, glass, hours per visit.

Tools: [Takeoff bid](/docs/tools/takeoff-bid/), [Room labeller](/docs/tools/room-labeller/), [Room census](/docs/tools/room-census/).

Presets: `bid.trade = "cleaning"`, `bid.clean.visits = 3`.

## Commercial property underwriter

Prices a warehouse, an office, a shop or an apartment community: roof, flood position, what is on site against the record, and rent and sale price against comps.

Tools: [Risk sheet](/docs/tools/risk-sheet/), [Market comps](/docs/tools/market-comps/), [Industrial fit](/docs/tools/industrial-fit/), [Roof facts](/docs/tools/roof-facts/), [Loading docks](/docs/tools/loading-docks/), [Parking count](/docs/tools/parking-count/).

## Community risk reduction officer

Finds homes and units where smoke alarms are missing, and shows what a closed bedroom door buys.

Tools: [Smoke alarm census](/docs/tools/life-safety-census/), [Smoke clock](/docs/tools/smoke-clock/), [Fire pre-plan](/docs/tools/fire-preplan/), [Egress routes](/docs/tools/egress-routes/).

Presets: `fire.growth = "fast"`, `fire.escape_min = 3`.

## CoStar research lead

Decides which record fields to fix or add across a portfolio, from where records and scans disagree.

Tools: [Field audit](/docs/tools/field-audit/), [Record versus reality](/docs/tools/record-vs-reality/), [Derived fields](/docs/tools/derived-fields/), [Room census](/docs/tools/room-census/).

## CoStar researcher

Checks and enriches property records: room types, areas, what changed since the record.

Tools: [Record versus reality](/docs/tools/record-vs-reality/), [Room census](/docs/tools/room-census/), [Room labeller](/docs/tools/room-labeller/).

## Daycare operator

Looking for a building to license as a child-care centre and needs the capacity inside and out.

Tools: [Daycare capacity](/docs/tools/daycare-capacity/), [Door widths](/docs/tools/door-widths/), [Room census](/docs/tools/room-census/), [Path to water](/docs/tools/path-to-water/).

Presets: `access.door_width_m = 0.815`, `access.door_standard = "ADA 2010 \u00a7404.2.3, 32 in clear (strollers and evacuation cribs)"`.

## Dog owner choosing a home

Is choosing a home for a dog: a fenced, flat yard with shade, no unfenced pool, a pet door to the yard, room for a crate, a dog park and a vet nearby.

Tools: [Pet fit](/docs/tools/pet-fit/), [Nearby](/docs/tools/nearby/), [Home search for pets and kids](/docs/tools/home-search/), [Path to water](/docs/tools/path-to-water/), [Tour](/docs/tools/tour/).

Presets: `pets.profile = [{"kind": "dog", "weight_lb": 60, "age": "adult"}]`, `nearby.profile = "pets"`, `pets.dog_lb = 60`.

## Emergency manager or caseworker before a storm

Has a storm coming and a household to advise: how deep the water gets inside, what to move first, and what the people there can finish in the hours left.

Tools: [Storm plan](/docs/tools/storm-plan/), [Flood rehearsal](/docs/tools/flood-rehearsal/), [What sits below the water](/docs/tools/valuables-height/).

## Facility manager

Audits the building the business already occupies: access, ways out, life safety, cleaning and what to fix first.

Tools: [Facility audit](/docs/tools/facility-audit/), [Door widths](/docs/tools/door-widths/), [Egress routes](/docs/tools/egress-routes/), [Bathroom clearance](/docs/tools/bathroom-clearance/), [Takeoff bid](/docs/tools/takeoff-bid/).

Presets: `access.door_width_m = 0.813`, `bid.trade = "cleaning"`.

## Family checking a neighbourhood

Is choosing a home and wants every hazard at the address (flood, fire, earthquake, heat, noise) and what the neighbourhood is like.

Tools: [Hazard profile](/docs/tools/hazard-profile/), [Area profile](/docs/tools/area-profile/), [Connectivity](/docs/tools/connectivity/), [Permit history](/docs/tools/permit-history/).

## Arranging a home by feng shui

Wants a home read the way a feng shui practitioner would: the front door's direction, the Bagua sectors, where the bed and desk go, and their own favourable directions.

Tools: [Feng shui reading](/docs/tools/feng-shui/), [Room sizes](/docs/tools/room-sizes/), [Furniture fit](/docs/tools/furniture-fit/).

## Fire captain

Pre-plans a building: entries, egress widths, hazards, standpipes and the route in.

Tools: [Fire pre-plan](/docs/tools/fire-preplan/), [Egress routes](/docs/tools/egress-routes/), [Door widths](/docs/tools/door-widths/), [Room census](/docs/tools/room-census/), [Tour](/docs/tools/tour/).

Presets: `access.door_width_m = 0.813`, `access.door_standard = "IBC 2021 \u00a71010.1.1, 32 in clear egress"`.

## Fire training officer

Runs size-up drills on real houses and grades crews against the measured interior.

Tools: [Size-up quiz](/docs/tools/size-up-quiz/), [Egress routes](/docs/tools/egress-routes/), [Smoke clock](/docs/tools/smoke-clock/), [Fire pre-plan](/docs/tools/fire-preplan/).

Presets: `fire.preconnect_m = 61`.

## Moving large furniture

Is moving a sofa, bed, piano or appliance and needs to know it fits through.

Tools: [Door widths](/docs/tools/door-widths/), [Furniture fit](/docs/tools/furniture-fit/), [Room census](/docs/tools/room-census/).

## Home gym in the garage

Wants a squat rack and room to press overhead in the garage, maybe with one car still parked.

Tools: [Garage fit](/docs/tools/garage-fit/).

Presets: `garage.count = 0`, `garage.uses = ["squat_rack", "workbench", "bikes"]`.

## Family planning home security

Is planning security cameras and wants every door and ground-floor window watched.

Tools: [Camera coverage](/docs/tools/camera-coverage/), [Window check](/docs/tools/window-check/), [Wi-Fi coverage](/docs/tools/wifi-coverage/), [Egress routes](/docs/tools/egress-routes/), [Room census](/docs/tools/room-census/).

Presets: `security.max_cameras = 4`, `security.camera_fov_deg = 110`, `security.camera_range_m = 9`.

## Houston homeowner before a storm

Has a hurricane or flood coming and wants to know what water would reach and what to move.

Tools: [Flood rehearsal](/docs/tools/flood-rehearsal/), [What sits below the water](/docs/tools/valuables-height/), [Roof facts](/docs/tools/roof-facts/), [Room census](/docs/tools/room-census/).

## Industrial tenant rep

Finds a distribution warehouse for a client: clear height, docks, truck court, highways, rent against comps.

Tools: [Site scorecard](/docs/tools/site-scorecard/), [Industrial fit](/docs/tools/industrial-fit/), [Market comps](/docs/tools/market-comps/), [Truck access](/docs/tools/truck-access/), [Loading docks](/docs/tools/loading-docks/).

Presets: `site.profile = "industrial"`, `site.clear_height_min_ft = 28`, `site.docks_min = 4`, `site.highway_max_km = 3`, `site.flood = "prefer_outside"`.

## Insurance underwriter

Prices risk on a property: roof, flood exposure, what was built versus what is recorded.

Tools: [Roof facts](/docs/tools/roof-facts/), [Flood rehearsal](/docs/tools/flood-rehearsal/), [Record versus reality](/docs/tools/record-vs-reality/), [Room census](/docs/tools/room-census/).

## LA homeowner after the fires

Lives in Los Angeles after the January 2025 fires and wants to know what to clear round the house, whether the roof is fire rated, and how far the fire station is.

Tools: [Wildfire defensible space](/docs/tools/wildfire-space/), [Roof facts](/docs/tools/roof-facts/), [Fire pre-plan](/docs/tools/fire-preplan/).

## Los Angeles household preparing for an earthquake

Lives in Los Angeles and wants each room's safe spot, nothing tall that can fall on a bed, the ways out, and the gas shutoff found before the shaking starts.

Tools: [Earthquake readiness](/docs/tools/quake-ready/), [Egress routes](/docs/tools/egress-routes/), [Field check](/docs/tools/field-check/).

## Light sleeper or night-shift worker

Sleeps lightly or by day and is choosing the bedroom furthest from road, rail and aircraft noise.

Tools: [Quiet rooms](/docs/tools/quiet-rooms/), [Noise level](/docs/tools/noise-level/), [Daylight](/docs/tools/daylight/), [Room census](/docs/tools/room-census/).

Presets: `noise.windows_open = false`.

## Film or photo location scout

Scouts homes and spaces for a shoot: room sizes and ceiling heights, natural light, parking for the trucks, and a step-free way in for carts and gear.

Tools: [Room sizes](/docs/tools/room-sizes/), [Daylight](/docs/tools/daylight/), [Truck access](/docs/tools/truck-access/), [Parking count](/docs/tools/parking-count/), [Curb to door](/docs/tools/curb-to-door/), [Step-free route](/docs/tools/step-free-route/).

## Office relocation lead

Moves a company's office: commutes for the team, size for the headcount, rent, transit and access.

Tools: [Site scorecard](/docs/tools/site-scorecard/), [Commute fit](/docs/tools/commute-fit/), [Market comps](/docs/tools/market-comps/), [Office fit](/docs/tools/office-fit/), [Step-free route](/docs/tools/step-free-route/).

Presets: `site.profile = "office"`, `site.parking_ratio_min = 3`, `site.transit_max_m = 800`, `commute.long_min = 45`.

## Office tenant

Is choosing office space and wants seats, meeting rooms and how the plan works for a team.

Tools: [Office fit](/docs/tools/office-fit/), [Room census](/docs/tools/room-census/), [Door widths](/docs/tools/door-widths/), [Daylight](/docs/tools/daylight/).

Presets: `access.door_width_m = 0.813`.

## Older adult or family

Is choosing a home for an older relative or young children and cares about safe movement.

Tools: [Door widths](/docs/tools/door-widths/), [Step-free route](/docs/tools/step-free-route/), [Bathroom clearance](/docs/tools/bathroom-clearance/), [Stairs](/docs/tools/stairs-count/), [Room census](/docs/tools/room-census/).

Presets: `access.door_width_m = 0.813`.

## Parent with young kids choosing a home

Is choosing a home with a toddler or young children: stairs that need gates, a pool path with no barrier, windows a child could fall from, a yard the kitchen looks onto, and a playground, park and elementary school within a short walk.

Tools: [Kids fit](/docs/tools/kids-fit/), [Path to water](/docs/tools/path-to-water/), [Nearby](/docs/tools/nearby/), [Stairs](/docs/tools/stairs-count/), [Home search for pets and kids](/docs/tools/home-search/), [Tour](/docs/tools/tour/).

Presets: `kids.youngest_age = 3`, `nearby.profile = "kids"`.

## Parent of a toddler, house with a pool

Has a child under five and a backyard pool, and wants to know every way the child could reach the water.

Tools: [Path to water](/docs/tools/path-to-water/), [Door widths](/docs/tools/door-widths/), [Risk sheet](/docs/tools/risk-sheet/).

Presets: `access.door_width_m = 0.815`, `access.door_standard = "ADA 2010 \u00a7404.2.3, 32 in clear"`.

## Tennis or pickleball player

Plays tennis or pickleball and wants courts within a short walk or ride, with a gym and a park close by.

Tools: [Nearby](/docs/tools/nearby/), [Home search for pets and kids](/docs/tools/home-search/).

Presets: `nearby.mode = "walk"`, `nearby.ok_min = 10`, `nearby.categories = ["tennis", "pickleball", "gym", "park"]`.

## Remote worker

Works from home and needs strong Wi-Fi and a quiet room for the office, fast home internet, a quiet street and transit or a bike route for the days out.

Tools: [Wi-Fi coverage](/docs/tools/wifi-coverage/), [Quiet rooms](/docs/tools/quiet-rooms/), [Connectivity](/docs/tools/connectivity/), [Office fit](/docs/tools/office-fit/), [Daylight](/docs/tools/daylight/), [Room census](/docs/tools/room-census/), [Hazard profile](/docs/tools/hazard-profile/), [Area profile](/docs/tools/area-profile/).

Presets: `wifi.router_class = "typical"`.

## Renter checking a listing's claims

Has a listing open and wants each claim checked, plus what the listing leaves out.

Tools: [Listing claims](/docs/tools/listing-claims/), [Daylight](/docs/tools/daylight/), [Record versus reality](/docs/tools/record-vs-reality/), [Room census](/docs/tools/room-census/).

## Renter checking a listing

Is about to rent and wants to know whether the listing matches the place.

Tools: [Room census](/docs/tools/room-census/), [Record versus reality](/docs/tools/record-vs-reality/), [Daylight](/docs/tools/daylight/), [Storage space](/docs/tools/storage-space/).

## Retail site selector

Picks a chain's next store: parking, the road it faces, co-tenants, walk-in trade and rent.

Tools: [Site scorecard](/docs/tools/site-scorecard/), [Retail site](/docs/tools/retail-site/), [Market comps](/docs/tools/market-comps/), [Parking count](/docs/tools/parking-count/).

Presets: `site.profile = "retail"`, `site.parking_ratio_min = 4`, `site.transit_max_m = 800`.

## Home robot maker

Designs a wheeled home robot and wants to know what share of real homes it can get around, and which change to its size helps most.

Tools: [Robot fit](/docs/tools/robot-fit/), [Measure search](/docs/tools/measure-search/), [Turning space](/docs/tools/turning-space/).

Presets: `robot.body_width_m = 0.5`, `robot.turning_diameter_m = 0.7`, `robot.step_height_m = 0.02`.

## Plant lover or home office worker choosing a room

Wants to know which room gets the most sun for plants, which gives daylight without screen glare for a desk, and which bedroom stays cool in summer.

Tools: [Sun by room](/docs/tools/sun-rooms/), [Daylight](/docs/tools/daylight/), [Window check](/docs/tools/window-check/), [Office fit](/docs/tools/office-fit/).

## RV or boat owner

Keeps a boat, trailer or motorhome and needs it off the street: driveway length, and whether the garage door is tall enough.

Tools: [Driveway fit](/docs/tools/driveway-fit/), [Garage fit](/docs/tools/garage-fit/).

Presets: `driveway.vehicle = "boat_20ft"`, `garage.vehicle = "boat_20ft"`, `garage.count = 1`, `garage.uses = []`.

## Older dog that cannot do stairs

Has an older dog with stiff joints: no stairs to daily rooms, grip underfoot, a flat yard, a short way out the back door, and an emergency vet within a short drive.

Tools: [Pet fit](/docs/tools/pet-fit/), [Stairs](/docs/tools/stairs-count/), [Step-free route](/docs/tools/step-free-route/), [Nearby](/docs/tools/nearby/), [Home search for pets and kids](/docs/tools/home-search/).

Presets: `pets.profile = [{"kind": "dog", "weight_lb": 70, "age": "senior"}]`, `nearby.profile = "pets"`, `access.riser_m = 0.178`, `pets.dog_lb = 70`, `pets.dog_age = "senior"`.

## Homeowner considering solar

Wants to know how much of the roof can carry panels, what they would make in a year and how long they take to pay back.

Tools: [Solar roof](/docs/tools/solar-roof/), [Roof facts](/docs/tools/roof-facts/).

## Family with a teenager who plays soccer

Has a teenager who plays soccer: fields and a high school within a walk or a bike ride, a park nearby, and safe streets to get there.

Tools: [Nearby](/docs/tools/nearby/), [Kids fit](/docs/tools/kids-fit/), [Home search for pets and kids](/docs/tools/home-search/).

Presets: `nearby.mode = "cycle"`, `kids.youngest_age = 14`, `nearby.categories = ["soccer", "school_high", "park", "basketball"]`.

## Truck dispatcher

Sends trucks to a site and needs the approach, the dock and the doors a pallet passes.

Tools: [Truck access](/docs/tools/truck-access/), [Loading docks](/docs/tools/loading-docks/), [Door widths](/docs/tools/door-widths/).

Presets: `access.door_width_m = 1.1`, `access.door_standard = "a 40 in pallet on a pallet jack, with a hand's width each side"`.

## Agent or host staging a home virtually

A listing agent or short-stay host who wants to show the rooms furnished: what fits where, how big each room is, and the light.

Tools: [Furniture fit](/docs/tools/furniture-fit/), [Room sizes](/docs/tools/room-sizes/), [Daylight](/docs/tools/daylight/), [Tour](/docs/tools/tour/).

## Wheelchair user looking for a home

Uses a wheelchair and is searching many homes for ones they can get into, around and use without changes.

Tools: [Measure search](/docs/tools/measure-search/), [Step-free route](/docs/tools/step-free-route/), [Bathroom clearance](/docs/tools/bathroom-clearance/), [Turning space](/docs/tools/turning-space/), [Curb to door](/docs/tools/curb-to-door/).

Presets: `search.need = "wheelchair"`, `access.door_width_m = 0.815`, `access.turning_diameter_m = 1.525`, `access.destinations = ["Bathroom", "Bedroom", "Kitchen"]`.

## Wheelchair user

Uses a wheelchair and needs every door, route and bathroom to work for them.

Tools: [Door widths](/docs/tools/door-widths/), [Step-free route](/docs/tools/step-free-route/), [Turning space](/docs/tools/turning-space/), [Bathroom clearance](/docs/tools/bathroom-clearance/), [Room census](/docs/tools/room-census/), [Tour](/docs/tools/tour/).

Presets: `access.door_width_m = 0.813`, `access.door_standard = "ADA 2010 \u00a7404.2.3, 32 in clear"`.

## Wheelchair van owner

Drives a side-entry wheelchair van and needs about 8 ft beside it for the ramp, and a door the van clears.

Tools: [Garage fit](/docs/tools/garage-fit/), [Driveway fit](/docs/tools/driveway-fit/), [Step-free route](/docs/tools/step-free-route/), [Door widths](/docs/tools/door-widths/).

Presets: `garage.vehicle = "wheelchair_van"`, `garage.count = 1`, `driveway.vehicle = "wheelchair_van"`, `access.door_width_m = 0.813`.
