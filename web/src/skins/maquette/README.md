# Maquette: a model on a table

Direction C of the design studies, built as a complete look at `/c`. The product is a model-maker's table. The city
is a table of white blocks. A building is a white card model cut open. Everything the agent or a tool produces is a
thing laid on the table. This file is the look's rules; use them and add nothing ad hoc.

## The metaphor has to do work

Each physical thing stands for one product idea, and makes it clearer than a panel would.

| Thing on the table | What it is in the product | Why it is clearer |
|---|---|---|
| A tag on a string | A finding (`pins`, a clearance on a route) | The scene places each pin at its anchor; the tag's string comes down to a foot on that exact doorway. Number and status mark always, words when there are few, on hover, and always for the current one. |
| Yellow tape | The route, the agent, "this one" | One colour for one meaning: where to go and where to look. The route in the model and on a plan, the block the agent is reading, the current tag, the current check, the current print. |
| A sheet of tracing paper | The sheet on top of the stack is a lens | Only that tool's marks are on the model, and a tab on the sheet's top edge names it. Five tools' overlays are never drawn at once. |
| Blue acetate | Water | The scene raises the water to the tool's level; depth tags are blue. |
| A photo print | A photograph a finding was judged from | The print of the finding being looked at lies on the table, taped, with a thread to its tag in the model. "Stand here" enters the 360° photo at the place it was taken. |
| Two prints beside the model | The doors into the 360° interior and the drone capture | They are real thumbnails of what is behind them. Inside either, the table is put away and one strip of tape leads back (so does Escape). |
| The job ticket (near edge) | Brief, plan, live runs, questions, learned, kept, the ask line | One object. A line each while it runs; the rest behind a press. |
| The stack (far edge) | Tools, why each is here, result sheets | One object. The tool in use is the solid tab on top. |

## The table

The study's mat was green (`#1f5c4a`). Real photographs were laid on six candidate surfaces, each also through a
rough projector simulation (lifted blacks, lower contrast and saturation): a 360° interior, a drone photo and an
aerial patch of one house. Result: `shots/skins/maquette/00-surface-test-real-photos.png` in the data folder.

- Green: lawn and trees in the photographs go dull against it, and the projector simulation shifts it to mint.
- Pale mat and greyboard: white card nearly disappears, which is the whole idea gone.
- Mid grey: photographs are right, white print on the mat is weak under a projector.
- **Deep slate `#2c3532`**: chosen. Photographs keep their colour, white card and prints carry a room, and a splat's
  soft edge fades into it. It keeps a trace of the cutting mat's green.

A photograph is never placed straight on the mat except where it is the whole view (inside the 360° photo, the
drone capture) or the model's own ground. Everywhere else it has a paper border: `.mq-pic`, `.mq-printlet`,
`.mq-found`, the two door prints.

## Tokens (`tokens.css`)

| Token | Use |
|---|---|
| `--mat`, `--mat-low`, `--mat-high` | the table; recesses (water on the city table); raised patches (parks) |
| `--print`, `--print-2`, `--line`, `--line-2` | what is printed on the mat, and its grid |
| `--card`, `--card-2`, `--ink`, `--ink-2`, `--rule` | card and paper, and what is written on them |
| `--tape`, `--tape-ink` | the one accent |
| `--water` | acetate |
| `--pass`, `--warn`, `--fail`, `--unknown` | the status scale, always with `<Glyph>` |
| `--ramp-lo`, `--ramp-hi` | the one quantity ramp: card to pencil blue |
| `--lie`, `--lift` | paper lying on the table; paper picked up (popovers, hover) |
| `--cut` | a tag's cut corner |
| `--ease-out`, `--ease-in-out` | arriving; moving on screen. Nothing eases in. |

The map and the 3D scene cannot read CSS variables. `City.tsx` (`MAT`, `CARD`, `TAPE`) and `scene.css`
(`--scene-*`) repeat the same values; change them together.

## Rules

