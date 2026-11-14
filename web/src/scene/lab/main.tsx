// scene-lab: load any scan id and exercise every view and every overlay kind. The scene workstream's test bench.
import { StrictMode, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BuildingScene } from '../BuildingScene.tsx'
import { buildModel, sightBlocked } from '../model.ts'
import { useSceneLink } from '../store.ts'
import type { Mode, Pick, ScanPlan, View } from '../types.ts'
import { SAMPLE_KINDS, SAMPLE_LABEL, sampleOverlays, type SampleKind } from './samples.ts'
import './lab.css'

const MODES: [Mode, string][] = [['dollhouse', 'Dollhouse'], ['plan', 'Plan'], ['pano', 'Panorama'], ['splat', 'Drone splat']]
const q = new URLSearchParams(location.search)

// ?look=yaw,pitch points the panorama camera (degrees in the scan frame), for repeatable screenshots
const look = (p: ScanPlan) => {
  const pano = p.panos.find((x) => x.label === q.get('pano')), [yaw, pitch] = (q.get('look') ?? '').split(',').map(Number)
  if (pano && q.get('look') === 'door') { // face the nearest doorway that is in view: the check that overlays sit on real doors
    const m = buildModel(p)
    const door = p.openings.filter((o) => o.floor === pano.floor && o.type !== 'window' && !sightBlocked(m, o.floor, pano.position[0], pano.position[1], o.center[0], o.center[1], o.wall))
      .map((o) => ({ o, d: Math.hypot(o.center[0] - pano.position[0], o.center[1] - pano.position[1]) })).filter((x) => x.d > 1.2).sort((a, b) => a.d - b.d)[0]
    if (door) return { pano: pano.id, yaw_deg: (Math.atan2(door.o.center[1] - pano.position[1], door.o.center[0] - pano.position[0]) * 180) / Math.PI, pitch_deg: -6 }
  }
  return pano && Number.isFinite(yaw) ? { pano: pano.id, yaw_deg: yaw, pitch_deg: pitch || 0 } : null
}

