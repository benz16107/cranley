/* Which pane sizes to remember when a split's layout changes. Pure, so it runs under `node --test`. */

/** A pane of a split, as far as remembering goes: its id and the size in pixels it last had. */
export type Sized = { id: string; last?: number }

/** After a layout change: the panes whose size the person changed, with their new size in pixels. A pane the window
    squeezed, or one a neighbour's drag did not touch, is not among them, so it keeps the size the person chose for
    it. `layout` gives each pane's share of the split in percent, `all` is the split's size in pixels. Every pane's
    `last` is brought up to date. */
export function resized(panes: Iterable<Sized>, layout: Record<string, number>, all: number, byPerson: boolean): [id: string, px: number][] {
  const out: [string, number][] = []
  if (!all) return out
  for (const p of panes) {
    const share = layout[p.id]
    if (share == null) continue
    const px = (share / 100) * all
    if (byPerson && p.last != null && Math.abs(px - p.last) >= 1) out.push([p.id, px])
    p.last = px
  }
  return out
}

/** Where the focus goes when a drawer opens: into the sheet, not onto the edge that resizes it (the first thing in
    the popup that can take the focus). For the popup's `initialFocus`. */
export const sheetFocus = () => document.querySelector<HTMLElement>('.drawer :is(button, a[href], input, select, textarea)')
