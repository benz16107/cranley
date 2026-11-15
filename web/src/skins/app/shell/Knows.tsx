import { useEffect, useState } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { useCatalog, useRoute, userOp } from '../../../core/index.ts'
import { Empty, Icon } from '../design/ui.tsx'
import { Sheet } from '../design/split.tsx'
import { sheetFocus } from '../lib/split.ts'
import { FIRST_RUN_KEY } from '../lib/firstrun.ts'
import { become, loadPerson, mark, openKnows, usePerson, type Fact, type Note } from '../lib/person.ts'
import { useUi } from './store.ts'
import './knows.css'

/* What Cranley knows about the person, and every place that knowledge was used. Three parts, used across the look:
   - <Knows />        the page of it: each fact with where it came from, a way to change or forget it, and how the
                      investigations have gone, measured.
   - <Because />      "because you" chips: on a run's result, and for the whole investigation in the agent panel.
   - <Marks />        Useful / Not relevant on a check.
   The server writes every sentence and every number here (agent/profile.py); this file only lays them out. */

const forget = (f: Pick<Fact, 'key' | 'label'>) => userOp({ op: 'pref.set', key: f.key, label: f.label, value: null })

/** The count on the way in: facts about the person, not corrections to one building. */
export function useKnown() { return usePerson((s) => (s.person?.facts.length ?? 0) + (s.person?.who ? 1 : 0)) }

/** The way into the page, with how much is known. Hidden on a read-only link: that work is someone else's. */
export function KnowsButton({ className = 'btn sm quiet' }: { className?: string }) {
  const n = useKnown(), shared = useCatalog((s) => !!s.shared)
  if (shared) return null
  return <button type="button" className={className} onClick={() => { useUi.setState({ panel: null }); openKnows() }} title="What Cranley knows about you, and where each thing came from"><Icon name="user" size={13} />Cranley knows{n > 0 && <span className="count">{n}</span>}</button>
}

function FactRow({ f }: { f: Fact }) {
  const [editing, setEditing] = useState(false)
  const [v, setV] = useState('')
  const num = f.edit?.type === 'number' || f.edit?.type === 'integer'
  const save = () => {
    const value = num ? Number(v) : v.trim()
    if (v.trim() === '' || (num && !Number.isFinite(value))) return
    userOp({ op: 'pref.set', key: f.key, label: f.label, value: f.edit?.type === 'integer' ? Math.round(value as number) : value, unit: f.unit ?? undefined, from: 'You changed it in what Cranley knows' })
    setEditing(false)
  }
  return (
    <li>
      <div className="grow">
        <span className="k">{f.label}</span>
        {editing ? (
          <form className="row" onSubmit={(e) => { e.preventDefault(); save() }}>
            {f.edit?.options
              ? <select className="field" value={v} onChange={(e) => setV(e.target.value)} aria-label={f.label} autoFocus>{f.edit.options.map((o) => <option key={o}>{o}</option>)}</select>
              : <input className="field" inputMode={num ? 'decimal' : undefined} value={v} onChange={(e) => setV(e.target.value)} aria-label={f.label} style={num ? { width: 96 } : undefined} autoFocus />}
            {f.unit && <span className="muted">{f.unit}</span>}
            <button className="btn sm solid">Save</button><button type="button" className="btn sm quiet" onClick={() => setEditing(false)}>Cancel</button>
          </form>
        ) : <span className="v"><b className={typeof f.value === 'number' ? 'num' : undefined}>{f.shown}</b>{f.unit && <> {f.unit}</>}</span>}
        <small>{f.why.charAt(0).toUpperCase() + f.why.slice(1)}.</small>
      </div>
      {!editing && f.edit && <button type="button" className="btn sm quiet" aria-label={`Change: ${f.label}`} onClick={() => { setV(String(f.value)); setEditing(true) }}>Change</button>}
      {!editing && <button type="button" className="btn sm" aria-label={`Forget: ${f.label} ${f.shown}`} onClick={() => forget(f)}>Forget</button>}
    </li>
  )
}

/** "Questions asked: 4, then 1, then 0". One value per investigation, oldest first, as the server counted them. */
function Adapted() {
  const p = usePerson((s) => s.person), loading = usePerson((s) => s.loading)
  if (!p) return null
  if (!p.adapted.length) return <p className="kn-none">{loading ? 'Counting.' : 'After a second investigation this shows how each one went: what was asked, what was reused, what was kept back.'}</p>
  return (
    <>
      <dl className="kn-adapt">
        {p.adapted.filter((r) => r.values.some((x) => x != null)).map((r) => (
          <div key={r.id}><dt>{r.label}</dt><dd>{r.values.map((x, i) => <span key={i}>{i > 0 && <span className="muted">, then </span>}<b className="num">{x ?? 'none'}</b></span>)}</dd></div>
        ))}
      </dl>
      <p className="kn-foot">Counted from the logs of {p.sessions.length === p.investigations ? `your ${p.sessions.length} investigations` : `your first investigation and your latest ${p.sessions.length - 1}`}, oldest first. Nothing here is written by the model.</p>
    </>
  )
}

