---
title: "Peri: Forward Deployed Challenge"
---

Judged real-world need, usability (could the business adopt it immediately), execution.

**Built forward-deployed.** Cranley started from the problem, not the data. Before and while building, we asked
consumers and businesses what goes wrong with the inside and outside of their buildings, then changed the tools to match
what they said.

**1. Discovery.** What people told us, in interviews and written answers:

| Who | How | What they said |
|---|---|---|
| Jean Ryan, President of Disabled In Action of Metropolitan New York (an all-volunteer disability rights group in New York City), a powered-wheelchair user | A recorded 31-minute phone interview on Saturday night, after she replied to our email | She no longer asks whether a place is "wheelchair accessible", because she has been told yes and arrived to find a step. She asks whether there are any steps, including steps a few feet inside an accessible entrance and in lobbies before the elevators. A bathroom stall door that opens inward blocks the chair, and a bin beside the toilet can make an accessible stall unusable. Many people own more than one chair and do not know the widths. |
| Truck, boat, RV and Cybertruck owners (r/f150, r/boating, r/cybertruck, r/TruckCampers, r/RVLiving, r/Garages) | Written answers to a question posted in each community | Garage depth decides it more than width. One owner wrote that most subdivision garages built after 1999 near him are 19.5 to 20 ft deep against 25 to 30 ft in older homes; another chose a smaller car because the garage could not take the truck; boat owners measure the trailer tongue and the door opening, not the ceiling. Several trucks "fit" with no room to walk around them. |
| Home networking and home automation (r/HomeNetworking, r/homeautomation) | Written answers | Signal dies at ductwork, glass walls and a detached garage; a doorbell camera mounted too low sees only shoes. |
| Los Angeles residents and wildfire (r/AskLosAngeles, r/wildfire) | Written answers | Insurers order trees trimmed off roofs; a defensible-space checklist of vents, gutters, decks and what sits within 20 ft. |
| Workplaces: a chef who takes over kitchens (r/Chefit), restaurant operators (r/restaurant), a Walmart receiving associate (r/walmart), managers (r/AskManagers), emergency management (r/EmergencyManagement) | Written answers | Check cart and hand-truck access, cooler space and 3-phase power before taking a kitchen; hot water that never reaches the far sinks; a dock that unloads around a 90 degree corner; an office under a bathroom; a library emergency review that found gaps a routine inspection missed. |
| 340 organisations and businesses in New Jersey, New York, Texas and elsewhere | Email | Three people replied: the interview above and two declines; the rest were automatic replies or silence. |

**2. Build.** What changed because of it, on main the same night (`ws/feedback`, merged at `480147f`):

1. Steps first: step-free route now opens with a steps check per destination, counts steps seen in the panoramas against
   the route, and lists the rooms reached with no step, including steps inside past the front door.
2. Several chairs per person: the profile keeps each chair (everyday and travel) with the door width it needs, and the
   route, bathroom and turning checks run for each chair.
3. Bathroom: which way each door opens (from the scan, else the panorama, else "not in the scan"), and clear floor in
   front of and beside the toilet, with scanned objects such as bins counted as blocking.
4. Aisles: turning space counts the objects a phone scan measured on the floor and checks the aisle from the doorway to
   the turning spot between them.
5. Floors and elevators: other floors say "elevator only" when the scan has one.
6. What a scan cannot tell: the step-free route and bathroom checks each end with a list of it, and turning space says
   when a scan recorded walls only.
7. From the truck and boat owners: garage fit checks depth to the back wall on its own, clear of objects the scan
   measured, with a "not in the scan" line for fittings on the wall; boats and trailers use the maker's storage length;
   the door opening is checked at a trailer's fenders and side lights.

**3. Evidence.** Jean Ryan agreed before the call to be filmed and to have anything from it shared. In her words
(times in the recording):

> "I don't ask them if it's a wheelchair accessible. I ask them if they have any steps." (07:05)

> "Is it wheelchair accessible? Yes. I get there, and there's a step, and I couldn't go in. I have a 400-pound chair." (05:22)

> "I could get in the bookstore, but I couldn't go to the books." (05:57)

> "If it opens in, you typically cannot get in because the door is blocking them." (09:45, on bathroom stall doors)

> "A lot of people have more than one chair." (02:19)

**State:** complete. Organisation: Disabled In Action of Metropolitan New York. Person and role: Jean Ryan, President
(stated by her at 25:24). Evidence: the recorded interview and the quotes above. Consulted on Saturday 14 November,
during the event.

**Scripted flow:** `web/src/skins/app/demo/flows/peri.json`, "A business checks an office and keeps the report".

**Demo path.** The discovery table first (who we asked and what they said), then one change it caused (steps first on
the wheelchair route), then the scan-to-report flow and the PDF.
