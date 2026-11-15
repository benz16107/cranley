# Devpost form: answers ready for Ben

**SUBMITTED 2026-11-15 3:12 am ET** (submission 1303844, status Submitted) with Ben's go via the lead (~3:20 am, "yeah you can submit it"), using the answers below, Discord `bennyboy0406 - Ben Zhou`, and opt-ins CoStar 109286, Amazon 109287, Peri 109288, Photon 109283, MLH Tiger Data 109145, MLH MongoDB Atlas 109148 and LangChain deepagents 109306 (LangChain appeared on Devpost's prize list after the first read). Video and the recut interview links are added later with `update_project` / a re-submit. **Re-submitted 4:06 am** with Ben's yes via the lead: only the technology feedback answer (29743) changed (ElevenLabs paragraph, the voice line is live); the same seven opt-ins passed; every other answer and the entry video left as saved.

Hackathon `hackprinceton-fall-26` (id 31990). Deadline 8:00 am ET Sunday Nov 15 (Devpost closes 8:30 am; the rules say
8:00, so treat 8:00 as the stop). Judging 9:30 am to 2 pm, 2-minute in-person demo required even with a video. Video
optional, at most 2 minutes. Opt into every sponsor prize on Devpost before the deadline; an unticked prize is not judged.

Devpost project: https://devpost.com/software/threshold-o1e7uj (project 1548715, draft submission 1303844). The
description, tagline, links and built-with are filled in through the Devpost MCP; Ben ticks the boxes and submits.

## Project fields

| Field | Answer |
|---|---|
| Name | Cranley |
| Tagline (200) | Ask anything about a building. Get a measured answer. An agent that measures the real building, inside and out, before you commit. |
| Description | `docs/devpost/description.md` (synced) |
| Built with (25) | python, fastapi, langchain, deepagents, langgraph, langsmith, anthropic, mongodb-atlas, timescaledb, tiger-data, photon, postgis, pgvector, react, typescript, elevenlabs, three.js, maplibre, deck.gl, swift, swiftui, arkit, roomplan, ollama, matterport |
| Video | https://youtu.be/W-0JnByJJss (1:56, unlisted; set on the project and the entry; may be swapped for a dark-mode cut) |

## Custom questions (ids from `get_submission_requirements`)

| Field (id) | Answer |
|---|---|
| Public Git Repository (29740) | https://github.com/benz16107/cranley |
| Universities (29742) | University of Toronto |
| Technology feedback (29743) | see below |
| GenAI used, dropdown (29744) | Anthropic, ElevenLabs |
| Did you implement a generative AI model or API (29745) | see below |
| Gemini project number (29746) | N/A |
| Discord usernames and names (29747) | bennyboy0406 - Ben Zhou |
| Main HackPrinceton track (29748) | Business/Enterprise |
| Rookie fraction (29749) | Less than 2/3 rookies |
| Rules checkbox (29750) | Ben ticks |
| Opt-in checkbox (29751) | Ben ticks after opting into the prizes below |
| GoDaddy Registry domains (30095) | None (cranley.app is a .app domain) |

Rookie note: Ben is entering solo and is not a first-time hacker, so the team is 0 of 1 rookies. The dropdown's "1/1"
would mean one rookie out of one, which is wrong; "Less than 2/3 rookies" is the option that covers 0 of 1.

## Sponsor prizes to opt into on Devpost

- [CoStar Group] Inside and Out: AI for the Built World
- [Amazon] Best Practical AI Innovation
- [Peri] Forward Deployed Engineer (Jean Ryan, President, Disabled In Action of Metropolitan New York; recorded interview, quotes; consent given before the call)
- [Photon] Build a Messaging Agent using Photon 2.0 (winner, runner-up, Best Voice Agent)
- [MLH] Best Use of Tiger Data
- [MLH] Best Use of MongoDB Atlas
- [LangChain] Best use of deepagents (added to Devpost's prize list during the night; opted in)

Not entered: Gemini, Solana, Vultr, SpaceXSI, GoDaddy Registry, DEV Writing, Nessie, Arlequin, Physical AI.
ChatOverflow needs no submission (it ranks connected agents).

## Technology feedback (29743)

**Anthropic Claude.** Claude ran every model step: the composer that picks tools for a need, the investigator agent
and its subagents, and the vision reader that labels rooms and finds objects such as smoke alarms in panorama photos.
Structured output made the composer's tool plan reliable to parse. The hard part was keeping numbers out of its text:
we added a rubric grader after one turn claimed "none of the checks ran" following twelve runs.

**MongoDB Atlas.** Change streams made live sync between the desktop and the phone a few lines of code, and automated
embedding (voyage-4) meant no embedding key in the app. The free tier's limit of three search indexes shaped the design:
we merged text and vector search into one `$rankFusion` query instead of adding a fourth index. The LangGraph
checkpointer on Atlas let a paused agent turn resume in another server process.

**Tiger Cloud.** Zero-copy forks were the surprise of the weekend: a fork was ready in about 31 seconds on the free plan,
so a city-wide what-if runs on a copy that is deleted afterwards. pgai's vectorizer worked on Tiger Cloud's PostgreSQL 18
only after we installed its catalog SQL by hand, since the `ai` extension is not offered there. A StreamingDiskANN index
grown row by row returned poor recall until a scheduled job rebuilt it.

**LangChain deepagents and LangSmith.** Subagents, human-in-the-loop interrupts, skills and the MongoDB checkpointer fit
together cleanly, and parallel subagents mapped naturally to one building each. Subagents need a call budget that leaves
room to answer, or they spend it all reading memory. LangSmith traces made those failures easy to find, and its datasets
let us score each composer prompt change.

**Photon.** The 2.0 API made iMessage replies, reply threads and attachments straightforward to wire, and reply threads
mapped well to investigations. On the free shared line a person has to text first and a late send can be refused, so we
queue refused answers until their next message. Tapbacks and polls are not available on the shared iMessage line yet.

**ElevenLabs.** We set up a voice agent that calls the same tools over SIP, with a script that creates the agent and its
tools. Tool calling worked well with short spoken answers. It now answers on a Photon voice number: on the first real call
it ran the garage check, read the measured answer aloud, and the plan picture and the answer arrived by iMessage after the call.


**Vercel.** The Astro site and docs deploy with one command, with previews behind a login and production on our own
domain. Pointing cranley.app at Vercel took one DNS change.

## Generative AI (29745)

Yes. Anthropic Claude (Sonnet for the agent, Opus for vision) through LangChain. Claude composes the workspace (which
tools fit a need and which questions to ask), runs the investigator agent that plans and fans out one subagent per
building, labels rooms and finds objects such as smoke alarms in panorama photos, and writes the plain-language notes.
It never states a measurement: every number comes from geometry, a simulation or a lookup, and a rubric grader rejects
closing messages that contain numbers. ElevenLabs runs the phone voice agent, which calls the same tools. Embeddings:
Ollama nomic-embed-text inside Tiger through pgai, voyage-4 inside Atlas, and bge-small through fastembed.

## Try it links

- Start here: https://cranley.app
- Live demo: https://cranley.app/app (open, no access code since ~3:30 am; the code still exists in the data .env if Ben turns it back on)
- Fallback if cranley.app/app is down: https://linuxbox.<tailnet>:10000/app (same door, same code)
- Code: https://github.com/benz16107/cranley
- Conversation with Jean Ryan (7 min): https://youtu.be/xFw0Rpz9pbk
