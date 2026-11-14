import { useEffect, useMemo, useRef, useState } from 'react'
import { setQuery, useRoute, useWorkspace, type Block, type Doc, type Panel, type Status } from '../../core/index.ts'
import { fmt } from './lib.ts'
export { lensOverlays } from './lens.ts'

/* View state of this look that is not the product's: which sheet is on top (?c_p), whether the stack is folded
   (?c_fold), and what the sheet on top puts on the model. Everything is read from the workspace document. */

type Of<T extends Block['type']> = Extract<Block, { type: T }>
export const block = <T extends Block['type']>(p: Panel | null | undefined, type: T) => p?.blocks.find((b): b is Of<T> => b.type === type)

/** The sheets that belong to where the person is: this scan's on a building; on the city table, the ones about many
    places and those of the selected address (a site tool's result sends the view there to see its marks). */
export const panelsHere = (doc: Doc, sid: string | null, at: string[] = []) => doc.panels.filter((p) => (sid ? p.sid === sid : !p.sid || at.includes(p.sid)))

/** The sheet on top of the stack, and how to bring another one up. */
export function useSheet(sid: string | null, at: string[] = []) {
  const doc = useWorkspace((s) => s.doc)
  const { q } = useRoute()
  const atKey = at.join(',')
  const here = useMemo(() => panelsHere(doc, sid, at), [doc, sid, atKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const active = here.find((p) => p.id === q.get('c_p')) ?? here.at(-1) ?? null
  // a finding focused from the model, the plan or a link brings its own sheet to the top
  const focus = doc.camera?.finding
  useEffect(() => {
    const f = doc.findings.find((x) => x.id === focus)
    const p = f && (here.find((x) => f.run && x.run === f.run) ?? here.find((x) => x.tool === f.tool))
    if (p && p.id !== active?.id) setQuery({ c_p: p.id })
  }, [focus]) // eslint-disable-line react-hooks/exhaustive-deps
  // a sheet that has just been laid goes on top
  const count = useRef(here.length)
  useEffect(() => { if (here.length > count.current && q.get('c_p')) setQuery({ c_p: null }); count.current = here.length }, [here.length]) // eslint-disable-line react-hooks/exhaustive-deps
  return { here, active, pick: (id: string) => setQuery({ c_p: id, c_fold: null }), folded: q.get('c_fold') === '1', fold: (on: boolean) => setQuery({ c_fold: on ? '1' : null }) }
}

/** The one figure printed large on the mat: the measurement the focused finding is about, else the sheet's first
    metric. The value is the one in the block; nothing is worked out here. */
export type Headline = { value: number; unit: string; title: string; note?: string; status?: Status }
export function headline(doc: Doc, panel: Panel | null): Headline | null {
  if (!panel) return null
  const f = doc.findings.find((x) => x.id === doc.camera?.finding)
  const c = f && block(panel, 'CheckList')?.checks.find((x) => x.findings.includes(f.id) && x.measured != null)
  if (f && c) return { value: c.measured!, unit: c.unit, title: f.title, status: c.status, note: c.threshold != null ? `Limit ${fmt(c.threshold, 3)} ${c.unit}` : undefined }
  const m = block(panel, 'MetricRow')?.metrics.find((x) => x.value != null)
  return m ? { value: m.value!, unit: m.unit, title: m.label, note: panel.title, status: block(panel, 'VerdictHeader')?.status } : null
}

export function usePhone() {
  const [phone, set] = useState(() => window.matchMedia('(max-width: 760px)').matches)
  useEffect(() => { const m = window.matchMedia('(max-width: 760px)'); const on = () => set(m.matches); m.addEventListener('change', on); return () => m.removeEventListener('change', on) }, [])
  return phone
}
