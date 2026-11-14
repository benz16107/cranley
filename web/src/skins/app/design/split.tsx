import { createContext, use, useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { Group, Panel, Separator, usePanelRef, type PanelImperativeHandle } from 'react-resizable-panels'
import { resized, type Sized } from '../lib/split.ts'

/* Panels that resize by their edges, on react-resizable-panels. Nothing is drawn for a handle: an edge shows an
   accent line while the pointer is on it, while it is dragged, and while it has the keyboard's focus (arrow keys
   resize, Home and End go to the limits). A pane keeps its size in pixels when the window changes, remembers it per
   browser under `threshold.app.size.<id>` (so Settings' "Reset" clears it), and a double click on its edge puts it
   back to the size it was designed at. On a phone a Split is `off`: its panes are plain elements and nothing drags. */

const KEY = 'threshold.app.size.'
const kept = new Map<string, number | null>()
const read = (id: string) => {
  if (!kept.has(id)) { let v = 0; try { v = Number(localStorage.getItem(KEY + id)) } catch { /* private window */ } kept.set(id, v > 0 ? v : null) }
  return kept.get(id) ?? undefined
}
const write = (id: string, px: number | null) => {
  kept.set(id, px)
  try { if (px == null) localStorage.removeItem(KEY + id); else localStorage.setItem(KEY + id, String(Math.round(px))) } catch { /* not remembered */ }
}

type Size = number | string
/** One pane of a live Split: how to read its size now, the size it last had, and how to put it back. */
type Entry = Sized & { ref: RefObject<PanelImperativeHandle | null>; size: Size }
const Live = createContext<Set<Entry> | null>(null) // null outside a Split, and inside one that is off
const panes = new Map<string, Entry>()

export function Split({ className, vertical, off, children }: { className?: string; vertical?: boolean; off?: boolean; children: ReactNode }) {
  const [mine] = useState(() => new Set<Entry>())
  const el = useRef<HTMLDivElement>(null)
  if (off) return <div className={className} data-plain="">{children}</div>
  return (
    <Live value={mine}>
      <Group className={className} elementRef={el} orientation={vertical ? 'vertical' : 'horizontal'} resizeTargetMinimumSize={{ coarse: 20, fine: 8 }}
        // Only a size the person changed is remembered: a pane the window squeezed keeps the width they chose for it.
        // The sizes come from the layout given here; a pane asked for its size during a key press still says the old one.
        onLayoutChanged={(layout, meta) => {
          const all = (vertical ? el.current?.clientHeight : el.current?.clientWidth) ?? 0
          for (const [id, px] of resized(mine, layout, all, meta.isUserInteraction)) write(id, px)
        }}>{children}</Group>
    </Live>
  )
}

/** A pane with a size of its own: a sidebar, an inspector, a drawer. `size` is the designed size, in pixels or as
    a share of the split ("44%"). `fixed` holds it at that size: its edges do not drag. */
export function Pane({ id, size, min, max, fixed, className, children }: { id: string; size: Size; min?: Size; max?: Size; fixed?: boolean; className?: string; children: ReactNode }) {
  const live = use(Live), ref = usePanelRef()
  useEffect(() => {
    if (!live) return
    // its size now, when the split has laid it out; a pane added later is not laid out yet, and the split's next
    // layout tells us (asking it sooner throws)
    let last: number | undefined
    try { last = ref.current?.getSize().inPixels } catch { /* not laid out yet */ }
    const e: Entry = { id, ref, size, last }
    live.add(e); panes.set(id, e)
    return () => { live.delete(e); if (panes.get(id) === e) panes.delete(id) }
  }, [live, id, size, ref])
  if (!live) return className ? <div className={className}>{children}</div> : <>{children}</>
  return <Panel id={id} panelRef={ref} className={className ? `pane ${className}` : 'pane'} defaultSize={fixed ? size : read(id) ?? size} minSize={fixed ? size : min} maxSize={fixed ? size : max} disabled={fixed} groupResizeBehavior="preserve-pixel-size">{children}</Panel>
}

/** The pane that takes what the others leave: the page, the 3D view, the map. */
export function Fill({ id, min, className, children }: { id: string; min?: Size; className?: string; children: ReactNode }) {
  if (!use(Live)) return <>{children}</>
  return <Panel id={id} className={className ? `pane ${className}` : 'pane'} minSize={min}>{children}</Panel>
}

/** A drawer's sheet: it lies along the right of the window and resizes by its left edge. It goes inside a popup of
    class `drawerwrap`, which covers the window and lets a click beside the sheet through to the backdrop. */
export function Sheet({ children }: { children: ReactNode }) {
  return (
    <Split className="sheet" off={window.matchMedia('(max-width: 760px)').matches}>
      <Fill id="beside">{null}</Fill>
      <Edge of="drawer" label="Resize the drawer" />
      <Pane id="drawer" size={480} min={360} max="92%" className="drawer">{children}</Pane>
    </Split>
  )
}

/** The edge between two panes. `of` names the pane it sizes: a double click puts that pane back to its designed size. */
export function Edge({ of, label }: { of: string; label: string }) {
  if (!use(Live)) return null
  // the library's own double click goes back to the size the pane mounted with, which here is the remembered one
  return <Separator className="edge" aria-label={label} disableDoubleClick onDoubleClick={() => { const e = panes.get(of); if (e) { write(of, null); e.ref.current?.resize(e.size) } }} />
}
