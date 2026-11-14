import { Suspense, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Tabs } from '@base-ui/react/tabs'
import {
  Scene, SceneBoundary, fetchRecord, focusFinding, panoFace, runToolHere, useBuildingView, useBuildings, useWorkspace,
  type Doc, type SceneMode, type ScanPlan, type Status,
} from '../../../core/index.ts'
import { PanelView } from '../blocks/blocks.tsx'
import { Copy, Empty, Icon, IconBtn, Menu, MenuBtn, RunState, Seg, SourceChip, St, Stats, StatusGlyph, ToolKey, type IconName } from '../design/ui.tsx'
import { dur, int, plural } from '../lib/format.ts'
import { facts } from '../lib/pending.ts'
import { go, goScan } from '../lib/place.ts'
import { FAMILIES, useTools, type ToolInfo } from '../lib/tools.ts'
import { useScheme } from '../shell/theme.ts'
import { useUi } from '../shell/store.ts'

const MODES: { id: SceneMode; label: string; icon: IconName; none: string }[] = [
  { id: 'dollhouse', label: '3D', icon: 'cube', none: '' }, { id: 'plan', label: 'Plan', icon: 'plan', none: '' },
  { id: 'pano', label: 'Inside', icon: 'walk', none: 'This scan has no 360° positions' }, { id: 'splat', label: 'Drone', icon: 'drone', none: 'No drone capture for this building' },
]
const WORST: Record<Status, number> = { fail: 0, warn: 1, unknown: 2, pass: 3 }
type F = Doc['findings'][number]

/** A menu of every tool that runs on one scan: the investigation's own first, then by family. */
export function RunToolMenu({ sid, trigger }: { sid: string; trigger: React.ReactElement }) {
  const tools = useTools().filter((t) => t.onScan && !t.planned)
  const mine = useWorkspace((s) => s.doc.tools)
  const item = (t: ToolInfo) => <Menu.Item key={t.id} onClick={() => runToolHere(t.id, sid)}><ToolKey id={t.id} title={t.title} />{t.title}{t.slow && <small>slow</small>}</Menu.Item>
  const own = tools.filter((t) => mine.some((m) => m.id === t.id))
  return (
    <MenuBtn align="end" trigger={trigger}>
      {own.length > 0 && <><div className="mh">In this investigation</div>{own.map(item)}<hr /></>}
      <div className="mh">All tools, by family</div>
      {FAMILIES.map((f) => {
        const list = tools.filter((t) => t.family === f.id)
        if (!list.length) return null
        return (
          <Menu.SubmenuRoot key={f.id}>
            <Menu.SubmenuTrigger><Icon name={f.icon} />{f.label}<small>{list.length}</small><Icon name="right" size={11} /></Menu.SubmenuTrigger>
            <Menu.Portal><Menu.Positioner sideOffset={2} alignOffset={-4} style={{ zIndex: 61 }}><Menu.Popup className="menu">{list.map(item)}</Menu.Popup></Menu.Positioner></Menu.Portal>
          </Menu.SubmenuRoot>
        )
      })}
      <hr />
      <Menu.Item onClick={() => go('tools')}><Icon name="tool" />Browse the tool catalogue</Menu.Item>
    </MenuBtn>
  )
}

