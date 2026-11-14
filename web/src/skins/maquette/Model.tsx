import { Suspense, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { Slider } from '@base-ui/react/slider'
import { Switch } from '@base-ui/react/switch'
import { Scene, SceneBoundary, droneImage, fetchDrone, navigate, panoFace, useBuildingView, useRoute, useWorkspace, userOp, type Doc, type ScanPlan, type SceneMode, type SceneProps } from '../../core/index.ts'
import { Photo } from './blocks.tsx'
import { anchorPoint, findingPhoto, street } from './lib.ts'
import { headline, lensOverlays, type useSheet } from './state.ts'
import { Big, Glyph, Icon, Print, Src } from './ui.tsx'
import './scene.css'

/* One building: a white card model cut open on the table. The sheet on top of the stack is a lens (only its tool's
   marks are on the model), every finding is a tag on a string at its own doorway, the route is tape, water is
   poured in. Two photo prints lie beside the model: one is the door into the 360° interior, the other into the
   drone capture. Inside either, the table is put away and one strip of tape leads back. */

const WHOLE = 3.2 // the cut slider's top: walls left whole
type Found = Doc['findings'][number]

/** Ties the print on the table to its place in the model: a thread from the print to the scene's own tag for the
    same finding, which is also marked as the current one. The scene does not say where an anchor is on screen yet
    (core-requests.md, Maquette 2), so the tag is found by its label; with no tag in view there is no thread. */
function useThread(host: RefObject<HTMLElement | null>, from: RefObject<HTMLElement | null>, label: string | null) {
  const line = useRef<SVGLineElement>(null)
  useEffect(() => {
    if (!label) return
    const l = line.current
    let raf = 0, pin: HTMLElement | null = null
    const tick = () => {
      raf = requestAnimationFrame(tick)
      const root = host.current, a = from.current
      if (!root || !l) return
      if (!pin?.isConnected) {
        pin = [...root.querySelectorAll<HTMLElement>('.th-pin')].find((p) => p.getAttribute('aria-label')?.includes(`. ${label} (`)) ?? null
        pin?.setAttribute('data-mq-current', '')
      }
      const on = !!pin && !pin.hidden && !!a
      l.style.opacity = on ? '1' : '0'
      if (!on) return
      const p = pin!.getBoundingClientRect(), r = a!.getBoundingClientRect(), o = root.getBoundingClientRect()
      l.setAttribute('x1', String(r.left + r.width / 2 - o.left)); l.setAttribute('y1', String(r.top + 6 - o.top))
      l.setAttribute('x2', String(p.left + 9 - o.left)); l.setAttribute('y2', String(p.bottom - o.top)) // the tag's foot (scene.css)
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); pin?.removeAttribute('data-mq-current'); if (l) l.style.opacity = '0' }
  }, [label]) // eslint-disable-line react-hooks/exhaustive-deps
  return line
}

/** Where to stand to see a finding: the position its photograph was taken from, else the nearest one on its floor. */
function standpoint(plan: ScanPlan, f: Found): { pano: string; yaw_deg: number; pitch_deg: number } | null {
  const at = anchorPoint(plan, f.anchor), ref = f.media?.find((m) => m.kind === 'pano')?.ref.split('/')
  const named = plan.panos.find((p) => p.id === (ref && ref.length > 1 ? ref[1] : ref?.[0]))
  const near = at ? [...plan.panos].map((p) => ({ p, d: Math.hypot(p.position[0] - at[0], p.position[1] - at[1]) })).filter((x) => x.d > 0.8).sort((a, b) => a.d - b.d)[0]?.p : undefined
  const p = named ?? near
  if (!p) return null
  return { pano: p.id, yaw_deg: at ? (Math.atan2(at[1] - p.position[1], at[0] - p.position[0]) * 180) / Math.PI : 0, pitch_deg: -4 }
}

const ModelMark = () => <svg width="34" height="26" viewBox="0 0 34 26" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true"><path d="M3 9 17 3l14 6v10l-14 6L3 19Z" /><path d="M3 9l14 6 14-6M17 15v10" /></svg>
const PlanMark = () => <svg width="34" height="26" viewBox="0 0 34 26" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M4 3h26v20H4ZM4 13h9M19 13h11M17 3v6M17 17v6" /></svg>

