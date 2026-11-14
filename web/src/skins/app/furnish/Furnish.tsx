/* Furniture a person tries in a room: a small catalogue in the building's toolbar, and a card for the piece that is
   selected. The scene draws the pieces, lets them be dragged and measures them (<Scene furnish>); this file keeps
   the list and prints what the scene reports. Nothing here goes to the server or outlives the page. */
import { useMemo } from 'react'
import { create } from 'zustand'
import type { SceneProps } from '../../../core/index.ts'
import { Icon, IconBtn, Menu, MenuBtn, SourceChip, St, Stats } from '../design/ui.tsx'
import './furnish.css'

type Furnish = NonNullable<SceneProps['furnish']>
type Piece = Furnish['items'][number]
type Check = Parameters<NonNullable<Furnish['onReport']>>[0][number]

/* Length, depth and height in metres: common North American sizes, typed in. A piece is drawn at exactly its size. */
const CATALOGUE: { group: string; items: [label: string, model: string, length: number, depth: number, height: number][] }[] = [
  { group: 'Living room', items: [['Sofa, three seats', 'furniture/sofa', 2.13, 0.97, 0.86], ['Sectional sofa', 'furniture/sectional', 2.8, 1.65, 0.86], ['Armchair', 'furniture/armchair', 0.9, 0.9, 0.86], ['Coffee table', 'furniture/coffee-table', 1.2, 0.6, 0.45], ['Upright piano', 'furniture/piano', 1.52, 0.64, 1.27]] },
  { group: 'Bedroom', items: [['Twin bed', 'furniture/bed-single', 1.91, 0.97, 0.6], ['Queen bed', 'furniture/bed-double', 2.03, 1.52, 0.6], ['King bed', 'furniture/bed-double', 2.03, 1.93, 0.6], ['Crib', 'furniture/crib', 1.37, 0.76, 0.9], ['Wardrobe', 'furniture/wardrobe', 1.2, 0.6, 2]] },
  { group: 'Dining and study', items: [['Dining table and four chairs', 'furniture/dining-set', 1.83, 1.6, 0.95], ['Desk', 'furniture/desk', 1.4, 0.7, 0.75], ['Bookshelf', 'furniture/bookshelf', 0.9, 0.3, 1.8]] },
  { group: 'Appliances', items: [['Refrigerator', 'furniture/fridge', 0.91, 0.86, 1.78], ['Washer', 'furniture/washer', 0.69, 0.76, 0.97]] },
]
const num = (v: number) => v.toFixed(2) // the scene's own chips print two decimals; the card matches them
const SOURCE = { layer: 'matterport', method: 'geometry', confidence: 'medium', note: 'Worked out in this browser from the scan\'s walls and doorways, as an empty room. The scan does not record which way a door opens, so both sides of every doorway are kept clear.' } as const

const useStore = create<{ pieces: Record<string, Piece[]>; selected: string | null; checks: Check[] }>(() => ({ pieces: {}, selected: null, checks: [] }))
const setPieces = (sid: string, items: Piece[]) => useStore.setState((s) => ({ pieces: { ...s.pieces, [sid]: items }, ...(items.length ? {} : { selected: null, checks: [] }) }))

/** What <Scene furnish> takes for this scan: null until a piece is added, so a scan with no furniture costs nothing. */
export function useFurnish(sid: string): Furnish | null {
  const items = useStore((s) => s.pieces[sid]), selected = useStore((s) => s.selected)
  return useMemo(() => (items?.length ? { items, selected, onChange: (next) => setPieces(sid, next), onSelect: (id) => useStore.setState({ selected: id }), onReport: (checks) => useStore.setState({ checks }) } : null), [sid, items, selected])
}