function Overview({ plan, sid, panels, onResults }: { plan: ScanPlan; sid: string; panels: Doc['panels']; onResults: (panel: string) => void }) {
  const b = useBuildings((s) => s.all.find((x) => x.scans.some((y) => y.sid === sid)))
  const q = plan.quality
  const can: [string, boolean | undefined, string?][] = q ? [
    ['Walls', q.walls, q.walls_source === 'dxf' ? 'recovered from the drawing, not measured' : q.walls_confidence ? `${q.walls_confidence} confidence` : undefined],
    ['Room outlines', q.polygons], ['Doors and windows', q.openings], ['Room names', q.labels], ['Position on the map checked', q.georef],
  ] : []
  return (
    <div className="stack ins-pad">
      <Stats items={[
        { label: 'Rooms', value: int(plan.rooms.length) }, { label: 'Doorways', value: int(plan.openings.filter((o) => o.type === 'doorway').length) },
        { label: 'Floors', value: int(plan.floors.length) }, { label: '360° positions', value: int(plan.panos.length) },
      ]} />
      <section className="ins-sec">
        <h3>Results on this scan</h3>
        {panels.length === 0 ? <p className="muted">No tool has run here yet. Use “Run a tool” above, or ask the agent.</p> : (
          <ul className="rows">
            {panels.map((p) => {
              const v = p.blocks.find((x) => x.type === 'VerdictHeader')
              return <li key={p.id}><button type="button" onClick={() => onResults(p.id)}><ToolKey id={p.tool} title={p.title} /><span className="grow trunc">{p.title}</span>{v && v.type === 'VerdictHeader' && <St status={v.status} />}</button></li>
            })}
          </ul>
        )}
      </section>
      {can.length > 0 && (
        <section className="ins-sec">
          <h3>What this scan can answer</h3>
          <ul className="can">
            {can.map(([label, ok, note]) => <li key={label}><StatusGlyph status={ok ? 'pass' : 'unknown'} /><span className="grow">{label}{note && <span className="muted">, {note}</span>}</span><span className="muted">{ok ? 'yes' : 'no'}</span></li>)}
            <li><StatusGlyph status={plan.has.splat ? 'pass' : 'unknown'} /><span className="grow">Drone capture</span><span className="muted">{plan.has.splat ? 'yes' : 'no'}</span></li>
            <li><StatusGlyph status={plan.has.defurnished ? 'pass' : 'unknown'} /><span className="grow">Empty-room photos</span><span className="muted">{plan.has.defurnished ? 'yes' : 'no'}</span></li>
          </ul>
          {q?.notes?.map((n) => <p key={n} className="muted small">{n}</p>)}
        </section>
      )}
      <section className="ins-sec">
        <h3>Details</h3>
        <dl className="kv">
          <dt>Address</dt><dd>{plan.address || 'Not recorded'}</dd>
          {plan.city && <><dt>City</dt><dd>{plan.city}</dd></>}
          <dt>Kind</dt><dd style={{ textTransform: 'capitalize' }}>{plan.segment || 'Not recorded'}</dd>
          <dt>Scan id</dt><dd className="row"><span className="num">{sid}</span><Copy text={sid} label="Copy the scan id" /></dd>
          {plan.geo && <><dt>Position</dt><dd className="num">{plan.geo.lat.toFixed(5)}, {plan.geo.lon.toFixed(5)}</dd></>}
        </dl>
      </section>
      {b && b.scans.length > 1 && (
        <section className="ins-sec">
          <h3>Other scans at this address <span className="count">{b.scans.length - 1}</span></h3>
          <ul className="rows">{b.scans.filter((x) => x.sid !== sid).slice(0, 30).map((x) => <li key={x.sid}><button type="button" onClick={() => goScan(x.sid)}><Icon name="building" /><span className="grow trunc">{x.name}</span><span className="muted">{plural(x.rooms, 'room')}</span></button></li>)}</ul>
        </section>
      )}
    </div>
  )
}

