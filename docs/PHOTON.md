# Cranley on Photon 2.0

Cranley checks real buildings for the people who have to live or work in them: will the truck fit the garage, can a
wheelchair reach the bathroom, how high does the water come. On Photon 2.0, the same agent and the same measuring tools
answer in iMessage and on a phone call, where those people already are: walking through a viewing, driving to one, or
standing in a doorway with a tape measure.

Code: `server/threshold/photon/` (bridge), `server/threshold/api/photon.py` (private routes), `server/scripts/setup_voice.py`
(ElevenLabs phone agent). Tests: `server/tests/photon/`.

## What a person can do

| They send | Cranley does | Photon 2.0 feature |
|---|---|---|
| A question in plain words ("will an F-150 fit in this garage?") | runs the composer and investigator (the web app's agent), answers with a picture of the floor plan marked with the result's findings, the verdict, the measurements and a link to the full workspace | shared iMessage line, native replies, attachment upload, typing indicator |
| A reply to an earlier answer ("what about a 76 cm chair?") | follows up in that answer's workspace, not the newest one: the thread is the investigation | `parentMessageId` in and out |
| "yes" / "no" / "always" | approves or skips a slow or invasive step the agent asked about first (a smoke simulation, reading every panorama) | native replies |
| A photo of a doorway with a bank card in it | measures the clear width (`photo_measure`) | inbound attachments, download |
| A photo of a ceiling ("is there a smoke alarm?") | checks it with the vision reader | inbound attachments |
| A short video | runs the walkthrough tool | inbound video (Nov 7) |
| A voice note | transcribed, then treated as words | inbound audio |
| Their location, or a map link | finds the nearest scanned building and opens a workspace on it | inbound vCard attachment |
| "visit" | the checks the scan could not settle arrive one at a time; each reply (a measurement or a photo) settles one, and the desktop workspace updates live | replies, attachments |
| "report" | the site report as a PDF in the chat, ready to forward to a landlord | attachment upload |
| "voice on" | each answer also arrives as a native iMessage voice message | `voice` content (Nov 7) |
| (nothing) | the chat's background becomes the plan of the building being discussed | `space.background.update` (Nov 7) |
| (nothing) | a National Weather Service alert at that building is texted once, with what their own flood check said | send into an open thread |
| A phone call to Cranley's number | an ElevenLabs agent over SIP runs the same checks by voice; when the call ends, the plan, the lines and the link arrive in their iMessage thread | Voice on a Photon number, SIP profile, `call.ended` |

## Rules it keeps

- **Numbers never pass through model text.** Every line Cranley sends is built from the tool result's verdict,
  metrics and checks (`photon/words.py`). The agent's own note is passed on only when it holds no digits. The phone agent
  is told to read the `say` field as written; that field is built the same way.
- **A size a person types is read from their words**, deterministically: "70 cm" or "28 in" with a unit; a bare "70"
  is refused, not guessed.
- **Only rendered results leave the server.** The plan picture is drawn by Cranley (headless Chrome over an SVG we
  generate); no panorama or data file is ever sent.
- **The main API is not public.** One small relay (`photon/webhook.py`) is the only thing on the internet: it answers
  `/photon/webhook` after checking Photon's Standard Webhooks signature, and `/voice/tool/<name>` after checking a shared
  secret, and forwards to the API on localhost with an internal token. Everything else is 404.
- **Shared-line limits are handled.** Photon's free iMessage line can only answer people who texted first and may
  refuse a late send; a refused answer waits and is delivered on the person's next message.
- **Every event is handled once** (Photon may deliver twice), in order per chat, on a worker pool, so the webhook
  answers in milliseconds while an agent turn takes about a minute.

## Run it

```sh
cd server
uv run uvicorn threshold.api.app:app --host 127.0.0.1 --port 8911      # the private API
uv run python -m threshold.photon.webhook --port 8912                   # the relay
sudo tailscale funnel --bg --https=8443 http://127.0.0.1:8912          # only the relay is public
uv run python scripts/setup_voice.py                                    # the ElevenLabs phone agent and tools
```

Keys live in `$THRESHOLD_DATA_DIR/.env`: `PHOTON_API_KEY`, `PHOTON_PROJECT_ID`, `PHOTON_WEBHOOK_SECRET`,
`PHOTON_INTERNAL_TOKEN`, `VOICE_TOOL_SECRET`, `ELEVENLABS_API_KEY`, `PHOTON_APP_URL`. `PHOTON_SENDS=on` lets messages
leave; `PHOTON_ALLOW` limits answers to listed numbers while testing.
