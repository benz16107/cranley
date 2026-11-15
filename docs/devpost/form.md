# Devpost form: fields and draft answers

Hackathon `hackprinceton-fall-26` (id 31990). Deadline 8:00 am ET Sunday Nov 15 (Devpost closes 8:30 am; the rules say
8:00, so treat 8:00 as the stop). Judging 9:30 am to 2 pm, 2-minute in-person demo required even with a video. Video
optional, at most 2 minutes. Opt into every sponsor prize on Devpost before the deadline; the opt-in checkbox says an
unticked prize is not judged.

| Field (id) | Required | Draft answer |
|---|---|---|
| Name | yes | Cranley |
| Tagline (200) | yes | Listings say "accessible" and "two-car garage". Cranley measures it: an agent that checks real buildings, inside and out, before you commit. |
| Description | yes | `docs/devpost/description.md` |
| Built with (max 25) | yes | see below |
| Public Git Repository (29740) | yes | https://github.com/benz16107/cranley (being built from a cleaned history) |
| Universities (29742) | yes | fill in for every member |
| Technology feedback (29743) | yes | see below |
| GenAI used, dropdown (29744) | yes | Anthropic, Other |
| Did you implement a generative AI model or API (29745) | yes | see below |
| Gemini project number (29746) | yes | N/A |
| Discord usernames and names (29747) | yes | ask Ben |
| Main HackPrinceton track (29748) | yes | Business/Enterprise (default; question 3 in story.md) |
| Rookie fraction (29749) | yes | "Less than 2/3 rookies" if Ben is the only member or the team is experienced; ask |
| Rules checkbox (29750) | yes | Ben ticks |
| Opt-in checkbox (29751) | yes | Ben ticks after choosing prizes |
| GoDaddy Registry domains (30095) | no | none unless a domain is bought |

## Prizes to opt into on Devpost

- [CoStar Group] Inside and Out: AI for the Built World
- [Amazon] Best Practical AI Innovation
- [MLH] Best Use of Tiger Data
- [MLH] Best Use of MongoDB Atlas
- [Photon] Build a Messaging Agent using Photon 2.0 (winner, runner-up, Best Voice Agent)
- [Peri] Forward Deployed Engineer: only with a consulted business and evidence
- LangChain deepagents: not on Devpost's prize list; ask how to enter

## Built with (25)

python, fastapi, langchain, deepagents, langgraph, langsmith, anthropic, mongodb-atlas, timescaledb, tiger-data, postgresql,
postgis, pgvector, react, typescript, vite, three.js, maplibre, deck.gl, swift, swiftui, arkit, roomplan, ollama, matterport

## Technology feedback (29743)

MongoDB Atlas: change streams made live sync between the desktop and the phone a few lines of code, and automated
embedding (voyage-4) meant no embedding key in the app. The free tier's limit of three search indexes shaped our design:
we merged text and vector search into one hybrid `$rankFusion` query rather than adding a fourth index.

Tiger Data: zero-copy forks were the surprise of the weekend. A fork was ready in about 31 seconds on the free plan, so
"what if every door in the city were widened" runs on a copy that is deleted after. pgai's vectorizer worked against
Tiger Cloud's PostgreSQL 18 only after we installed its catalog SQL by hand, since the `ai` extension is not offered
there. A StreamingDiskANN index grown row by row returned poor recall until a scheduled job rebuilt it.

LangChain deepagents: subagents, human-in-the-loop interrupts and the MongoDB checkpointer fit together cleanly; a paused
turn resumes in another server process. Subagents need a call budget that leaves room to answer, or they spend it all
reading memory.

## Generative AI (29745)

Yes. Anthropic Claude (Sonnet for the agent, Opus for vision) through LangChain. Claude composes the workspace (which
tools fit a need and which questions to ask), runs the investigator agent that plans and fans out per building,
labels rooms and finds objects such as smoke alarms in panorama photos, and writes the plain-language notes. It never
states a measurement: every number comes from geometry, a simulation or a lookup, and a rubric grader rejects closing
messages that contain numbers. Embeddings: Ollama nomic-embed-text inside Tiger via pgai, voyage-4 inside Atlas, and
bge-small through fastembed.

Devpost draft: project 1548715, slug `threshold-o1e7uj`, https://devpost.com/software/threshold-o1e7uj (draft submission 1303844). Ben submits.
