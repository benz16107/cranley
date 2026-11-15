import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Popover } from '@base-ui/react/popover'
import { Command } from 'cmdk'
import { ask, compose, search, startOver, useBuildings, useCatalog, useWorkspace, type Building } from '../../../core/index.ts'
import { Icon } from '../design/ui.tsx'
import { homeBuildings, starterBuildings } from '../lib/home.ts'
import { usePerson } from '../lib/person.ts'
import { go, goScan } from '../lib/place.ts'
import { KnowsButton } from '../shell/Knows.tsx'
import { useIsPhone, useUi } from '../shell/store.ts'
import { Aerial } from './Aerial.tsx'
import { STARTS, type Start } from './starts.ts'

/** Which building the brief is about. Closed it is one quiet button in the field's bar; open it is a search over the
    scanned addresses. Before anything is typed it offers the buildings of the open work, or a few to try. */
function At({ value, onChange, back }: { value: Building | null; onChange: (b: Building | null) => void; back: React.RefObject<HTMLTextAreaElement | null> }) {
  const [open, setOpen] = useState(false), [q, setQ] = useState('')
  const all = useBuildings((s) => s.all), state = useBuildings((s) => s.state), load = useBuildings((s) => s.load)
  const doc = useWorkspace((s) => s.doc)
  const hits = useMemo(() => (q.trim().length >= 2 ? search(all, q, 8) : []), [all, q])
  const offer = useMemo(() => {
    const of = (sids: string[]) => [...new Set(sids.flatMap((sid) => all.find((b) => b.scans.some((s) => s.sid === sid)) ?? []))]
    const mine = of(homeBuildings(doc, all, 5).map((b) => b.sid))
    return mine.length ? { label: 'From your work', list: mine } : { label: 'Scanned addresses to try', list: of(starterBuildings(all, 5).map((b) => b.sid)) }
  }, [doc, all])
  const typed = q.trim().length >= 2, list = typed ? hits : offer.list
  const pick = (b: Building) => { onChange(b); setOpen(false) }
  return (
    <span className="ask-at" data-picked={value ? '' : undefined}>
      <Popover.Root open={open} onOpenChange={(o) => { setOpen(o); if (o) setQ('') }}>
        <Popover.Trigger className="btn quiet" aria-label={value ? `About ${value.address}. Change the building.` : 'Choose a building or address'}>
          {value ? <Aerial lat={value.lat} lon={value.lon} /> : <Icon name="building" size={14} />}
          <span className="trunc">{value ? value.address : 'Any building'}</span>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Positioner sideOffset={6} align="start" style={{ zIndex: 60 }}>
            <Popover.Popup className="pop ask-pop" finalFocus={back}>
              <Command shouldFilter={false} label="Find a building" loop>
                <Command.Input value={q} onValueChange={setQ} placeholder="Address or building name" />
                <Command.List>
                  {state === 'loading' && <div className="ask-wait" aria-busy="true">{[62, 48, 70].map((w) => <span key={w} className="sk" style={{ width: `${w}%` }} />)}</div>}
                  {state === 'error' && <p className="ask-miss">The building list did not load. <button type="button" className="link" onClick={load}>Try again</button></p>}
                  {state === 'ready' && typed && hits.length === 0 && <p className="ask-miss">No scanned building matches “{q.trim()}”. Try a street name, or browse the map.</p>}
                  {list.length > 0 && (
                    <Command.Group heading={typed ? 'Buildings' : offer.label}>
                      {list.map((b) => (
                        <Command.Item key={b.id} value={b.id} onSelect={() => pick(b)}>
                          <Aerial lat={b.lat} lon={b.lon} />
                          <span className="grow"><span className="trunc">{b.address}</span><small className="trunc">{[b.city, b.count === 1 ? b.scans[0]?.name : `${b.count} scans`].filter(Boolean).join(' · ')}</small></span>
                        </Command.Item>
                      ))}
                    </Command.Group>
                  )}
                  <Command.Group>
                    <Command.Item value="map" onSelect={() => go('explore')}><Icon name="map" size={14} /><span className="grow">Browse the map</span><span className="kbd">G E</span></Command.Item>
                  </Command.Group>
                </Command.List>
              </Command>
            </Popover.Popup>
          </Popover.Positioner>
        </Popover.Portal>
      </Popover.Root>
      {value && <button type="button" className="btn sm icon quiet" aria-label="Any building" title="Any building" onClick={() => { onChange(null); back.current?.focus() }}><Icon name="close" size={11} /></button>}
    </span>
  )
}