function Lab() {
  const [sid, setSid] = useState(q.get('sid') ?? '')
  const [draft, setDraft] = useState(sid)
  const [plan, setPlan] = useState<ScanPlan | null>(null)
  const [error, setError] = useState('')
  const [on, setOn] = useState(() => new Set((q.get('ov') ?? '').split(',').filter((k): k is SampleKind => (SAMPLE_KINDS as readonly string[]).includes(k))))
  const [water, setWater] = useState(Number(q.get('water') ?? 0.45))
  const [view, setView] = useState<View>({
    mode: (q.get('mode') as Mode) ?? 'dollhouse', cut: q.get('cut') ? Number(q.get('cut')) : null, explode: Number(q.get('explode') ?? 0),
    wipe: q.get('wipe') ? Number(q.get('wipe')) : null, measures: q.get('measures') === '1',
    surface: (['scan', 'splat'] as const).find((x) => x === q.get('surface')) ?? 'model', env: q.get('env') === 'aerial' ? 'aerial' : 'studio', style: q.get('style') === 'xray' ? 'xray' : 'solid',
    pose: q.get('pose') ? { bearing: Number(q.get('pose')!.split(',')[0]), pitch: Number(q.get('pose')!.split(',')[1]), range: Number(q.get('pose')!.split(',')[2]) || 'fit' } : undefined, // ?pose=bearing,pitch,range for repeatable screenshots
  })
  const [pick, setPick] = useState<Pick | null>(null)
  const [bench, setBench] = useState('')
  const hover = useSceneLink((s) => s.hover)

  useEffect(() => {
    setPlan(null); setError('')
    if (!sid) return
    fetch(`/api/scan/${sid}/plan`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`No scan ${sid} (${r.status})`)))).then((p: ScanPlan) => {
      setPlan(p)
      setView((v) => ({ ...v, floor: q.get('floor') ? p.floors[Number(q.get('floor'))]?.id : null, pano: p.panos.find((x) => x.label === q.get('pano'))?.id ?? null, focus: look(p) }))
    }).catch((e: Error) => setError(e.message))
  }, [sid])
  useEffect(() => { // every lab state is a link
    const p = new URLSearchParams({ sid, mode: view.mode })
    if (on.size) p.set('ov', [...on].join(','))
    if (view.cut != null) p.set('cut', String(view.cut)); if (view.explode) p.set('explode', String(view.explode))
    if (view.wipe != null) p.set('wipe', view.wipe.toFixed(2)); if (view.measures) p.set('measures', '1')
    if (on.has('water')) p.set('water', String(water))
    if (view.surface && view.surface !== 'model') p.set('surface', view.surface); if (view.env === 'aerial') p.set('env', 'aerial'); if (view.style === 'xray') p.set('style', 'xray')
    if (q.get('pose')) p.set('pose', q.get('pose')!)
    const pano = plan?.panos.find((x) => x.id === view.pano)?.label; if (pano && view.mode === 'pano') p.set('pano', pano)
    const fi = plan?.floors.findIndex((f) => f.id === view.floor) ?? -1; if (fi >= 0) p.set('floor', String(fi))
    history.replaceState(null, '', `?${p}`)
  }, [sid, view, on, water, plan])

  const overlays = useMemo(() => (plan ? sampleOverlays(plan, on, water) : []), [plan, on, water])
  const toggle = (k: SampleKind) => setOn((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n })
  const describe = (p: Pick | null) => {
    if (!p || !plan) return ''
    if (p.kind === 'room') { const r = plan.rooms.find((x) => x.id === p.id); return `room ${r?.label ?? 'unlabelled'}, ${r?.area?.toFixed(1) ?? '?'} m²` }
    if (p.kind === 'opening') { const o = plan.openings.find((x) => x.id === p.id); return `${o?.type}, ${o?.width?.toFixed(2)} m wide, ${o?.height?.toFixed(2)} m high` }
    if (p.kind === 'wall') { const w = plan.walls.find((x) => x.id === p.id); return `wall, ${w?.length.toFixed(2)} m long, ${w?.thickness} m thick` }
    if (p.kind === 'pano') return `scan position ${plan.panos.find((x) => x.id === p.id)?.label}`
    return `pin ${p.id}`
  }
  const runBench = async () => {
    setBench('measuring')
    const engine = (document.querySelector('.th-scene') as unknown as { __engine?: { benchmark(): Promise<string> } })?.__engine
    setBench(engine ? await engine.benchmark() : 'no scene')
  }

  return (
    <div className="lab th-scene-tokens">
      <header className="lab-strip">
        <form onSubmit={(e) => { e.preventDefault(); setSid(draft.trim()) }}>
          <label>Scan<input value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} size={12} /></label>
        </form>
        <div className="lab-seg" role="group" aria-label="View">
          {MODES.map(([m, name]) => <button key={m} aria-pressed={view.mode === m} disabled={m === 'splat' && !plan?.has.splat} onClick={() => setView((v) => ({ ...v, mode: m }))}>{name}</button>)}
        </div>
        <div className="lab-checks">
          {SAMPLE_KINDS.map((k) => <label key={k}><input type="checkbox" checked={on.has(k)} onChange={() => toggle(k)} />{SAMPLE_LABEL[k]}</label>)}
          {on.has('water') && <label className="lab-range">depth<input type="range" min={0} max={1.6} step={0.05} value={water} onChange={(e) => setWater(Number(e.target.value))} /><span className="th-num">{water.toFixed(2)} m</span></label>}
          <label><input type="checkbox" checked={!!view.measures} onChange={() => setView((v) => ({ ...v, measures: !v.measures }))} />Door widths</label>
          <label><input type="checkbox" checked={view.wipe != null} disabled={!plan?.has.defurnished} onChange={() => setView((v) => ({ ...v, wipe: v.wipe == null ? 0.5 : null }))} />Furnished | empty</label>
        </div>
      </header>
      <main className="lab-stage">
        {error ? <p className="lab-msg">{error}</p> : !plan ? <div className="lab-skeleton" aria-label="Loading scan" /> : (
          <BuildingScene plan={plan} overlays={overlays} view={view} onPick={setPick} onViewChange={setView} />
        )}
      </main>
      <footer className="lab-foot">
        <span>{plan ? `${plan.name ?? sid} · ${plan.walls.length} walls · ${plan.openings.length} openings · ${plan.rooms.length} rooms · ${plan.panos.length} positions · ${plan.floors.length} floor${plan.floors.length > 1 ? 's' : ''}` : ''}</span>
        <span className="lab-pick">{pick ? `picked ${describe(pick)}` : hover ? `over ${describe(hover)}` : 'click anything'}</span>
        <button onClick={runBench}>Measure frame rate</button><span className="th-num">{bench}</span>
      </footer>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<StrictMode><Lab /></StrictMode>)