1. **Print or paper.** Text is either printed on the mat (`--print`, capitals, tracked) or written on card
   (`--ink`). Print that sits over a photograph (the model's ground, a panorama) gets a strip of mat under it.
2. **Square.** Card and paper have square corners. A tag has one cut corner. Nothing is a pill.
3. **Shadows say height.** `--lie` for anything lying on the table, `--lift` for anything picked up. No other shadow.
4. **Slight rotation, once.** A sheet or print may sit up to 2 degrees off square. Controls never rotate.
5. **Type.** Archivo Variable: weight 900 at 62% width for the one large figure, 750 at 88% for titles on card,
   capitals with 0.12 to 0.18em tracking for print. Martian Mono for anything measured or counted (`.mq-num`).
6. **One large figure.** `<Big>`: the measurement the focused finding is about, else the first metric of the sheet
   on top, else a count. It is the value in the block, never worked out here.
7. **Status is shape and colour.** Circle, triangle, square, dashed ring. "Not measured" is hatched or a dashed
   ring, never a pass.
8. **Sources.** `<Src>` under every number: layer, method, confidence pips; the note opens on press.
9. **Buttons** are pieces of card (`.mq-btn`), tape for the one main action (`.is-tape`). Press is `scale(0.97)`.
10. **Loading** is a hatch in the shape of what is coming, or a line of tape. No spinner.

## Motion

Curves and durations are in `tokens.css` and `maquette.css`. Keyboard actions and the catalog do not animate.

| Moment | What moves |
|---|---|
| Arriving at the front door | the count runs up; the five sheets settle 60 ms apart |
| A tool is added | its tab slides in from the far edge and settles off square (320 ms); at the front door its sheet does |
| The work begins | the door holds 2.8 s so the sheets and reasons are seen, then goes to the table |
| The agent finds something | a tag drops onto its string (260 ms) and the string draws (180 ms); the figure counts to the value; the print drops in and its thread appears |
| A sheet is laid | it slides in from the far edge (320 ms); the lens tab follows |
| The route appears | on a plan, tape is unrolled from the entrance (700 ms, linear). In the model the scene draws it. |
| Water | the scene raises it to the level |
| Between views | the scene's own flights; the table's furniture is put away and brought back around them |

`prefers-reduced-motion`: nothing travels; opacity only. Pulses and the unrolling tape stop.

## What is restyled from the shared scene (`scene.css`)

Only `--scene-*` variables and `th-` classes. Pins become hang tags; chips become pieces of card; the scene's cut
and floor controls are hidden and driven from this look's own (`Model.tsx`); its legend, scale bar, note and inset
plan are moved clear of the stack. The scene's `frame` keeps the model clear of the figure and the open sheet, and
`onCamera` ends the thread on a finding that has no tag.

## Design tells, walked

Clean: no gradients for colour, no Lucide (Phosphor paths), no pure white, no rainbow, no feature-card row, no
emoji, no frosted blur, no Inter, Geist or Space Grotesk, no left stripes, no bento, no terminal mockup, no checkmark
bullets, no pricing tiers, no purple, no glow orbs, no sparkles, no animated arrows, no neon, no pastels, no em
dashes in copy.

On purpose:
- A line grid at the front door: it is the mat.
- Hatching for "loading" and "not measured": the drafting convention, and the only repeating pattern.
- Slight rotation and a hover lift on paper: things on a table. Hover motion is limited to things that can be
  picked up (sheets, prints, view cards) and gated to devices that hover.
- Trust gap, not fixed here: there is no terms or privacy page, and the front door takes a sentence about the
  person. Both are needed before this faces the public. That is the product's, not one look's.

## Libraries

Base UI (popover, slider, switch), cmdk (the catalog, Ctrl K), vaul (the phone drawer), Sonner (notices, as slips
of paper), NumberFlow (the large figure), MapLibre and deck.gl (the table of blocks). Nothing hand-built that one of
these ships.
