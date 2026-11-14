# Design studies (design v2, part 1)

Three directions for the product, each shown on the same three moments of one real investigation. They are routes in
the app and they run on the real API, the real map and the real scene (`web/src/scene`). The shell is not changed:
`main.tsx` loads this folder only when the path starts with `/study`.

```
/study                         index
/study/<a|b|c>/door            the front door
/study/<a|b|c>/city            the city with the agent at work
/study/<a|b|c>/building        one building under investigation, with a result
```

Arrow keys step through the nine screens. Reference research and the diagnosis of the current design are in the data
folder: `shots/design2/refs/NOTES.md` and `shots/design2/DIAGNOSIS.md`.

## What is real and what is staged

Real, read at run time: the building feed (`/api/buildings`), each house's plan (`/api/scan/{sid}/plan`), the drone
splat, the panoramas and the dollhouse (all through `<BuildingScene>`), and every number on screen. The numbers come
from `accessAudit` in `fixtures/access.ts` (the shell's in-browser stand-in for the access tool) and go from its
result object to the screen. Sentences that contain numbers are templates filled from that object.

Staged: the moment itself. The city screens freeze a run at "6 of 10 houses read" (`READ` in each direction); the
agent is not connected. The prompt field, the tool list and the view switch are drawn but do nothing.

Only scan ids are in this folder. Addresses, counts and widths are fetched.

## The three directions

| | A. Overflight | B. Broadsheet | C. Maquette |
|---|---|---|---|
| Idea | One camera shot from the city down to a doorway. The picture never leaves the screen. | A page the agent writes about a building. The verdict is the headline. | A model on a cutting mat that you take apart. |
| Setting | Dark only. The stage is always a photograph, a splat or a night map, and those read best on black. | Light only. It is a printed page; the 3D stage takes the paper's colour so the model sits in the layout. | One ground, the green of a cutting mat. White card for everything laid on it. |
| Signature | The measurement drawn in the photograph it came from, with one number at 236 px tied to the doorway by a line. The agent speaks in subtitles. | The headline with the measured number under a yellow marker, and each claim tied to a numbered figure. | Tags on strings: every finding is a cut-corner tag tied to the thing it measures. Tools are sheets laid over the model. |
| Type | Big Shoulders Display 800 (figures), Instrument Serif italic (the agent's voice), Archivo (labels) | Newsreader (headline and text), Archivo capitals (captions), Martian Mono (figures) | Archivo at 62% width, weight 900 (mat print), Martian Mono (tags) |
| Scale | 236 px over 12 px | 64 to 88 px over 11.5 px | 248 px over 12 px |
| Colour | Warm white on black. Colour only for the status scale. | Ink on paper, one marker yellow, one pencil blue for the agent and the route. | Mat green, card white, tape yellow for the route and the agent. |

The status scale is the same in all three and is never colour alone: circle pass, triangle within 5 cm, square fail,
dashed ring not measured.

## Motion, for the four moments that matter

Curves: ease-out `cubic-bezier(0.23, 1, 0.32, 1)` for things arriving, ease-in-out `cubic-bezier(0.77, 0, 0.175, 1)` for
things moving on screen. Nothing uses ease-in. Keyboard actions do not animate. Under `prefers-reduced-motion` nothing
travels: positions jump and only opacity changes.

**A. Overflight**

1. *Arriving at a building.* No cut. The map flies to the house (2400 ms, ease-in-out, pitch 58 to 70 degrees). Over the
   last 600 ms the map fades out and the splat fades in, with a 3 px blur on both to hide the seam. The splat then
   drifts at 3 degrees a second until touched. Going inside is the scene's own flight (1250 ms).
2. *The agent finds something.* The subtitle changes by crossfade (200 ms out, 320 ms in, 3 px blur). The figure
   counts from the limit down to the measured width (NumberFlow, 900 ms). The tape draws across the doorway left to
   right (420 ms, ease-out), then the leader line draws from the figure to the doorway (700 ms, 200 ms later).
3. *A tool is added.* Its name appears in the dock; the dock widens with a critically damped spring (350 ms, no
   bounce). Its layer fades into the picture in 260 ms. Nothing else moves.
4. *The route or the water appears.* The route draws from the entrance at a constant 6 m per second of real distance,
   linear, and each doorway's width lands as the line passes it. Water rises linearly at 0.25 m per second with its
   depth counting beside it, and stops without overshoot.

**B. Broadsheet**

1. *Arriving at a building.* The map shrinks into the corner as a key map (600 ms, ease-in-out, a shared element).
   The model rises out of the page: walls grow from the floor to the cut height (900 ms, ease-out).
2. *The agent finds something.* The headline is reset: the old line fades (160 ms), the new one fades in (260 ms),
   then the marker sweeps behind the number from left to right (460 ms, ease-out, 240 ms later). Its figure slides up
   8 px and fades in (260 ms).
3. *A tool is added.* A word joins the masthead and a rule draws under it from the left (240 ms). Its section is set
   into the page line by line, 60 ms apart.
4. *The route or the water appears.* The route is inked at constant speed, like a pen. Water is a flat blue wash
   that rises with a tide line; the depth is printed at the line and counts in centimetres.

While the agent works, one thing moves: a pale blue sweep across the line it is reading (2.4 s, linear, repeating).
Unread lines are hatched rules in the shape of what is coming.

**C. Maquette**

1. *Arriving at a building.* The chosen sheet lifts 6 px (200 ms), moves to the centre and the model is raised from
   its plan: the scene's plan-to-dollhouse move (1000 ms, ease-in-out).
2. *The agent finds something.* A tag drops onto its string from 12 px above (260 ms, ease-out, no bounce) and the
   string draws down to the doorway (180 ms). The figure on the mat counts to the width.
3. *A tool is added.* A sheet slides in from the right edge over the stack (320 ms, ease-out) and settles 1.4 degrees
   off square. The sheet under it dims to 60%.
4. *The route or the water appears.* The route is a strip of tape unrolled from the entrance (constant 6 m per
   second). Water is a sheet of blue acetate lowered onto the model, then raised to the level.

Built in the studies today: the subtitle arrival, the leader line, the marker sweep, the reading sweep, the pulsing
mark on the house being read, press feedback (`scale(0.96)`), and everything the scene already animates. The rest is
described here and not built.

## Design tells (`~/.claude/rules/design-tells.md`), walked for each

Clean in all three: no colour gradients, no Lucide, no pure white, no rainbow, no three feature cards, no emoji, no
frosted blur, no Inter, Geist or Space Grotesk, no coloured left stripes, no bento grid, no terminal mockup, no
checkmark bullets, no pricing tiers, no purple, no glow orbs, no sparkles, no animated arrows, no neon, no pastels,
no em dashes, no "not X but Y" lines. Headlines carry a fact: a count or a width.

On purpose:

- A: one rounded object, the dock. Black-to-clear scrims at the top and bottom edges so type reads on a photograph.
  Text shadow on the subtitle for the same reason, as film subtitles do.
- C: a line grid, because it is the mat (and in the building view it is the scene's real 1 m grid). Hard offset
  shadows and slight rotation on the paper cards, because they are things lying on a table. Hover lifts a sheet 6 px
  on devices that can hover.
- Trust gaps: there is still no terms or privacy page. The prompt field takes a free sentence about the user, so both
  are needed before this faces the public.

## Libraries (`~/.claude/rules/ui-libraries.md`)

Nothing hand-built that a library ships: the studies use what is installed (NumberFlow, MapLibre, deck.gl, the
scene). Three font packages were added: `@fontsource-variable/newsreader`, `@fontsource-variable/big-shoulders-display`,
`@fontsource/instrument-serif` (all OFL-1.1). When a direction is built for real, the dock's prompt is `cmdk` and the
phone sheet is `vaul`, both already installed.