/** The page of what is known, over the current page. Open from the agent panel, Home or Settings. */
export function Knows() {
  const open = usePerson((s) => s.open), p = usePerson((s) => s.person), loading = usePerson((s) => s.loading)
  const about = p?.facts.filter((f) => f.group === 'about') ?? [], matters = p?.facts.filter((f) => f.group === 'matters') ?? []
  useEffect(() => { if (open) void loadPerson(true) }, [open])
  const as = useRoute().q.get('as') // a link that opens the app as a named person
  useEffect(() => {
    if (!become(as)) return
    // someone opened by name is not on a first run: the guide does not open over their page
    try { localStorage.setItem(FIRST_RUN_KEY, '1') } catch { /* it asks on the next visit */ }
    if (useUi.getState().first === 'ask') useUi.setState({ first: null })
  }, [as])
  return (
    <Dialog.Root open={open} onOpenChange={(o) => openKnows(o)}>
      <Dialog.Portal>
        <Dialog.Backdrop className="backdrop" />
        <Dialog.Popup className="drawerwrap" aria-label="What Cranley knows about you" initialFocus={sheetFocus}>
          <Sheet>
            <header>
              <Icon name="user" />
              <Dialog.Title render={<h2 className="trunc" />}><b>Cranley knows</b></Dialog.Title>
              <Dialog.Close render={<button className="btn icon quiet" aria-label="Close" />}><Icon name="close" /></Dialog.Close>
            </header>
            <div className="body knows">
              <p className="kn-lede">What you have told Cranley, kept between investigations so a new one does not ask again. Each line says where it came from. Change or forget any of it.</p>
              {!p && loading && <div className="kn-sec"><span className="sk" style={{ width: '62%' }} /><span className="sk" style={{ width: '44%' }} /><span className="sk" style={{ width: '52%' }} /></div>}
              {/* once there are two investigations to compare, how they went leads: it is what the rest is for */}
              {p && p.adapted.length > 0 && <section className="kn-sec"><h3>How Cranley has adapted to you</h3><Adapted /></section>}
              {p && !p.who && !p.facts.length && <Empty icon="user" title="Nothing yet">Answer a question, change a setting, remove a tool or mark a check. It is kept here, with where it came from.</Empty>}
              {p?.who && (
                <section className="kn-sec">
                  <h3>Who you are</h3>
                  <ul className="kn-list"><li><div className="grow"><span className="v"><b>{p.who.title}</b></span><small>{p.who.said}</small></div><button type="button" className="btn sm" aria-label="Forget who you are" onClick={() => forget({ key: 'who.persona', label: 'Who you are' })}>Forget</button></li></ul>
                </section>
              )}
              {about.length > 0 && <section className="kn-sec"><h3>About you</h3><ul className="kn-list">{about.map((f) => <FactRow key={f.key} f={f} />)}</ul></section>}
              {matters.length > 0 && <section className="kn-sec"><h3>What matters to you</h3><ul className="kn-list">{matters.map((f) => <FactRow key={f.key} f={f} />)}</ul></section>}
              {p && !p.adapted.length && (p.who || p.facts.length > 0) && <section className="kn-sec"><h3>How Cranley has adapted to you</h3><Adapted /></section>}
              {p && p.on_buildings > 0 && <p className="kn-foot">{p.on_buildings} more {p.on_buildings === 1 ? 'correction belongs' : 'corrections belong'} to one building each (a room’s name, a check you rejected). They are listed under Learned in that investigation.</p>}
              <p className="kn-foot">Kept on the Cranley server under an id held in this browser. Anyone using this browser sees it.</p>
            </div>
          </Sheet>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
/** One "because you" chip: what was done, then when the person said so. The whole source is its title and on the
    page it opens. */
function Chip({ n }: { n: Note }) {
  return (
    <li>
      <button type="button" className="because" onClick={() => openKnows()} title={`${cap(n.why)}. Open what Cranley knows about you.`}>
        <Icon name="user" size={12} /><span className="grow"><span className="t">{n.text}</span><small>{cap(n.when)}</small></span>
      </button>
    </li>
  )
}
/** The chips for one run's result (`run`), or for the whole investigation (the agent panel). */
export function Because({ run }: { run?: string }) {
  const notes = usePerson((s) => s.notes)
  const mine = run ? notes.filter((n) => n.kind === 'input' && n.runs?.includes(run)) : notes.filter((n) => n.kind !== 'first')
  if (!mine.length) return null
  if (run) return <ul className="becauses" aria-label="Because of what Cranley knows about you">{mine.map((n) => <Chip key={n.kind + n.key} n={n} />)}</ul>
  return (
    <section className="rp-sec kn-used" aria-label="Because of what Cranley knows about you">
      <header><h3>Because of what Cranley knows about you</h3><span className="count">{mine.length}</span></header>
      <ul className="becauses">{mine.map((n) => <Chip key={n.kind + n.key} n={n} />)}</ul>
    </section>
  )
}

/** Checks of a kind the person marked useful: id -> why they are listed first. */
export function useFirst(): Map<string, string> {
  const notes = usePerson((s) => s.notes)
  const out = new Map<string, string>()
  for (const n of notes) if (n.kind === 'first') for (const id of n.findings ?? []) out.set(id, n.why)
  return out
}

/** Useful / Not relevant on one check. Not relevant hides the others of its kind too; the toast counts them. */
export function Marks({ id, title }: { id: string; title: string }) {
  const shared = useCatalog((s) => !!s.shared)
  if (shared) return null
  return (
    <span className="marks">
      <button type="button" className="btn sm quiet" aria-label={`Useful: ${title}`} onClick={() => void mark(id, 'useful')}>Useful</button>
      <button type="button" className="btn sm quiet" aria-label={`Not relevant: ${title}`} onClick={() => void mark(id, 'not_relevant')}>Not relevant</button>
    </span>
  )
}
