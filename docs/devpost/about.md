# About Cranley: sections moved off the Devpost page

The Devpost page follows the short GurtOS and Tessera layout. These sections were on it until 2026-11-14, 11:30 pm and
are kept here for the site (`/about/` or `/how/`). Generated from `docs/devpost/description.md` before the relayout.

## It learns you once

Jean Ryan of Disabled In Action told us "a lot of people have more than one chair", and many people do not know their widths. A person should only have to say it once.

Tell Cranley your wheelchair is 70 cm wide on the first home you look at. On the next home you type six words, "Is this one workable for me?", and it asks nothing: it measures every doorway against your chair, leaves out the tool you removed last time and keeps back the kinds of check you said were not relevant. Each of those decisions is written on screen with where it came from ("You told me on 14 Nov"), and one click changes or forgets it.

**Measured, not claimed.** We replayed one scripted wheelchair user over three homes through the real composer and agent. Questions asked: 1, then 0, then 0. Tool inputs filled from what it already knew: 0, then 3, then 3. Checks kept back because the person had waved that kind off: 0, then 3, then 9. Of the checks shown, the share this person's fixed rule counts as relevant: 19 of 29, then 38 of 38, then 46 of 46. The same counts appear in the app for a real person, under "How Cranley has adapted to you", taken from their own history. It is a replay of one person, not a user study, and time to the first result did not change in a way we can claim.

## What makes it different

- **Inside, outside and the record together.** Tools check one layer against another: the listed area against the measured one, the floor height from aerial elevation against the door sill from the scan.
- **Your own building.** The iPhone app scans a room with LiDAR (Apple RoomPlan) and converts it to the same plan format, so every geometry tool runs on a space that is in no dataset.
- **Photoreal 3D we built ourselves.** The scanned mesh baked with its own panoramas, interior Gaussian splats we trained, set in the 3D city with a cut-away, one continuous view from the street into the room.
- **Physics, not pictures.** CFAST for smoke. USGS high-water marks for floods.
- **The building in its city.** One continuous view from the map through the aerial and the 3D city into the room, with 66 map layers around it (flood zones, Harvey high-water marks, hydrants, zoning, permits, transit, live weather), each labelled with its source and fetch date.
- **Search by what is measured inside.** "One-floor houses with three bedrooms and every door at least 81 cm" is one query.
- **Where people already are.** Over Photon 2.0, ask by iMessage or a phone call from the viewing itself; a photo of a doorway with a bank card in it gets measured, and the PDF arrives in the chat.
- **Any agent can use it.** Every tool is also an MCP tool and a `threshold` CLI command, so Claude Code can ask "will an F-150 fit in this garage" and answer from the result.
- **Honest by construction.** Each number carries its layer, its method and a high, medium or low label. A scan that cannot answer gets an "unknown" verdict with the reason.

## Challenges we ran into

- The scans' mesh download was unavailable, so the first dollhouse was drawn from the wall graph. Later we found the scanned mesh through the model API and baked it with the panoramas.
- About half the scans have no wall graph. Every tool checks the plan's quality first and says plainly when it cannot answer; for some scans we recovered walls from the schematic drawing.
- The compass direction of a scan had no documented convention. We fitted it against building footprints from the aerial data before any tool relied on it.
- Some scans put their origin on an upper floor, which sank every 3D overlay by a storey until we fixed one height for the whole scene.
- A DiskANN index grown row by row had recall@10 of 0.0, so a TimescaleDB job now rebuilds it hourly.
- An agent turn once claimed "none of the checks ran" after twelve runs. That became the rubric grader.

## Accomplishments that we're proud of

- Every tool run through the real API on a 15-place demo set: 266 answers, 62 honest "cannot answer here", 1 error from a bad input, 0 judged wrong (from 29 wrong before the review pass).
- About 600 server tests and 90 web tests.
- Photoreal interiors trained on an integrated GPU.
- A phone reading reaches the desktop workspace in about a second.
- Adaptation, counted from the op logs: questions asked 1, 0, 0 and checks kept back 0, 3, 9 over three homes for one returning user.

## What we learned

- The value is in the join. Each layer alone answers little; the floor height from the air plus the sill from the scan answers the flood question.
- An agent is most useful when it never states a number. Choosing, asking and explaining is its job; measuring is the code's.
- Saying "this scan cannot tell" is a feature people trust more than a guess.
- Ask before you build. The question people really ask is "are there any steps?", not "is it accessible?", and "how deep is the garage?", not "is it a two-car garage?".

## Built with and credits

Our code was written during the event. Libraries and tools we used: FastAPI, Pydantic, Shapely, NumPy, LangChain deepagents, LangGraph, LangSmith, langchain-mcp-adapters, MongoDB MCP server, pymongo, pg8000, pgai, fastembed, Ollama (nomic-embed-text), Anthropic Claude, React, Vite, three.js, React Three Fiber, drei, Spark, MapLibre GL, deck.gl, Base UI, cmdk, Sonner, Vaul, NumberFlow, react-resizable-panels, zustand, Brush (splat training), NIST CFAST (fire model), Photon 2.0, ElevenLabs, Apple RoomPlan and ARKit, OpenStreetMap, USGS high-water marks. Data from CoStar, Matterport and Vexcel under the event's terms; none of it is in the repository.

