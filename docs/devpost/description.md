- **Start here:** https://cranley.app
- **Try it live:** https://cranley.app/app
- **Every track in detail:** https://cranley.app/tracks/
- **Code:** https://github.com/benz16107/cranley
- **Conversation with Jean Ryan (7 min):** https://youtu.be/EoHyoNs2idg
- **Video (2 min):** https://youtu.be/cwn0x1TZYKQ

---

## Measure the building before you commit

Ask anything about a building and get a measured answer, with its source.

### In 30 seconds

Listings say "accessible", "two-car garage", "fits a king bed", and nobody measures before you sign. Cranley is an agent that picks the right tools for your need, from 78 that measure real buildings inside and out: Matterport interior scans, Vexcel aerial imagery and the 3D city, CoStar records, or your own iPhone scan. Every number comes from a calculation, never from a model's text, and says where it came from.

![A Houston house on its site: the scanned interior cut open inside the drone capture and the Vexcel 3D city](https://d112y698adiu2z.cloudfront.net/photos/production/software_photos/005/908/055/datas/gallery.jpg)

---

## Sponsor tracks

Each track page has the details.

| Track | Page | What we built | Strongest proof | Video |
|---|---|---|---|---|
| CoStar | [page](https://cranley.app/tracks/costar/) | Asked for an agent using at least two of the three layers; we built one using all three in one frame, plus 78 tools, parallel subagents, a photoreal 3D city, iPhone scans and PDF reports | 50 tools run through the real API on 15 places: 266 answers, 62 honest "cannot answer here", 0 judged wrong | |
| Amazon | [page](https://cranley.app/tracks/amazon/) | Asked for AI that reasons, plans, acts and adapts; we built that, plus a profile that learns you once with the adaptation counted on screen, a phone companion, iMessage and an iPhone LiDAR app | Questions asked over three homes for a returning wheelchair user: 1, 0, 0 | |
| Peri | [page](https://cranley.app/tracks/peri/) | Asked to solve one consulted business's problem; we interviewed Jean Ryan, President of Disabled In Action of Metropolitan New York, asked 58 more people online, emailed 491 organisations, and shipped 12 groups of changes that night | 12 groups of changes, each with its commit in [docs/feedback.md](https://github.com/benz16107/cranley/blob/main/docs/feedback.md) | [Conversation (7 min)](https://youtu.be/EoHyoNs2idg)<br>[Teaser (32 s)](https://youtu.be/M5G2j62ZYGQ) |
| LangChain | [page](https://cranley.app/tracks/langchain/) | Asked for a deepagent; we built a deepagents investigator with planning, parallel subagents, approvals that resume from a MongoDB checkpoint, skills, long-term memory, a rubric grader, MCP tools and LangSmith experiments | Two houses checked at once, both paused before the smoke model and resumed from a MongoDB checkpoint | |
| Photon | [page](https://cranley.app/tracks/photon/) | Asked for a messaging agent on Photon 2.0; we built an iMessage agent (plan pictures, reply threads as investigations, photos, video, voice and location in, the PDF in the chat) and a phone voice agent. The voice agent waits on a phone number, and the first live round trip is unconfirmed | Every reply built from the tool result, never model text; 14 tests | |
| MongoDB Atlas | [page](https://cranley.app/tracks/mongodb/) | Asked to build with Atlas; we use 12 Atlas features: op log with transactions, change streams, Atlas Search, Vector Search with automated embedding, `$rankFusion`, time series, TTL, 2dsphere, schema validation, LangGraph checkpointer and store, MCP | A door width typed on the phone reaches the desktop in about a second | |
| Tiger Data | [page](https://cranley.app/tracks/tiger-data/) | Asked to show Tiger powering the app; we built the facts database on hypertables, compression, continuous aggregates and hyperfunctions, plus PostGIS, DiskANN, BM25, the pgai vectorizer, jobs, retention, read-only agent SQL and forks | A zero-copy fork ready in 31 s for a city-wide what-if; 234 MB compressed to 58 MB | |

![Amazon: two occupational therapists' home-assessment lists and the aging-in-place checks they became](https://d112y698adiu2z.cloudfront.net/photos/production/software_photos/005/908/256/datas/gallery.jpg)

![Photon: Cranley's actual replies to a garage question, shown in a messages frame](https://d112y698adiu2z.cloudfront.net/photos/production/software_photos/005/908/153/datas/gallery.jpg)

---

## The problem

> "I don't ask them if it's a wheelchair accessible. I ask them if they have any steps."

Jean Ryan, President of Disabled In Action of Metropolitan New York, who uses a 400-pound powered wheelchair

> "I measured. Listings never had the garage depth."

A truck owner on r/f150

![Truck and boat owners on garage depth, and what garage fit now checks](https://d112y698adiu2z.cloudfront.net/photos/production/software_photos/005/908/817/datas/gallery.jpg)

The scans, the aerial photos and the records that answer these questions exist, but each sits in its own product, one listing at a time.

---

## How it works

1. **Say what you need:** "I use a wheelchair, 81 cm wide. Can I reach the bathroom?"
2. **It picks the tools** from 78 and asks only what is missing.
3. **It checks many buildings at once,** one subagent each; slow steps wait for your yes.
4. **It shows the evidence:** the route through the photoreal building, the step in red, each number's source.
5. **Change it and keep it:** "widen this door" re-runs the checks; a PDF lists fixes and what was not checked.
6. **From anywhere:** your iPhone scan, the phone companion, iMessage, or any agent over MCP.

![Four agents at once: one subagent per candidate home, each running door, route, turning and bathroom checks](https://d112y698adiu2z.cloudfront.net/photos/production/software_photos/005/908/082/datas/gallery.jpg)

---

## Built forward-deployed

Before and while building we asked people what goes wrong with their buildings: a recorded 31-minute interview with Jean Ryan ([the conversation, 7 min](https://youtu.be/EoHyoNs2idg)), written answers from 58 people in 17 online communities, and 491 emails, which brought six human replies.

Their answers changed the tools the same night. Every quote and its change: [docs/feedback.md](https://github.com/benz16107/cranley/blob/main/docs/feedback.md).

![Outreach at a glance: a recorded interview, 58 people in 17 communities, 491 emails, six human replies](https://d112y698adiu2z.cloudfront.net/photos/production/software_photos/005/908/100/datas/gallery.jpg)

![What people told us and what we changed that night, each with its tool and commit](https://d112y698adiu2z.cloudfront.net/photos/production/software_photos/005/908/113/datas/gallery.jpg)

---

## Proof

| Number | What it measures |
|---|---|
| **266** | Answers from 50 tools run through the real API on 15 places; 62 honest "cannot answer here", 0 judged wrong |
| **810 + 118** | Server tests and web tests |
| **3.7 min** | A wheelchair brief: 6 tools composed, 25 tool runs on 5 buildings |
| **1, 0, 0** | Questions asked over three homes for one returning wheelchair user (a replay, not a user study) |
| **16 to 23 min** | Training one interior Gaussian splat on an AMD mini PC's integrated GPU, no NVIDIA (four buildings) |

---

## How we built it

- **Server (Python, FastAPI):** shared engines for routes, clearance, rules and vision; each tool returns a typed result with sources.
- **Agent (deepagents, LangGraph):** a composer picks tools; an investigator plans, fans out and asks before slow steps.
- **Data:** MongoDB Atlas for people's work, Tiger Cloud for building facts.
- **Web (React, three.js, MapLibre, deck.gl):** one view from the map into the room, with 66 public map layers.
- **Phone and messaging:** a phone companion, a RoomPlan iPhone app, iMessage and voice, an MCP server and CLI.
- **Physics:** NIST CFAST for smoke, USGS high-water marks for Hurricane Harvey.

---

## Limits

- Only scans with a wall graph get geometry checks; the rest get what panoramas and records can say.
- Flood and fire results are planning aids, not inspections.
- The iPhone app runs in the simulator; it has not been on a phone yet.

## What's next

The iPhone app on real phones and a hosted MCP server, so any shop, home or agent can check a building.

---

Built on open-source libraries credited in the [README](https://github.com/benz16107/cranley#credits), plus NIST CFAST, Brush and Apple RoomPlan. Data from CoStar, Matterport and Vexcel under the event's terms; none of it is in the repository.
