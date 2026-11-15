---
title: "Photon: Build a Messaging Agent using Photon 2.0"
---

Prizes: winner, runner-up, and Best Voice Agent. Built on `ws/photon` (merged at `a8c7348`); details in `docs/PHOTON.md`.

**Angle.** Cranley on Photon works like texting or calling your real estate agent. You have a question about a place,
so you text or call, and it answers with measurements. The same number can act as your contractor, inspector, property
manager or accessibility advisor. The people who need a building checked are rarely at a desk: they are walking through
a viewing, driving to one, or standing in a doorway with a tape measure. The same agent and the same measuring tools
answer in iMessage and on a phone call.

| What a person does | Why it is a real use of Photon 2.0 |
|---|---|
| Asks in plain words, gets the floor plan picture marked with findings, the verdict, the measurements and a workspace link | Shared iMessage line, native replies, attachment upload, typing indicator |
| Replies to an earlier answer ("what about a 76 cm chair?") | The reply thread is the investigation (`parentMessageId` in and out) |
| Says "yes", "no" or "always" to a slow step | Approvals by native reply |
| Sends a photo of a doorway with a bank card, a ceiling photo, a short video, a voice note, a location | Inbound attachments, video, audio and vCard locations each run a tool |
| Types "visit" | Unsettled checks arrive one at a time; each reply settles one and the desktop workspace updates live |
| Types "report" | The PDF arrives in the chat, ready to forward |
| Turns "voice on" | Answers also arrive as native iMessage voice messages |
| Does nothing | The chat background becomes the building's plan; a National Weather Service alert at that building arrives once with their own flood result |
| Calls the number | An ElevenLabs agent over SIP runs the same checks by voice; the plan and link follow in iMessage after the call (Best Voice Agent) |

Rules it keeps: every sent line is built from the tool result, never from model text; a typed size needs a unit; only
rendered pictures leave the server; the main API stays private behind one signature-checked relay; each event is
handled once, in order per chat.

**State (4:20 am):** merged with 14 tests; the live line is up with sends limited to an allowlist; the voice line is
wired (`edbfc67`) and Ben made the first real call at about 4 am. A full live round trip is not confirmed yet.

**Demo path.** Text the line "will an F-150 fit in this garage?" with a building link, get the marked plan back, reply
"what about two?", then "report" for the PDF. For Best Voice: call, ask the same, hang up, show the iMessage that follows.
