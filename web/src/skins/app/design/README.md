# The App look

Sheet's materials with a product's structure: paper, ink, one drafting blue, one status scale, set at the density of
a tool a person works in all day. Tokens are in `tokens.css`, shared classes in `base.css`, shared components in
`ui.tsx`. Use them and add nothing ad hoc.

## Structure

- **Shell** (`shell/`): sidebar, top bar with breadcrumb and search, the page, and the agent's run panel beside any
  page. `lib/place.ts` maps the address to a page.
- **Pages** (`pages/`): Home, Explore, Building, Investigations, Buildings, Insights, Tools, Settings. A page is either
  a document that scrolls (`.page > .inner`) or a work surface that fills the window (`.listpage`, `.ex`, `.bld`).
  Home is two columns that fold into one under 1000 px of page width: on the left the field for a brief, the open
  investigation and its buildings as aerial photos; on the right the map of scanned addresses and one activity feed
  (runs, failures, questions, phone captures). What it lists is worked out in `lib/home.ts`. A building's picture is
  the 256 px aerial the server keeps on disk, one image per card, never a 3D view.
- **Blocks** (`blocks/`): the twelve panel blocks. A tool's result is only ever built from these.
- **Stand-ins** (`lib/pending.ts`, `lib/tools.ts`): what core does not give yet. Each part names the request that
  replaces it.

## Rules

1. **Colour comes from tokens.** A canvas that cannot read CSS variables (the map) resolves one with `tokenRgba`.
   The 3D scene gets its own hex copies in `pages/pages.css` (`.app-scene`), light and dark.
2. **One accent.** `--accent` is selection, focus, a link, or "the agent is working". Never decoration, never a status.
3. **One status scale**, always with its glyph (`<StatusGlyph>`, `<St>`): circle, triangle, square, dashed ring.
   `unknown` means "not measured" and is hatched (`.hatch`), never shown as a pass.
4. **Sizes.** 13 px for the interface and tables, 12 px secondary, 11 px captions. Titles are 13 to 15 px semibold.
   No number is set larger than 14 px: a value sits in a stat strip (`<Stats>`, `.b-metrics`) or a table cell.
5. **Numbers.** A measured value, an id or a coordinate is `.num` (Martian Mono). A count stays in the text face.
   Every number is tabular. Every measured number has a `<SourceChip>`. Numbers come from a result object and are
   printed as given; only the format is ours.
6. **Density.** Rows 32 px, controls 28 px, sidebar items 28 px; 44 and 40 px on a touch screen (`--row-h`,
   `--ctl-h`).
7. **Shape.** 3 px on controls, 5 px on what floats and on cards. Hairlines (`--rule`) for structure. A shadow
   (`--lift`) only on menus, popovers, dialogs and drawers. No coloured stripe on one side of anything: a selected
   row takes `--accent-wash`, a focused finding also takes an accent outline.
8. **Tables** are `<DataTable>`: sortable heads, `useColumns` for the column chooser, a count in the footer, "show
   more" past 200 rows, rows in the shape of the data while loading, an `<Empty>` when there is nothing. A rollup is
   a table whose cells carry their own bar (`td.barcell`).
9. **Loading is `.sk`** (flat bars in the shape of what is coming) or a `<RunState state="running">` line that says
   what is happening. No spinner stands alone. Hatching is never used for loading.
10. **Motion.** Menus and popovers scale from their trigger in 140 ms; drawers slide in 200 ms; a thing the agent
    adds arrives once (`.arrive`). Nothing moves on hover, and nothing opened from the keyboard animates. The flight
    between the two cities is the one long move. Reduced motion stops all travel.
11. **Words.** Sentence case. Plain sentences, the person's words ("doorway", not "opening"), no exclamation marks.
    A message about a failure says what to do next. When something is not connected, the page says so.
12. **Components come from what is installed**: Base UI (menu, popover, tooltip, tabs, dialog, switch, slider), cmdk,
    Sonner, Vaul, react-resizable-panels. Icons are Phosphor regular (`icons.ts`), one set.
13. **Panels resize by their edges** (`design/split.tsx`, on react-resizable-panels): the sidebar, the agent panel, a
    building's inspector, Explore's list and a drawer's sheet. No handle is drawn. The 8 px on the line two panes
    share take the pointer, and an accent line shows there under the pointer, during a drag and for keyboard focus
    (arrow keys, Home, End). A pane keeps its pixels when the window changes, is remembered per browser under
    `threshold.app.size.<id>`, and goes back to its designed size on a double click. A new side panel is a `<Pane>`
    in a `<Split>`, never a fixed grid column. On a phone a split is off and nothing drags.

## The design tells checklist

Trust gaps: there is no terms of service or privacy policy, and Home takes a free sentence. Settings says plainly what
is stored and sent, and that neither document exists yet. Add both before this faces the public. No testimonials, no
stand-in screenshots; loading uses skeleton rows.

Avoided: gradients, Lucide, a pure white ground, rainbow colour, shadows on everything, three feature cards, emoji,
frosted blur, Inter, Geist and Space Grotesk, coloured left stripes, bento grids, terminal mockups, checkmark bullets,
pricing tiers, soft radius everywhere, purple and black, glow orbs, dot grids, sparkles, animated arrows, hover
motion, neon, pastels, em dashes and "not X but Y" copy.

Partial, and why: Home's five needs sit three and two in bordered tiles at 1440 px. They are buttons that start an
investigation, with no icon and no marketing line, and one row of five on a wide page. The tool keys use seven hues, one per tool family; they are
18 px squares and the only place those hues appear.