export function Model({ sid, sheet }: { sid: string; sheet: ReturnType<typeof useSheet> }) {
  const v = useBuildingView(sid), panel = sheet.active
  const doc = useWorkspace((s) => s.doc)
  const { q } = useRoute()
  const { plan, mode } = v
  const inside = mode === 'pano' || mode === 'splat'
  const root = useRef<HTMLDivElement>(null), print = useRef<HTMLElement>(null)

  // the lens: the sheet on top decides what is laid on the model
  const all = v.sceneProps?.overlays
  const lens = useMemo(() => (all ? lensOverlays(doc, sid, panel?.tool, all) : undefined), [doc, sid, panel?.tool, all])
  const sceneProps: SceneProps | null = v.sceneProps && { ...v.sceneProps, overlays: lens }

  // the finding being looked at, its print, and the thread to its tag
  const found = doc.findings.find((f) => f.id === doc.camera?.finding && f.anchor && 'sid' in f.anchor && f.anchor.sid === sid)
  const tagLabel = useMemo(() => {
    if (!found) return null
    const same = (a: unknown) => JSON.stringify({ ...(a as object), sid }) === JSON.stringify({ ...found.anchor, sid })
    return v.overlays.flatMap((o) => (o.kind === 'pins' ? o.pins : [])).find((p) => same(p.anchor))?.label ?? null
  }, [found, v.overlays, sid])
  const thread = useThread(root, print, mode === 'plan' || mode === 'splat' ? null : tagLabel) // the plan and the drone capture draw no tags
  const stand = plan && found ? standpoint(plan, found) : null
  const h = headline(doc, panel)

  // the two prints that are doors
  const insideSrc = plan?.panos.length ? panoFace(sid, v.view.pano ?? plan.panos[Math.floor(plan.panos.length / 2)].id, 1) : null
  const [airSrc, setAir] = useState<string | null>(null)
  useEffect(() => {
    let on = true
    setAir(null)
    if (plan?.has.splat) fetchDrone(sid, 12).then((d) => {
      const best = ((d.photos ?? []) as { name: string; gimbal_pitch_deg?: number }[]).sort((a, b) => Math.abs((a.gimbal_pitch_deg ?? -90) + 40) - Math.abs((b.gimbal_pitch_deg ?? -90) + 40))[0]
      if (on && best) setAir(`${droneImage(sid, best.name)}?w=360`) // a thumbnail: the server sizes it (core-requests.md, Maquette 4)
    }, () => {})
    return () => { on = false }
  }, [sid, plan?.has.splat])

  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape' && inside && !e.defaultPrevented && !document.querySelector('[data-open], [cmdk-root]')) v.setMode('dollhouse') }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [inside]) // eslint-disable-line react-hooks/exhaustive-deps

  // inside a photograph the stack is folded away, so the photograph has the whole table; it comes back with the model
  const put = useRef(false)
  useEffect(() => {
    if (inside && !sheet.folded) { put.current = true; sheet.fold(true) } else if (!inside && put.current) { put.current = false; sheet.fold(false) }
  }, [inside]) // eslint-disable-line react-hooks/exhaustive-deps

  const go = (m: SceneMode) => v.setMode(m)
  const multi = (plan?.floors.length ?? 0) > 1
  const floors = useMemo(() => [...(plan?.floors ?? [])].sort((a, b) => b.sequence - a.sequence), [plan])
  const toMap = () => navigate('/map', { b: q.get('b'), city: q.get('city') })
  const fault = <div className="mq-fault mq-paper"><p>The building view stopped on this scan.</p><button className="mq-btn is-ink is-sm" onClick={v.retry}>Try again</button></div>

  return (
    <main className="mq-model" ref={root} data-mode={mode} data-inside={inside || undefined} data-lens={(!!panel && !inside) || undefined}>
      <div className="mq-stage">
        {v.error && <div className="mq-fault mq-paper" role="alert"><p>{v.error}</p><button className="mq-btn is-ink is-sm" onClick={v.retry}>Try again</button></div>}
        {!plan && !v.error && <div className="mq-unroll" role="status" aria-label="Loading the plan"><i /><span className="mq-caps">Unrolling the plan</span></div>}
        {sceneProps && (
          <Suspense fallback={<div className="mq-unroll" role="status" aria-label="Loading the model"><i /><span className="mq-caps">Raising the model</span></div>}>
            <SceneBoundary key={v.sceneKey} fallback={fault}><Scene {...sceneProps} className="mq-scene" /></SceneBoundary>
          </Suspense>
        )}
      </div>

      {/* the tracing sheet: its tab names the lens, so what is on the model is never a guess */}
      {panel && !inside && <div className="mq-trace" key={panel.id}><span className="mq-caps">Laid on the model <b>{panel.title}</b></span></div>}
      <svg className="mq-thread" aria-hidden="true"><line ref={thread} /></svg>

      <Print onHome={() => navigate('/')}>
        <button className="mq-back" onClick={toMap}><Icon name="back" size={13} /> The table</button>
        {plan && <span className="where">{[street(plan.address), plan.city].filter(Boolean).join(', ')}{plan.name !== street(plan.address) && <small>{plan.name}</small>}</span>}
        {plan && <button className="mq-keep" aria-pressed={v.kept} onClick={v.toggleKeep}><Icon name={v.kept ? 'kept' : 'keep'} size={14} /> {v.kept ? 'Kept' : 'Keep'}</button>}
      </Print>

      {inside ? <button className="mq-return mq-tag mq-tape" onClick={() => go('dollhouse')}><Icon name="back" size={13} /> Back to the model on the table</button>
        : h ? <Big value={h.value} unit={h.unit} status={h.status}>{h.title}<br /><span className="mq-dim">{h.note}</span></Big>
        : plan && <Big value={plan.rooms.filter((r) => r.label !== 'Void').length} unit="rooms" digits={0}>{plan.name}<br /><span className="mq-dim">{doc.tools.length ? 'No tool has run here yet. Run one from the stack.' : 'Lay a tool on the model to measure it.'}</span></Big>}

      {plan && (
        <div className="mq-look">
          <nav className="mq-views" aria-label="Ways to look at this building">
            <button aria-pressed={mode === 'dollhouse'} onClick={() => go('dollhouse')}><ModelMark /><span>Model</span></button>
            <button aria-pressed={mode === 'plan'} onClick={() => go('plan')}><PlanMark /><span>Plan</span></button>
            {v.modes.includes('pano') && <button className="is-print" aria-pressed={mode === 'pano'} onClick={() => go('pano')}><Photo src={insideSrc} /><span>Step inside</span></button>}
            {v.modes.includes('splat') && <button className="is-print" aria-pressed={mode === 'splat'} onClick={() => go('splat')}><Photo src={airSrc} /><span>From the air</span></button>}
          </nav>
          <div className="mq-viewtools is-print">
            {mode === 'dollhouse' && (
              <label>Cut
                <Slider.Root value={v.view.cut ?? WHOLE} min={0.3} max={WHOLE} step={0.05} onValueChange={(x) => v.setView((s) => ({ ...s, cut: (x as number) >= WHOLE - 0.02 ? null : (x as number) }))} aria-label="Cut-away height in metres">
                  <Slider.Control className="mq-slider"><Slider.Track className="mq-track"><Slider.Indicator className="mq-range" /><Slider.Thumb className="mq-thumb" /></Slider.Track></Slider.Control>
                </Slider.Root>
                <span className="mq-num">{v.view.cut == null ? 'whole' : `${v.view.cut.toFixed(2)} m`}</span>
              </label>
            )}
            {multi && (mode === 'dollhouse' || mode === 'plan') && (
              <div className="floors" role="group" aria-label="Floors">
                {mode === 'dollhouse' && <button aria-pressed={!v.view.floor} onClick={() => v.setView((s) => ({ ...s, floor: null }))}>All</button>}
                {floors.map((f) => <button key={f.id} aria-pressed={v.view.floor === f.id || (mode === 'plan' && !v.view.floor && f.id === plan.floors[0].id)} onClick={() => v.setView((s) => ({ ...s, floor: f.id }))}>{f.label || `Floor ${f.sequence + 1}`}</button>)}
              </div>
            )}
            {multi && mode === 'dollhouse' && (
              <label>Pull apart
                <Slider.Root value={v.view.explode ?? 0} min={0} max={1} step={0.01} onValueChange={(x) => v.setView((s) => ({ ...s, explode: x as number }))} aria-label="Pull the floors apart">
                  <Slider.Control className="mq-slider"><Slider.Track className="mq-track"><Slider.Indicator className="mq-range" /><Slider.Thumb className="mq-thumb" /></Slider.Track></Slider.Control>
                </Slider.Root>
              </label>
            )}
            {mode !== 'splat' && <label className="sw"><Switch.Root className="mq-switch" checked={!!v.view.measures} onCheckedChange={(on) => v.setView((s) => ({ ...s, measures: on }))}><Switch.Thumb className="mq-knob" /></Switch.Root>Door widths</label>}
            {mode === 'pano' && plan.has.defurnished && <label className="sw"><Switch.Root className="mq-switch" checked={v.view.wipe != null} onCheckedChange={(on) => v.setView((s) => ({ ...s, wipe: on ? 0.5 : null }))}><Switch.Thumb className="mq-knob" /></Switch.Root>Empty the room</label>}
          </div>
        </div>
      )}

      {found && (
        <figure className="mq-found mq-paper" ref={print} key={found.id} data-s={found.status}>
          <Photo src={findingPhoto(found)} alt="" />
          <figcaption>
            <span className="mq-caps"><Glyph status={found.status} size={10} /> Looking at</span>
            <b>{found.title}</b>
            {found.detail && <p>{found.detail}</p>}
            <div className="mq-row">
              <Src source={found.source} />
              {stand && mode !== 'pano' && <button className="mq-btn is-tape is-sm" onClick={() => { v.setView((s) => ({ ...s, measures: true })); userOp({ op: 'camera.focus', anchor: { sid, ...stand }, finding: found.id }) }}>Stand here</button>}
            </div>
          </figcaption>
        </figure>
      )}
    </main>
  )
}