/** The catalogue. `off` says why a piece cannot be added right now (furniture is placed in the 3D view). */
export function FurnishMenu({ sid, off }: { sid: string; off?: string }) {
  const count = useStore((s) => s.pieces[sid]?.length ?? 0)
  const add = (label: string, model: string, size: [number, number, number]) => {
    const id = `${model}.${Date.now().toString(36)}`
    setPieces(sid, [...(useStore.getState().pieces[sid] ?? []), { id, label, model, size, center: null, yaw_deg: 0 }])
    useStore.setState({ selected: id })
  }
  return (
    <MenuBtn align="end" trigger={<button type="button" className="btn quiet" disabled={!!off} title={off ?? 'Try a piece of furniture in a room'}><Icon name="plus" size={13} /><span className="lbl">Furniture</span>{count > 0 && <span className="count">{count}</span>}<Icon name="down" size={11} /></button>}>
      {CATALOGUE.map((g) => (
        <div key={g.group} role="group" aria-label={g.group}>
          <div className="mh">{g.group}</div>
          {g.items.map(([label, model, l, d, h]) => <Menu.Item key={label} onClick={() => add(label, model, [l, d, h])}>{label}<small className="num">{num(l)} × {num(d)} m</small></Menu.Item>)}
        </div>
      ))}
      <hr />
      <p className="fz-fine">A piece stands where you are looking. Drag it on the floor; R turns it, Delete removes it.</p>
      {count > 0 && <Menu.Item onClick={() => setPieces(sid, [])}>Remove all furniture</Menu.Item>}
    </MenuBtn>
  )
}

function verdict(c: Check): string {
  const t = c.turning, said: string[] = []
  if (c.through) said.push('It stands in a wall.')
  if (c.doors.length) said.push(`It stands where ${c.doors.length > 1 ? `${c.doors.length} doors swing` : 'a door swings'}.`)
  if (t?.blocked) said.push(`It leaves no room to turn a wheelchair here: the largest clear circle is ${num(t.after)} m and a turn needs ${num(t.need)} m.`)
  if (said.length) return said.join(' ')
  if (!c.room) return 'It is outside every room in the scan.'
  return t && t.before < t.need ? `Clear of walls and doors. This room is too small for a ${num(t.need)} m wheelchair turn even when empty.` : 'Clear of walls and doors, and a wheelchair can still turn in this room.'
}

/** The selected piece: what it blocks, its room on each side, and the three things to do with it. */
export function FurnishCard({ sid }: { sid: string }) {
  const piece = useStore((s) => s.pieces[sid]?.find((p) => p.id === s.selected)), c = useStore((s) => s.checks.find((x) => x.id === s.selected))
  if (!piece || !c) return null
  const all = () => useStore.getState().pieces[sid] ?? []
  const turn = (by: number) => setPieces(sid, all().map((p) => (p.id === piece.id ? { ...p, yaw_deg: (p.yaw_deg + by + 360) % 360 } : p)))
  const side = (v: number | null) => (v == null ? 'open' : num(v))
  return (
    <aside className="fz-card" aria-label={`Furniture: ${piece.label}`}>
      <header>
        <St status={c.status}>{c.status === 'pass' ? 'Clear' : 'In the way'}</St>
        <b className="trunc">{piece.label}</b>
        <span className="num muted">{num(piece.size[0])} × {num(piece.size[1])} × {num(piece.size[2])} m</span>
        <span className="grow" />
        <IconBtn icon="undo" label="Turn 15° to the left" kbd="R" className="btn icon quiet sm" size={13} onClick={() => turn(15)} />
        <IconBtn icon="rerun" label="Turn 15° to the right" kbd="Shift R" className="btn icon quiet sm" size={13} onClick={() => turn(-15)} />
        <IconBtn icon="trash" label="Remove this piece" kbd="Del" className="btn icon quiet sm" size={13} onClick={() => { setPieces(sid, all().filter((p) => p.id !== piece.id)); useStore.setState({ selected: null }) }} />
        <IconBtn icon="close" label="Done with this piece" kbd="Esc" className="btn icon quiet sm" size={13} onClick={() => useStore.setState({ selected: null })} />
      </header>
      <p role="status">{verdict(c)}</p>
      <Stats items={[
        ...(['front', 'back', 'left', 'right'] as const).map((k) => ({ label: `${k[0].toUpperCase()}${k.slice(1)} to wall`, value: <span className="num">{side(c.sides[k])}</span>, unit: c.sides[k] == null ? undefined : 'm' })),
        ...(c.turning ? [{ label: 'Clear circle', value: <span className="num">{num(c.turning.after)}</span>, unit: 'm' }] : []),
      ]} />
      <footer><SourceChip source={SOURCE} /><span className="muted">Measured on the plan as you drag. Sizes are common ones, not yours.</span></footer>
    </aside>
  )
}
