- **Start here:** https://cranley.app
- **Try it live:** https://cranley.app/app (access code from Ben at the table)
- **Every track in detail:** https://cranley.app/tracks/
- **Code:** https://github.com/benz16107/cranley
- **Interview with Jean Ryan (4 min):** https://youtu.be/q5reRgHfS8Y

---

## Measure the building before you commit

Ask anything about a building and get a measured answer, with its source.

### In 30 seconds

Listings say "accessible", "two-car garage", "fits a king bed", and nobody measures before you sign. Cranley is an agent that picks the right tools for your need, from 78 that measure real buildings inside and out: Matterport interior scans, Vexcel aerial imagery and the 3D city, CoStar records, or your own iPhone scan. Every number comes from a calculation, never from a model's text, and says where it came from.

---

## Sponsor tracks

Each track's page has the full detail, proof and limits.

| Track | Page | What we built | Strongest proof | Video |
|---|---|---|---|---|
| CoStar | [page](https://cranley.app/tracks/costar/) | All three layers in one frame; an agent that checks many buildings at once and tests claims across layers | 50 tools run through the real API on 15 places: 266 answers, 62 honest "cannot answer here", 0 judged wrong | |
| Amazon | [page](https://cranley.app/tracks/amazon/) | Ask in plain words; it learns you once and adapts every later investigation, counted on screen | Questions asked over three homes for a returning wheelchair user: 1, 0, 0 | |
| Peri | [page](https://cranley.app/tracks/peri/) | A recorded interview with Jean Ryan, President of Disabled In Action of Metropolitan New York, changed the tools the same night | 12 groups of changes, each with its commit in [docs/feedback.md](https://github.com/benz16107/cranley/blob/main/docs/feedback.md) | [Interview (4 min)](https://youtu.be/q5reRgHfS8Y)<br>[Teaser (44 s)](https://youtu.be/KLdkvYwNQaA) |
| LangChain | [page](https://cranley.app/tracks/langchain/) | A deepagents investigator: parallel subagents, approvals, skills, memory, a rubric grader, LangSmith | Two houses checked at once, both paused before the smoke model and resumed from a MongoDB checkpoint | |
| Photon | [page](https://cranley.app/tracks/photon/) | The same agent over iMessage and a phone call: plan pictures, reply threads, photos and voice notes, the PDF in the chat | Every reply built from the tool result, never model text; 14 tests | |
| MongoDB Atlas | [page](https://cranley.app/tracks/mongodb/) | Workspaces and op log, change-stream live sync, `$rankFusion` search, time series, vector memory | A door width typed on the phone reaches the desktop in about a second | |
| Tiger Data | [page](https://cranley.app/tracks/tiger-data/) | The building facts database: hypertables, compression, continuous aggregates, DiskANN, pgai, forks | A zero-copy fork ready in 31 s for a city-wide what-if; 234 MB compressed to 58 MB | |

---

## The problem

> "I don't ask them if it's a wheelchair accessible. I ask them if they have any steps."
>
> Jean Ryan, President of Disabled In Action of Metropolitan New York, who uses a 400-pound powered wheelchair

> "I measured. Listings never had the garage depth."
>
> A truck owner on r/f150

The scans, the aerial photos and the records that answer these questions exist, but each sits in its own product, one listing at a time.

---

## How it works

1. **Say what you need.** "I use a wheelchair, 81 cm wide. Find a one-bedroom in Houston I can get into and use the bathroom."
2. **It picks the tools** from 78 and asks only what is missing.
3. **It checks many buildings at once,** one subagent each; slow steps wait for your yes.
4. **It shows the evidence:** the route through the photoreal building, the step in red, each number's source.
5. **Change it and keep it:** "widen this door" re-runs the checks; a PDF lists fixes and what was not checked.
6. **From anywhere:** your iPhone scan, the phone companion, iMessage, or any agent over MCP.

---

## Built forward-deployed

Before and while building we asked people what goes wrong with their buildings: a recorded 31-minute interview with Jean Ryan ([4-minute highlights](https://youtu.be/q5reRgHfS8Y)), written answers from 58 people in 17 online communities (truck, boat and RV owners, occupational therapists, a chef, store associates, restaurant operators, managers), and 491 emails, which brought six human replies (the interview, a Los Angeles theatre's managing director, a museum director who asked to talk on Sunday, and three declines).

Their answers changed the tools the same night: steps first, several chairs per person, bathroom door swing, garage depth and trailer checks, a store's backroom and a kitchen's rack route. Every quote and its change: [docs/feedback.md](https://github.com/benz16107/cranley/blob/main/docs/feedback.md).

---

## Proof

| Number | What it measures |
|---|---|
| **266** | Answers when every tool built by Saturday morning (50) ran through the real API on 15 places; 62 honest "cannot answer here", 0 judged wrong |
| **810 + 118** | Server tests and web tests |
| **3.7 min** | A wheelchair brief: 6 tools composed, 25 tool runs on 5 buildings |
| **1, 0, 0** | Questions asked over three homes for one returning wheelchair user; checks kept back 0, 3, 9 (counted from the op logs; a replay, not a user study) |
| **16 to 23 min** | Training one interior Gaussian splat on an AMD mini PC's integrated GPU, no NVIDIA (four buildings) |

---

## How we built it

- **Server (Python, FastAPI):** shared engines for routes, clearance, rules, takeoff, georeference and vision; each tool returns a typed result with sources.
- **Agent (deepagents, LangGraph):** a composer picks tools; an investigator plans, fans out and asks before slow steps.
- **Data:** MongoDB Atlas for people's work, Tiger Cloud for building facts.
- **Web (React, three.js, MapLibre, deck.gl):** one view from the map into the room, with 66 public map layers.
- **Phone and messaging:** a phone companion, a SwiftUI RoomPlan app, iMessage and voice (Photon, ElevenLabs), an MCP server and CLI.
- **Physics:** NIST CFAST for smoke, USGS high-water marks for Hurricane Harvey.

---

## Limits

- Only scans with a wall graph get geometry checks; the rest get what panoramas and records can say.
- Flood and fire results are planning aids, not inspections.
- The iPhone app runs in the simulator; it has not been on a phone yet.
- The adaptation numbers come from a scripted replay of one person.

## What's next

The iPhone app on real phones, so any shop or home can be checked in ten minutes, and a hosted MCP server so any agent can check a building.

---

Built on open-source libraries credited in the [README](https://github.com/benz16107/cranley#credits), plus NIST CFAST, Brush and Apple RoomPlan. Data from CoStar, Matterport and Vexcel under the event's terms; none of it is in the repository.
