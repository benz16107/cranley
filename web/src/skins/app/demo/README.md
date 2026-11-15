# Demo flows

The top bar's **Demo** menu plays a scripted flow on the real app: the agent's turns, tool runs, the camera and the
page's own buttons, with a caption for each step in a bar at the bottom right. The bar has Pause / Resume, Next
(end this step's caption now), the time since the start, and a close button that stops the flow.

A step that fails or takes too long runs its `else` step, or is skipped with a note in the bar, and the flow goes on.
Each play starts a new investigation under a fresh profile, so nothing a rehearsal taught the agent changes the next
play.

From the console: `thresholdDemo.play('costar')`, `thresholdDemo.stop()`. A link with `?play=costar` starts that flow
2.5 s after the page loads (`scripts/demo-record` uses this).

## Change a flow

A flow is one JSON file in `flows/`. Add, remove or edit a file: no code changes. `pnpm test` checks every file
(known steps, every `$name` defined in `vars`, a `tool` on each tool step) and names the line that is wrong. In `pnpm dev` the menu updates as
you save; for the laptop copy run `scripts/demo-sync` again (it rebuilds the web app).

```json
{
  "id": "costar",                       // the ?play= name, unique
  "track": "CoStar",                    // shown under the title in the menu; the menu is sorted by it
  "title": "Check a listing against the scan, then tour it",
  "about": "First caption, shown while the flow starts.",
  "vars": { "building": "<scan-id>" },  // "$building" anywhere below is replaced by this
  "steps": [
    { "do": "open", "sid": "$building", "say": "Caption while this step runs.", "hold": 2000 },
    { "do": "tool", "tool": "door_widths", "inputs": { "min_width_m": 0.81 },
      "else": { "do": "tool", "tool": "room_census" } }
  ]
}
```

To show a different tool in a flow, change `"tool"` (and its `"inputs"`) in a `tool` step, or the brief in an `ask`
step. The tool ids are the ones on the Tools page and at `GET /api/tools`; a tool with a required input that has no
default needs it in `inputs`: without it the app asks for it as a question, and the flow notes "did not run" and
moves on.

Every step may have:

| field | meaning |
|---|---|
| `say` | the caption while it runs; it stays until the next step's `say` |
| `hold` | ms to wait after the step before the next one (default 1500). Pause holds it, Next ends it |
| `timeout` | ms before the step counts as failed (default 30 000; `ask` and `answer` 150 000) |
| `else` | one step to run instead when this one fails or times out |

## Steps

| `do` | fields | what it does |
|---|---|---|
| `open` | `sid` (a scan), or `page`: `home`, `explore`, `investigations`, `investigation` (the open one), `buildings`, `insights`, `tools`, `settings`; `params` for the address | goes there |
| `ask` | `text`; `sid` to ask about one scan, `sids` for several; `answers` (a word of the question: the answer, e.g. `{ "seat": 20, "hours": 12 }`); `answer: false` to leave the agent's questions open; `approve: false` to leave its approval cards for a `click` step | one agent turn, waited to its end. Each question the agent asks takes the matching `answers` entry, else the answer on offer (as "Use the defaults" does), else the first choice; a number question with none of those stops the step. Approvals are run |
| `answer` | `answers`, `approve` | answers the open questions with their defaults and starts the investigation |
| `tool` | `tool`, `inputs`, `sid` (default: the scan in view), `open: false` to leave its result closed | runs one tool into the investigation and opens its result |
| `click` | `label`, `all: true` for every match, `within` (a CSS selector) | presses the page's own button whose label, title or text is `label` (exact first, then the start of it), waiting up to `timeout` for it to appear. Outlined for a moment so the audience sees it. Examples: `Play` then `Tour` (a menu: one click opens it, the next picks), `Run it`, `Download report` then `Everything in this investigation` |
| `type` | `into` (a CSS selector), `text` | types into a field |
| `focus` | `finding`: `first`, `worst`, an index or an id; `tool` to pick from one tool's findings | points the camera at a finding |
| `agent` | `open: false` to close | opens the agent panel |
| `firstrun` | | opens the guided first run's dialog |
| `share` | | makes a read-only link (MongoDB store only) and opens it in a second window |
| `window` | `url` (`here` for this page) | opens a second window. When the browser blocks it, the bar shows "Open the second window" |
| `new` | | a new investigation, keeping the profile (so the agent can search what came before) |
| `wait` | `ms`; or `for: "agent"` (the turn and its runs end); or `for: "<label>"` (a button appears) | waits |
| `say` | | only a caption |

## Offline

The laptop copy (`scripts/demo-up`) runs the server through `scripts/demo-llm`, which saves every model answer while
there is network and replays it when there is none. A recorded `ask` replays only when it is asked the same way
from the same code: rerun `scripts/demo-record` on linuxbox after changing a brief, then `scripts/demo-sync`. A flow
whose `ask` has no recording falls to its `else` step, so give every `ask` an `else` that runs a tool.

What needs the network whatever is recorded: the MongoDB flow's share link and search over past work (Atlas), and the
Tiger flow's database fork (Tiger Cloud). Both flows have `else` steps for that. The Explore map's street tiles come
from OpenFreeMap; open the map once on the laptop while online and the browser keeps the tiles it showed.
