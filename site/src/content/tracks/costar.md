---
title: "CoStar: Inside and Out, AI for the Built World"
---

Judged 30% use of the data, 30% agentic depth, 25% usefulness, 15% demo and polish.

**Angle.** The track asks for something that makes CoStar say "we didn't know you could do that with our data". Every
CoStar product today answers questions inside one listing. Cranley answers a person's question across a whole city,
by measurement, with all three layers checking each other.

| Criterion | What serves it |
|---|---|
| Use of the data (30%) | All three layers in one frame: walls and doorways from Matterport, elevation, ortho, property facts and the 3D city from Vexcel, records from CoStar. Cross-layer tools: record versus reality (listed vs measured area, claims check), flood (Vexcel ground elevation + Matterport door sills), garage and driveway fit (interior garage + aerial driveway), site tools (docks, truck access, parking from the air), drone splat aligned to the scan. Search by measurement over every scan with a wall graph. |
| Agentic depth (30%) | A deepagents investigator that plans (todo list the person watches), fans out one subagent per building in parallel, asks before expensive steps, remembers what it learned per building, and resumes after a restart from a MongoDB checkpoint. The composer picks tools for the need from more than 75, asks only the missing inputs, and the workspace is a document the agent and the person edit with the same operations (with undo). |
| Usefulness (25%) | Checked against discovery (Peri section): truck owners told us garage depth decides whether a truck fits, and that newer subdivision garages run 19.5 to 20 ft deep; garage fit, built earlier the same day, measures the scanned garage instead of trusting "two-car garage" in the listing. 50 personas, each a real user with a named need: wheelchair user, fire captain, Houston homeowner before a storm, truck dispatcher, office tenant, CoStar researcher, insurance underwriter, daycare operator, car owner. For the people who open CoStar every morning: a tenant rep's weighted site scorecard across candidates, market comps from CoStar records, industrial fit (clear height, docks, truck court), retail site screening, commute fit for a whole team, and a facility audit PDF. PDF report a person can hand to a landlord. |
| Demo and polish (15%) | Photoreal building on its site, flood rising in the street, smoke filling rooms, the agent's lanes working in parallel. A dense working tool, not a showcase. |

**Scripted flow:** `web/src/skins/app/demo/flows/costar.json`, "Check a listing against the scan, then tour it": the agent reads the
listing, the CoStar record and the scan side by side, the camera goes to the room where they disagree, then the tour
plays every finding.

**Demo path (2 minutes).**
1. Home. Type "I use a wheelchair, 81 cm wide. Find a one-bedroom in Houston I can get into and use the bathroom."
2. The composer adds step-free route, door widths, turning space and bathroom clearance, asks nothing (width given).
3. The investigator's lanes run five buildings at once; the ranked table fills.
4. Open the top building: photoreal, on its site in the city. The route draws from the curb to the toilet; the one
   narrow door shows red with "Matterport geometry, high".
5. Record versus reality on the same building: the listed area against the measured one.
6. Twenty-second switch: Houston homeowner, Harvey water rising through the same photoreal house, the list of what
   to move first.
7. Close on the catalogue and the line "every number from a calculation".