function Evidence({ findings }: { findings: F[] }) {
  const current = useWorkspace((s) => s.doc.camera?.finding)
  const tools = useWorkspace((s) => s.doc.tools)
  if (!findings.length) return <Empty icon="target" title="No evidence on this scan yet">Each finding a tool makes is listed here and can be shown in the building.</Empty>
  return (
    <ul className="evid">
      {findings.map((f) => {
        const m = f.media?.find((x) => x.kind === 'pano'), [a, b, c] = m?.ref.split('/') ?? []
        return (
          <li key={f.id}>
            <button type="button" disabled={!f.anchor} aria-current={current === f.id || undefined} onClick={() => focusFinding(f, { stay: true })} title={f.anchor ? 'Show this in the building' : 'This finding has no place to show'}>
              {m && b ? <img src={panoFace(a, b, c ? Number(c) : 1)} alt="" loading="lazy" width={72} height={54} onError={(e) => { e.currentTarget.style.visibility = 'hidden' }} /> : <span className="ph hatch" />}
              <span className="grow">
                <span className="t"><StatusGlyph status={f.status} />{f.title}</span>
                {f.detail && <span className="s">{f.detail}</span>}
                <span className="m"><span className="muted">{tools.find((t) => t.id === f.tool)?.title ?? f.tool}</span><SourceChip source={f.source} /></span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

const words = (k: string) => k.replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (c) => c.toUpperCase())
const show = (v: unknown) => (v === true ? 'Yes' : v === false ? 'No' : String(v))
/** Leaves of a record, as rows. Long text and lists of objects are left to their own section. */
function leaves(o: unknown, path: string[] = [], out: [string, string][] = []): [string, string][] {
  if (o == null || out.length > 400) return out
  if (Array.isArray(o)) { if (o.length && o.every((x) => typeof x !== 'object')) out.push([path.map(words).join(' · '), o.join(', ')]); else o.slice(0, 12).forEach((x, i) => leaves(x, [...path, String(i + 1)], out)) }
  else if (typeof o === 'object') for (const [k, v] of Object.entries(o)) leaves(v, [...path, k], out)
  else if (o !== '') out.push([path.map(words).join(' · '), show(o)])
  return out
}
function Record({ sid }: { sid: string }) {
  const [rec, setRec] = useState<Record<string, unknown> | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [find, setFind] = useState('')
  useEffect(() => { let on = true; setRec(null); setErr(null); fetchRecord(sid).then((r) => on && setRec(r), (e: Error) => on && setErr(e.message)); return () => { on = false } }, [sid])
  const claims = (rec?.claims ?? {}) as Record<string, { value: unknown; unit: string | null; path: string }>
  const sections = useMemo(() => Object.entries(rec ?? {}).filter(([k]) => !['sid', 'claims', 'trimmed', 'match'].includes(k)).map(([k, v]) => [k, leaves(v)] as const).filter(([, rows]) => rows.length), [rec])
  if (err) return <Empty icon="record" title="No record for this scan">{err === 'Nothing there.' ? 'The scan is not matched to a property record or a listing.' : err}</Empty>
  if (!rec) return <div className="ins-pad stack">{[70, 40, 55, 35, 60].map((w, i) => <span key={i} className="sk" style={{ width: `${w}%` }} />)}</div>
  const hit = (s: string) => !find || s.toLowerCase().includes(find.toLowerCase())
  return (
    <div className="stack ins-pad">
      <section className="ins-sec">
        <h3>What the record says <SourceChip source={{ layer: 'costar', method: 'lookup', confidence: 'high' }} /></h3>
        {Object.keys(claims).length === 0 ? <p className="muted">The record makes no claim a scan can check.</p> : (
          <dl className="kv">
            {Object.entries(claims).map(([k, c]) => <div key={k} style={{ display: 'contents' }}><dt title={c.path}>{words(k)}</dt><dd>{c.value == null ? <span className="muted">not stated</span> : <><span className={typeof c.value === 'number' ? 'num' : undefined}>{show(c.value)}</span>{c.unit && <span className="muted"> {c.unit}</span>}</>}</dd></div>)}
          </dl>
        )}
        <p className="muted small">Run “Record versus reality” to check these against the scan.</p>
      </section>
      <section className="ins-sec">
        <h3>Full record</h3>
        <label className="inset"><Icon name="search" size={13} /><input className="field" value={find} onChange={(e) => setFind(e.target.value)} placeholder="Find a field" aria-label="Find a field in the record" /></label>
        {sections.map(([k, rows]) => {
          const shown = rows.filter(([a, b]) => hit(a) || hit(b))
          if (!shown.length) return null
          return (
            <details key={k} className="recsec" open={!!find || undefined}>
              <summary><Icon name="right" size={11} />{words(k)}<span className="count">{shown.length}</span></summary>
              <dl className="kv">{shown.map(([a, b], i) => <div key={i} style={{ display: 'contents' }}><dt>{a}</dt><dd>{b.length > 220 ? b.slice(0, 220) + '…' : b}</dd></div>)}</dl>
            </details>
          )
        })}
      </section>
    </div>
  )
}

function History({ sid, runs }: { sid: string; runs: Doc['runs'] }) {
  const tools = useWorkspace((s) => s.doc.tools), panels = useWorkspace((s) => s.doc.panels)
  return (
    <div className="stack ins-pad">
      <section className="ins-sec">
        <h3>Runs on this scan, in this investigation <span className="count">{runs.length}</span></h3>
        {!runs.length ? <p className="muted">Nothing has run on this scan in the open investigation.</p> : (
          <ul className="rows tall">
            {runs.map((r) => {
              const p = panels.find((x) => x.run === r.id), title = tools.find((t) => t.id === r.tool)?.title ?? r.label.split(' · ')[0]
              return (
                <li key={r.id}><button type="button" disabled={!p} onClick={() => p && useUi.setState({ panel: p.id })}>
                  <ToolKey id={r.tool} title={title} />
                  <span className="grow"><span className="trunc">{title}</span>{r.summary && <span className="s">{r.summary}</span>}</span>
                  {r.status === 'done' ? <span className="num muted">{dur(r.ms)}</span> : <RunState state={r.status} />}
                </button></li>
              )
            })}
          </ul>
        )}
      </section>
      <section className="ins-sec">
        <h3>Measured facts over time</h3>
        {facts.fetchFactHistory ? <FactHistory sid={sid} /> : <p className="note"><Icon name="info" size={13} /><span>Not connected yet. Every value a tool measures on this scan is kept in the facts database with its date, and this tab will list them once the app can read it.</span></p>}
      </section>
    </div>
  )
}
function FactHistory({ sid }: { sid: string }) {
  const [rows, setRows] = useState<Record<string, unknown>[] | null>(null)
  useEffect(() => { let on = true; facts.fetchFactHistory!(sid).then((r) => on && setRows(r), () => on && setRows([])); return () => { on = false } }, [sid])
  if (!rows) return <span className="sk" style={{ width: '60%' }} />
  if (!rows.length) return <p className="muted">No facts recorded for this scan yet.</p>
  return <dl className="kv">{rows.slice(0, 60).map((r, i) => <div key={i} style={{ display: 'contents' }}><dt>{String(r.field ?? '')}</dt><dd className="num">{String(r.value ?? '')} {String(r.unit ?? '')}</dd></div>)}</dl>
}

export function Building({ sid }: { sid: string }) {
  const doc = useWorkspace((s) => s.doc)
  const scheme = useScheme()
  const runs = useMemo(() => doc.runs.filter((r) => r.sid === sid), [doc.runs, sid])
  const panels = useMemo(() => doc.panels.filter((p) => p.sid === sid), [doc.panels, sid])
  const focused = doc.camera?.finding ? doc.findings.find((f) => f.id === doc.camera!.finding)?.tool : undefined
  // Which tools draw on the building. Left alone, it is the one result in view: the tool of the focused finding, else
  // the latest result. Five tools drawing at once cannot be read.
  const drawn = useMemo(() => [...new Set(doc.overlays.filter((o) => !o.sid || o.sid === sid).map((o) => o.tool))], [doc.overlays, sid])
  const [pick, setPick] = useState<string[] | null>(null)
  // The result in view: the one the person opened, else the focused finding's, else the latest. null is "none open".
  const [chosen, setChosen] = useState<string | null | undefined>(undefined)
  const inView = chosen !== undefined ? panels.find((p) => p.id === chosen) ?? null : (focused && panels.findLast((p) => p.tool === focused)) || panels.at(-1) || null
  const on = pick ?? (inView && drawn.includes(inView.tool) ? [inView.tool] : drawn)
  const v = useBuildingView(sid, on.length === drawn.length ? undefined : { tools: on })
  const b = useBuildings((s) => s.all.find((x) => x.scans.some((y) => y.sid === sid)))
  const [tab, setTab] = useState(() => (doc.panels.some((p) => p.sid === sid) ? 'results' : 'overview'))

  const findings = useMemo(() => {
    const mine = new Set(runs.map((r) => r.id))
    return doc.findings.filter((f) => (f.anchor && 'sid' in f.anchor && f.anchor.sid === sid) || (f.run && mine.has(f.run))).sort((x, y) => WORST[x.status] - WORST[y.status])
  }, [doc.findings, runs, sid])
  const working = runs.filter((r) => r.status === 'running' && !panels.some((p) => p.run === r.id))

  // A result that arrives while the person is on this scan is shown; so is the result of a focused finding.
  const count = panels.length, last = panels.at(-1)
  const mine = !!last && !doc.runs.find((r) => r.id === last.run)?.step
  useEffect(() => { setChosen(undefined) }, [count, doc.camera?.finding]) // a new result, or a finding focused: that is the one in view
  useEffect(() => {
    if (!count) return
    setTab('results')
    // a tool the person ran: the server's camera closes in on its worst finding, so frame the whole building again
    if (mine) { const t = setTimeout(v.stepBack, 900); return () => clearTimeout(t) }
  }, [count]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || /^(input|textarea|select)$/i.test(t.tagName) || document.querySelector('[cmdk-root], [role="dialog"], [role="menu"]')) return
      const m = MODES[Number(e.key) - 1]
      if (m && v.modes.includes(m.id)) v.setMode(m.id)
      else if (e.key.toLowerCase() === 'k') v.toggleKeep()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  })

  const i = b ? b.scans.findIndex((x) => x.sid === sid) : -1
  const tools = doc.tools
  const fault = (text: string): ReactNode => <div className="scene-state"><Empty icon="warn" title={text} action={<button className="btn" onClick={v.retry}>Try again</button>} /></div>

  return (
    <div className="bld">
      <header className="pagehead">
        <IconBtn icon="back" label="Back to the map" onClick={() => go('explore', { city: b?.metro ?? undefined, b: b?.id })} />
        <div className="ttl">
          <h2 className="trunc">{v.plan?.name ?? (v.error ? 'Scan not available' : <span className="sk" style={{ width: 180, display: 'inline-block' }} />)}</h2>
          <p className="muted trunc">{v.plan ? [(v.plan.address ?? '').split(',')[0], v.plan.city, plural(v.plan.rooms.length, 'room'), plural(v.plan.floors.length, 'floor')].filter(Boolean).join(' · ') : ' '}</p>
        </div>
        {b && b.scans.length > 1 && (
          <div className="pager" role="group" aria-label="Scans at this address">
            <IconBtn icon="left" label="Previous scan at this address" disabled={i <= 0} onClick={() => goScan(b.scans[i - 1].sid)} />
            <span className="muted">{i + 1} of {b.scans.length}</span>
            <IconBtn icon="right" label="Next scan at this address" disabled={i >= b.scans.length - 1} onClick={() => goScan(b.scans[i + 1].sid)} />
          </div>
        )}
        <RunToolMenu sid={sid} trigger={<button type="button" className="btn" disabled={!v.plan}><Icon name="play" size={13} />Run a tool<Icon name="down" size={11} /></button>} />
        <button type="button" className="btn" aria-pressed={v.kept} onClick={v.toggleKeep} disabled={!v.plan} title="Keep this scan in Buildings ( K )"><Icon name="keep" size={14} />{v.kept ? 'Kept' : 'Keep'}</button>
      </header>

      <div className="bld-body">
        <section className="work" aria-label="Building view">
          <div className="worktools">
            <Seg label="View" value={v.mode} onChange={v.setMode} options={MODES.map((m) => ({ id: m.id, label: m.label, icon: m.icon, disabled: !v.modes.includes(m.id), title: v.plan && !v.modes.includes(m.id) ? m.none : undefined }))} />
            <span className="grow" />
            {drawn.length > 0 && (
              <MenuBtn align="end" trigger={<button type="button" className="btn quiet" aria-label={`Overlays: ${on.length} of ${drawn.length} tools drawn on the building`}><Icon name={on.length ? 'eye' : 'eyeoff'} size={14} /><span className="lbl">Overlays</span><span className="count">{on.length} of {drawn.length}</span></button>}>
                <div className="mh">Draw on the building</div>
                {drawn.map((t) => (
                  <Menu.CheckboxItem key={t} checked={on.includes(t)} closeOnClick={false} onCheckedChange={(yes) => setPick(yes ? [...on, t] : on.filter((x) => x !== t))}>
                    <span className="mi-check"><Menu.CheckboxItemIndicator><Icon name="check" size={12} /></Menu.CheckboxItemIndicator></span>{tools.find((x) => x.id === t)?.title ?? t}
                  </Menu.CheckboxItem>
                ))}
                <hr />
                <Menu.Item closeOnClick={false} onClick={() => setPick(on.length === drawn.length ? [] : drawn)}>{on.length === drawn.length ? 'Hide all' : 'Show all'}</Menu.Item>
                {pick && <Menu.Item onClick={() => setPick(null)}>Follow the result in view</Menu.Item>}
              </MenuBtn>
            )}
            <IconBtn icon="expand" label="Show the whole building" onClick={v.stepBack} disabled={!v.plan} />
          </div>
          <div className="scene-host">
            {v.error && fault(v.error)}
            {!v.plan && !v.error && <div className="scene-state"><RunState state="running">Loading the plan</RunState></div>}
            {v.sceneProps && (
              <Suspense fallback={<div className="scene-state"><RunState state="running">Loading the building view</RunState></div>}>
                {/* keyed by scan and scheme: the scene builds its model for one plan and reads its colours when it mounts */}
                <SceneBoundary key={`${v.sceneKey}:${scheme}`} fallback={fault('The building view stopped on this scan.')}>
                  <Scene {...v.sceneProps} className="app-scene" />
                </SceneBoundary>
              </Suspense>
            )}
          </div>
        </section>

        <Tabs.Root className="insp" value={tab} onValueChange={(t) => setTab(String(t))} aria-label="Inspector">
          <Tabs.List className="tabs">
            <Tabs.Tab value="overview">Overview</Tabs.Tab>
            <Tabs.Tab value="results">Results{panels.length > 0 && <span className="count">{panels.length}</span>}{working.length > 0 && <i className="ring" />}</Tabs.Tab>
            <Tabs.Tab value="evidence">Evidence{findings.length > 0 && <span className="count">{findings.length}</span>}</Tabs.Tab>
            <Tabs.Tab value="record">Record</Tabs.Tab>
            <Tabs.Tab value="history">History{runs.length > 0 && <span className="count">{runs.length}</span>}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="overview" className="insp-body scroll">
            {v.plan ? <Overview plan={v.plan} sid={sid} panels={panels} onResults={(id) => { setChosen(id); setPick(null); setTab('results') }} />
              : v.error ? <Empty icon="building" title="Nothing to show for this scan" action={<button className="btn" onClick={() => go('explore')}>Back to the map</button>}>{v.error}</Empty>
              : <div className="ins-pad stack">{[60, 80, 45].map((w, k) => <span key={k} className="sk" style={{ width: `${w}%` }} />)}</div>}
          </Tabs.Panel>
          <Tabs.Panel value="results" className="insp-body scroll">
            {working.map((r) => <div key={r.id} className="b-loading working"><RunState state="running">{r.label.split(' · ')[0]}</RunState>{r.summary && <p className="muted small">{r.summary}</p>}<span className="sk" style={{ width: '64%' }} /></div>)}
            {panels.length === 0 && working.length === 0 && (
              <Empty icon="play" title="No results on this scan" action={<RunToolMenu sid={sid} trigger={<button type="button" className="btn solid">Run a tool<Icon name="down" size={11} /></button>} />}>
                Pick a tool to measure this scan. Its result, checks and evidence appear here, and it draws on the building.
              </Empty>
            )}
            {[...panels].reverse().map((p) => <PanelView key={p.id} panel={p} open={p.id === inView?.id} onOpen={(o) => { setChosen(o ? p.id : null); setPick(null) }} />)}
          </Tabs.Panel>
          <Tabs.Panel value="evidence" className="insp-body scroll"><Evidence findings={findings} /></Tabs.Panel>
          <Tabs.Panel value="record" className="insp-body scroll"><Record sid={sid} /></Tabs.Panel>
          <Tabs.Panel value="history" className="insp-body scroll"><History sid={sid} runs={runs} /></Tabs.Panel>
        </Tabs.Root>
      </div>
    </div>
  )
}
