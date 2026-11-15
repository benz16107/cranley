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
| The president of a New York City disability rights organisation, a powered-wheelchair user | A 31-minute phone call on Saturday night, after she replied to our email | She no longer asks whether a place is "wheelchair accessible", because she has been told yes and arrived to find a step. She asks whether there are any steps, including steps a few feet inside an accessible entrance and in lobbies before the elevators. A bathroom stall door that opens inward blocks the chair, and a bin beside the toilet can make an accessible stall unusable. Many people own more than one chair and do not know the widths. |
| Truck, boat, RV and Cybertruck owners (r/f150, r/boating, r/cybertruck, r/TruckCampers, r/RVLiving, r/Garages) | Written answers to a question posted in each community | Garage depth decides it more than width. One owner wrote that most subdivision garages built after 1999 near him are 19.5 to 20 ft deep against 25 to 30 ft in older homes; another chose a smaller car because the garage could not take the truck; boat owners measure the trailer tongue and the door opening, not the ceiling. Several trucks "fit" with no room to walk around them. |
| Home networking and home automation (r/HomeNetworking, r/homeautomation) | Written answers | Signal dies at ductwork, glass walls and a detached garage; a doorbell camera mounted too low sees only shoes. |
| Los Angeles residents and wildfire (r/AskLosAngeles, r/wildfire) | Written answers | Insurers order trees trimmed off roofs; a defensible-space checklist of vents, gutters, decks and what sits within 20 ft. |
| Workplaces: a chef who takes over kitchens (r/Chefit), restaurant operators (r/restaurant), a Walmart receiving associate (r/walmart), managers (r/AskManagers), emergency management (r/EmergencyManagement) | Written answers | Check cart and hand-truck access, cooler space and 3-phase power before taking a kitchen; hot water that never reaches the far sinks; a dock that unloads around a 90 degree corner; an office under a bathroom; a library emergency review that found gaps a routine inspection missed. |
| 340 organisations and businesses in New Jersey, New York, Texas and elsewhere | Email | Three people replied: the interview above and two declines; the rest were automatic replies or silence. |

**2. Build.** What changed because of it (being built on `ws/feedback`; each item is marked when it merges):

1. Steps first: the wheelchair route's headline is whether there are any steps or level changes between the entrance and
   the room, including steps inside past the front door and before the elevators.
2. Several chairs per person (everyday and travel), each checked.
3. Bathroom door swing (opens in or out) and clear floor space beside and in front of the toilet, with objects such as
   a bin counted as blocking.
4. Aisles and turning space with objects on the floor counted, for shops.
5. Floors and elevators: which rooms are reachable without stairs, and a plain line when the only way is an elevator.
6. What a scan cannot tell, on every result: temporary obstructions, an elevator out of service, whether anyone
   enforces the rules.

**3. Evidence.** The interview notes with timestamps and the written answers are kept with the team; quotes and the
organisation's name will appear here once the person we interviewed agrees to be named.

**State:** one organisation consulted during the event (the interview above). Peri's rule needs the organisation's
name, the person's name and role, and one piece of evidence, so the entry is complete only once she agrees to be named.

**Scripted flow:** `web/src/skins/app/demo/flows/peri.json`, "A business checks an office and keeps the report".

**Demo path.** The discovery table first (who we asked and what they said), then one change it caused (steps first on
the wheelchair route), then the scan-to-report flow and the PDF.