/** What Cranley already knows, said in one line under the field. The server wrote every word and value in it. */
function Known() {
  const person = usePerson((s) => s.person)
  if (!person || (!person.who && person.facts.length === 0)) return null
  const about = person.facts.filter((f) => f.group === 'about').slice(0, 2)
  return (
    <p className="ask-known">
      <KnowsButton className="btn sm" />
      <span className="trunc">
        {person.who?.title}
        {about.map((f) => <span key={f.key}> · {f.label} <span className="num">{f.shown}{f.unit ? ` ${f.unit}` : ''}</span></span>)}
      </span>
    </p>
  )
}

/** Home's one entry: say what you need, about any building or about one. A sentence alone composes a workspace (the
    tools and questions arrive on this page). A sentence about a building opens that building and asks there. A
    building alone opens it. Keyboard: C comes here from anywhere on the page, Enter starts, Down from an empty field
    walks the starting points, Escape gives the keys back to the page. */
export function Ask({ first, returning }: { first: boolean; returning: boolean }) {
  const [text, setText] = useState(''), [at, setAt] = useState<Building | null>(null), [from, setFrom] = useState<Start | null>(null)
  const live = useCatalog((s) => s.live)
  const phone = useIsPhone()
  const field = useRef<HTMLTextAreaElement>(null), starts = useRef<HTMLUListElement>(null)
  const said = text.trim()

  const send = () => {
    if (at) {
      const sid = at.scans[0]?.sid
      if (!said || !sid) { if (at.scans.length === 1 && sid) goScan(sid); else go('explore', { city: at.metro ?? undefined, b: at.id }); return }
      // a new brief is a new investigation, here about one building: the agent works where the person can see it
      startOver(); goScan(sid)
      if (!phone) useUi.getState().setRun(true)
      void ask(said)
      return
    }
    if (said) void compose(said, from && from.sentence === said ? from.need : undefined)
  }
  // On a first visit starting is the one thing to do, so the field has the focus. With work open it does not: the
  // single-key shortcuts (G E, the agent panel) must keep working on arrival. Not on a phone: it raises the keyboard.
  useEffect(() => { if (first && !phone && !document.querySelector('[role="dialog"]')) field.current?.focus({ preventScroll: true }) }, [first, phone])
  useEffect(() => {
    const key = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.key.toLowerCase() !== 'c' || e.metaKey || e.ctrlKey || e.altKey || /^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable || document.querySelector('[role="dialog"], [role="menu"]')) return
      e.preventDefault(); field.current?.focus()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])
  const start = (s: Start) => {
    setText(s.sentence); setFrom(s)
    const el = field.current
    if (el) { el.focus(); requestAnimationFrame(() => el.setSelectionRange(s.sentence.length, s.sentence.length)) }
  }
  const walk = (e: KeyboardEvent, i: number) => {
    const all = [...(starts.current?.querySelectorAll('button') ?? [])]
    const next = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? all[i + 1] : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? all[i - 1] ?? field.current : e.key === 'Escape' ? field.current : undefined
    if (next) { e.preventDefault(); next.focus() }
  }

  return (
    <section className="ask" aria-labelledby="ask-h">
      <h1 id="ask-h">{returning ? 'Welcome back. What do you need this time?' : 'What do you need from a building?'}</h1>
      <form className="ask-field" onSubmit={(e) => { e.preventDefault(); send() }}>
        <textarea ref={field} rows={2} value={text} onChange={(e) => setText(e.target.value)} aria-label="Who you are and what you need" aria-keyshortcuts="C"
          placeholder={at ? 'Is this one workable for a wheelchair?' : 'I use a wheelchair and I am choosing a one-bedroom apartment in Houston'}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() }
            else if (e.key === 'ArrowDown' && !text) { e.preventDefault(); starts.current?.querySelector('button')?.focus() }
            else if (e.key === 'Escape') e.currentTarget.blur()
          }} />
        <div className="ask-bar">
          <At value={at} onChange={setAt} back={field} />
          <span className="grow" />
          <button className="btn solid" disabled={!said && !at}>{at && !said ? 'Open building' : 'Start'}<span className="kbd">Enter</span></button>
        </div>
      </form>
      <Known />
      {live === false && <p className="note"><Icon name="info" size={13} /><span>The agent server is not answering. A starting point below plays back a recorded composition; only the step-free access investigation runs.</span></p>}
      <div className="ask-starts">
        <h2 id="starts-h">Start as</h2>
        <ul ref={starts} aria-labelledby="starts-h">
          {STARTS.map((s, i) => (
            <li key={s.id}>
              <button type="button" onClick={() => start(s)} onKeyDown={(e) => walk(e, i)} aria-pressed={from?.id === s.id && from.sentence === said} title={s.sentence}>
                <b>{s.who}</b><span>{s.sentence}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
