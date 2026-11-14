# Threshold design system: "Sheet"

The product is drawn as a survey sheet and an architect's drawing set. Light is ink on drafting paper. Dark is
a blueprint: pale line on Prussian blue. The stage (map or building) is the sheet. Everything else is a pane
laid on it.

Tokens are in `tokens.css`, shared classes in `base.css`, shared components in `ui.tsx`. Use them and add
nothing ad hoc. If a token is missing, say so in your report and the shell workstream adds it.

## Why this direction

Two directions were rendered over the real map (`web/design-lab/sheet.html` and `instrument.html`).
"Instrument" (dark, amber readouts, a reticle) was rejected for three reasons. Its amber accent is the same
colour as the caution status, so the one colour would mean two things. Its glow-on-black look is what a
generic agent dashboard looks like. And the building view is line drawings and photographs, which read as
drawings on paper and as a video game on black. "Sheet" keeps a dark scheme, as the blueprint.

## Rules other workstreams must follow

1. **Colour comes from tokens.** No hex values in components. A canvas that cannot read CSS variables (the
   map, three.js) resolves a token with `tokenRgba('--ink')` or `tokenCss('--ink')` from `ui.tsx`, and
   resolves it again when the scheme changes.
2. **One accent.** `--accent` (drafting blue) means selected, focused, a link, or "the agent is here".
   It is never decoration and never a status.
3. **One status scale.** `--pass`, `--warn`, `--fail`, `--unknown`, always with the glyph from
   `<StatusGlyph>`: circle, triangle, square, dashed ring. Status is never shown by colour alone.
   `unknown` means "not measured". Draw it hatched (`.hatch`), never as a pass.
4. **One data ramp.** `--ramp-1` (low) to `--ramp-6` (high) for any quantity on the map, plan or a chart.
   Do not invent a second ramp or use status colours for a quantity.
5. **One hue per tool.** `toolHue(id)` gives a tool's colour. Use it for the tool's key (`<ToolKey>`), and
   for outlines of its pins and overlays. Do not fill large areas with it.
6. **Every number carries a source chip.** `<SourceChip source={…} />` beside any measured or counted value:
   which data layer, which method, how confident. Numbers come from a tool result object. Text written by a
   model never supplies a number.
7. **Type.** Archivo for words: `.label` (narrow capitals) for field names, normal width for text, wide
   only for the cover sheet headline. Martian Mono, class `.num`, for anything measured, counted or
   located. Sizes from `--text-*` only. Sentence case everywhere except `.label`.
8. **Shape.** Radius is `--r-1` (2 px). Panes have a hairline edge and no shadow. Only things that float
   (popovers, callouts, the phone sheet) take `--lift`. Separate with rules (`--rule`), not with cards
   inside cards. No coloured stripe on one side of a row: a selected row takes `--accent-wash` and an accent
   outline.
9. **Motion.** Durations and curves from `--dur-*` and `--ease-*`. Things the agent adds arrive once
   (`.arrive`, 260 ms, 6 px). Nothing the user placed moves. Keyboard actions do not animate. The flight
   between the two cities is the one long move. Under `prefers-reduced-motion` nothing travels.
10. **Loading is hatching** (`.skeleton`), in the shape of what is coming. No spinners.
11. **Panels are built from the twelve blocks** in `web/src/skins/sheet/blocks/blocks.tsx`. A tool does not draw its
    own panel. If a block is missing something, ask for it; do not build a thirteenth.
12. **Hit areas** are at least 40 px on desktop and 44 px on the phone, even when the visible control is
    smaller. Focus is always visible (`:focus-visible`, 2 px accent).
13. **Words.** Plain sentences, the user's words for things ("doorway", not "opening"), no exclamation
    marks, no em dashes. A message that reports a failure says what to do next.

## Contrast (WCAG ratio on the pane colour)

| Token | Light | Dark |
|---|---|---|
| `--ink` | 15.6 | 13.3 |
| `--ink-2` | 7.3 | 8.0 |
| `--ink-3` | 5.3 | 5.3 |
| `--accent` | 7.7 | 7.6 |
| `--pass` / `--warn` / `--fail` | 5.1 / 4.7 / 6.3 | 8.4 / 8.3 / 6.9 |
| `--tool-1` to `--tool-8` | 4.8 to 6.6 | 7.0 to 8.9 |

`--rule` and `--rule-strong` are hairlines (below 3:1). They never carry state on their own.

## The design tells checklist

Hit on purpose: none of the trust-gap tells apply to an internal tool, except that the app has no terms or
privacy page. It collects no name or email. Add both before it faces the public.

Avoided: gradients, Lucide (icons are Phosphor, one set), pure white ground, shadows on everything,
three feature cards, emoji, frosted blur, Inter/Geist/Space Grotesk, coloured left stripes, bento grids,
terminal mockups, checkmark bullets, pricing tiers, soft radius everywhere, purple and black, glow orbs, dot
grids, sparkles, animated arrows, hover motion (hover changes colour only), neon, pastels, em dashes and
"not X but Y" copy.

Partial, and why: the metric row can hold three numbers side by side. It is a ruled row of a table with a
source chip per cell, not three cards, and it holds one to four. The dark scheme is blue on dark blue, which
is the blueprint the direction is named for; it has no purple and no glow.
