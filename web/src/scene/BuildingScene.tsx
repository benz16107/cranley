// <BuildingScene plan overlays view onPick />: everything that shows a building. The shell never reaches into three.js.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Engine, type FrameInfo, type SceneState } from './engine/Engine.ts'
import { furnish as checkFurniture, standAt } from './furnish.ts'
import { FloorPlan, type FloorPlanHandle } from './FloorPlan.tsx'
import { isKnownOverlay, type Model } from './model.ts'
import { ShowLayer } from './show/ShowPanel.tsx'
import type { ShowState } from './show/types.ts'
import { useSceneLink } from './store.ts'
import type { CameraInfo, Furnish, Overlay, Pick, Placed, ScanPlan, Vec3, View } from './types.ts'
import { ViewSwitcher } from './ViewSwitcher.tsx'
import './scene.css'

export interface BuildingSceneProps {
  plan: ScanPlan
  overlays?: Overlay[]
  view?: View
  onPick?: (p: Pick) => void
  /** Called when the person changes the view from inside the scene: walking to a scan position, dragging the cut. */
  onViewChange?: (v: View) => void
  /** The camera whenever it changes, and once when a designed flight ends: bearing, pitch, range and fov in the
      units of `view.pose` and `view.fov`, and where `view.focus` is on screen. For a leader line or a timed arrival. */
  onCamera?: (c: CameraInfo) => void
  /** What the scene is doing: its mode, whether it is loading, and the drone capture's progress. */
  onState?: (s: SceneState) => void
  /** What `view.show` is doing: its playhead, clock and the numbers on screen, whenever a step passes. For a look's
      own transport (play, a time slider) in its toolbar. */
  onShow?: (s: ShowState | null) => void
  /** Where /api lives. Empty means same origin. */
  api?: string
  className?: string
  /** true asks the server, as soon as the scene mounts, to colour the scanned mesh in the background; `onState`
      then reports `scan.colour` ('unknown', then 'baking' with `scan.progress`, 'ready' or 'none'). Without it the
      question is only asked when the photoreal surface is first shown. */
  prepare?: boolean
  /** false leaves out the scene's own view switcher (surface, surroundings, x-ray, fly in), for a look
      that mounts <ViewSwitcher> in its own toolbar. */
  switcher?: boolean
  /** Furniture a person is trying out, in the 3D view: each piece is drawn as its model at its exact size, can be
      dragged on the floor (the arrow keys move the selected one, R turns it, Delete removes it), and is checked as it moves
      against the walls, the door swings and its room's wheelchair turning circle. All of it is worked out in the
      browser from the plan. Leave it out and the scene has no furniture. */
  furnish?: Furnish | null
}
type Of<K extends string> = Extract<Overlay, { kind: K }>
const NO_OVERLAYS: Overlay[] = []
const NO_PIECES: Placed[] = []
type Stood = Placed & { center: Vec3 }
const DEFAULT_VIEW: View = { mode: 'dollhouse' }
const niceLength = (m: number) => [0.5, 1, 2, 5, 10, 20, 50].find((v) => v >= m) ?? 100

export function BuildingScene({ plan, overlays = NO_OVERLAYS, view: viewProp = DEFAULT_VIEW, onPick, onViewChange, onCamera, onState, onShow, api = '', className, switcher = true, prepare = false, furnish = null }: BuildingSceneProps) {
  const host = useRef<HTMLDivElement>(null), engine = useRef<Engine | null>(null)
  const planLayer = useRef<HTMLDivElement>(null), planHandle = useRef<FloorPlanHandle>(null), insetHandle = useRef<FloorPlanHandle>(null)
  const scaleBar = useRef<HTMLDivElement>(null), scaleText = useRef<HTMLSpanElement>(null)
  const [state, setState] = useState<SceneState | null>(null)
  const showSink = useRef<((s: ShowState | null) => void) | null>(null)
  const [model, setModel] = useState<Model | null>(null)
  const [view, setView] = useState(viewProp)
  const [seen, setSeen] = useState(viewProp)
  if (seen !== viewProp) { setSeen(viewProp); setView(viewProp) } // the outside can always say "look here"
  const cb = useRef({ onPick, onViewChange, onCamera, onState, onShow, furnish })
  useEffect(() => { cb.current = { onPick, onViewChange, onCamera, onState, onShow, furnish } })
  const playing = view.show?.kind ?? null, shown = !!playing
  useEffect(() => { if (!playing) cb.current.onShow?.(null) }, [playing])
  const change = useCallback((v: View) => { setView(v); cb.current.onViewChange?.(v) }, [])

  useEffect(() => {
    const onFrame = (f: FrameInfo) => {
      const layer = planLayer.current
      if (layer) { layer.style.opacity = String(f.plan.presence); layer.style.visibility = f.plan.presence > 0.01 ? 'visible' : 'hidden'; layer.style.pointerEvents = f.plan.presence > 0.5 ? 'auto' : 'none' }
      if (f.plan.presence > 0.01) {
        planHandle.current?.set(f.plan.scale, f.plan.tx, f.plan.ty)
        const len = niceLength(90 / f.plan.scale)
        if (scaleBar.current) scaleBar.current.style.width = `${(len * f.plan.scale).toFixed(1)}px`
        if (scaleText.current) scaleText.current.textContent = `${len} m`
      }
      insetHandle.current?.cone(f.look)
    }
    const e = new Engine(host.current!, plan, { api, onPick: (p) => cb.current.onPick?.(p), onViewChange: change, onState: (st) => { setState(st); cb.current.onState?.(st) }, onFrame, onCamera: (c) => cb.current.onCamera?.(c), prepare, onShow: (sh) => { showSink.current?.(sh); cb.current.onShow?.(sh) } })
    engine.current = e; setModel(e.model)
    useSceneLink.setState({ hover: null, selected: null })
    return () => { e.dispose(); engine.current = null }
  }, [plan, api, change, prepare])
  useEffect(() => { engine.current?.setOverlays(overlays) }, [overlays, model])

  // ---- furniture: the pieces as given, or as they are mid-drag; checked here so only the scene redraws while one moves ----
  const [carried, setCarried] = useState<Placed[] | null>(null), held = useRef<Placed[] | null>(null)
  const given = furnish?.items ?? NO_PIECES, pieces = carried ?? given, picked = furnish?.selected ?? null
  useEffect(() => { // a new piece arrives without a place: it stands where the camera is looking, clear of the last one put there
    const e = engine.current
    if (!e || !given.some((p) => !p.center)) return
    const at = e.standPoint(), stood = given.filter((p) => p.center)
    cb.current.furnish?.onChange(given.map((p) => {
      if (p.center) return p
      const c = standAt(e.model, at.floor, at.x, at.y, p.size)
      while (stood.some((q) => Math.hypot(q.center![0] - c[0], q.center![1] - c[1]) < 0.3)) c[0] += 0.4
      const placed = { ...p, center: c }
      stood.push(placed)
      return placed
    }))
  }, [given, model])
  const furnishing = !!furnish
  const furnished = useMemo(() => {
    const stood = pieces.filter((p): p is Stood => !!p.center)
    return model && furnishing ? { stood, ...checkFurniture(model, stood, picked) } : null
  }, [model, pieces, picked, furnishing])
  useEffect(() => { if (furnished) cb.current.furnish?.onReport?.(furnished.checks) }, [furnished])
  useEffect(() => {
    engine.current?.setFurnish(furnished && {
      items: furnished.stood, own: furnished.overlays,
      onMove: (id, x, y) => { held.current = (held.current ?? cb.current.furnish?.items ?? []).map((p) => (p.id === id && p.center ? { ...p, center: [x, y, p.center[2]] } : p)); setCarried(held.current) },
      onDrop: () => { if (held.current) cb.current.furnish?.onChange(held.current); held.current = null; setCarried(null) }, // one render: the given pieces take over where the drag left them
      onSelect: (id) => { if (id !== (cb.current.furnish?.selected ?? null)) cb.current.furnish?.onSelect?.(id) },
    })
  }, [furnished, model])
  // An edit from the keyboard: mid-drag it joins what is being carried, otherwise it goes to whoever owns the pieces.
  const editPieces = (next: Placed[]) => { if (held.current) { held.current = next; setCarried(next) } else furnish?.onChange(next) }
  const drawn = useMemo(() => (furnished ? [...overlays, ...furnished.overlays.filter((o) => o.kind === 'box')] : overlays), [overlays, furnished])
  useEffect(() => { engine.current?.setView(view) }, [view, model])

  const lens = useMemo(() => overlays.find((o): o is Of<'lens'> => o.kind === 'lens' && isKnownOverlay(o) && !!(o as Of<'lens'>).legend), [overlays])
  const mode = state?.mode ?? view.mode, maxH = model?.maxH ?? 3
  const multi = plan.floors.length > 1
  const pickFromPlan = (p: Pick) => { cb.current.onPick?.(p); if (p.kind === 'pano') change({ ...view, mode: 'pano', pano: p.id }) }
  const floorOrder = useMemo(() => [...plan.floors].sort((a, b) => (b.sequence ?? 0) - (a.sequence ?? 0)), [plan])

  const dragWipe = (e: React.PointerEvent) => {
    const r = host.current!.getBoundingClientRect()
    const move = (ev: PointerEvent) => change({ ...view, wipe: Math.min(0.98, Math.max(0.02, (ev.clientX - r.left) / r.width)) })
    const up = () => { removeEventListener('pointermove', move); removeEventListener('pointerup', up) }
    addEventListener('pointermove', move); addEventListener('pointerup', up); e.preventDefault()
  }

  return (
    <div ref={host} className={`th-scene ${className ?? ''}`} data-mode={mode} tabIndex={0} aria-label={`Building view: ${plan.name ?? plan.sid}`}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return // sliders and buttons keep their own keys
        const k: Record<string, [number, number, number]> = { ArrowLeft: [-1, 0, 0], ArrowRight: [1, 0, 0], ArrowUp: [0, -1, 0], ArrowDown: [0, 1, 0], '+': [0, 0, -1], '=': [0, 0, -1], '-': [0, 0, 1] }
        const piece = furnish && pieces.find((p) => p.id === picked)
        if (piece?.center && k[e.key] && e.key.startsWith('Arrow')) { // the selected piece moves the way the arrow points on screen: 10 cm, or 50 with Shift
          const s = e.shiftKey ? 0.5 : 0.1, [dx, dy] = engine.current?.floorStep(k[e.key][0] * s, -k[e.key][1] * s) ?? [0, 0]
          editPieces(pieces.map((p) => (p === piece ? { ...p, center: [piece.center![0] + dx, piece.center![1] + dy, piece.center![2]] } : p))); e.preventDefault()
        } else if (piece && (e.key === 'r' || e.key === 'R')) editPieces(pieces.map((p) => (p === piece ? { ...p, yaw_deg: (p.yaw_deg + (e.shiftKey ? -15 : 15) + 360) % 360 } : p)))
        else if (piece && (e.key === 'Delete' || e.key === 'Backspace')) { editPieces(pieces.filter((p) => p !== piece)); furnish.onSelect?.(null) }
        else if (piece && e.key === 'Escape') furnish.onSelect?.(null)
        else if (e.key === 'Escape' && mode === 'pano') change({ ...view, mode: 'dollhouse' })
        else if (k[e.key]) { engine.current?.step(...k[e.key]); e.preventDefault() }
      }}>
      <div ref={planLayer} className="th-plan">
        {model && <FloorPlan plan={plan} model={model} overlays={drawn} floor={view.floor} measures={view.measures} pano={state?.pano} driven handle={planHandle} onPick={pickFromPlan} />}
        <div className="th-scalebar"><div ref={scaleBar} /><span ref={scaleText} className="th-num" /></div>
      </div>

      {state?.loading && <div className="th-loading" role="status" aria-label="Loading" style={mode === 'splat' ? { ['--p' as string]: state.splat.progress } : undefined} data-known={mode === 'splat'} />}

      {switcher && <ViewSwitcher plan={plan} view={view} onChange={change} interior={!!state && state.interior.status !== 'none' && state.interior.status !== 'unknown'} className="th-views-in" />}
      {state && (mode === 'dollhouse' || mode === 'splat') && (() => {
        const w = state.world, s = state.scan, lines: string[] = []
        if (view.env === 'aerial') lines.push(w.status === 'loading' ? 'Loading the surroundings' : w.status === 'missing' ? `No surroundings for this scan. ${w.note}` : w.kind ? `${state.site ? 'Drone capture round the house, ' : ''}Vexcel ${w.kind}${state.site ? ' beyond' : ''}${w.capture ? `, flown ${w.capture.slice(0, 7).replace('/', '-')}` : ''}. ${w.note}` : '')
        if ((view.surface ?? 'model') !== 'model' && mode === 'dollhouse' && state.interior.status !== 'ready' && state.interior.status !== 'loading') lines.push(s.status === 'loading' ? 'Loading the scanned mesh' : s.status === 'missing' ? 'This scan has no scanned mesh; showing the measured model.' : s.colour === 'baking' ? `Colouring the scanned mesh from its panoramas: ${Math.round(s.progress * 100)}%` : s.colour === 'none' && s.status === 'ready' ? 'The scanned mesh could not be coloured; showing its form.' : '')
        if (mode === 'splat' && view.env === 'aerial' && state.splat.splats) lines.unshift(`Drone capture: a sample, ${(state.splat.splats / 1e6).toFixed(2)}M of its ${(state.splat.total / 1e6).toFixed(1)}M Gaussians.`)
        const text = lines.filter(Boolean)
        return <>{text.length > 0 && !shown && <p className="th-note th-note-layers">{text.map((t) => <span key={t}>{t}</span>)}</p>}{w.credit && view.env === 'aerial' && w.status === 'ready' && <span className="th-credit">© Vexcel Imaging, Microsoft</span>}</>
      })()}

      {playing && <ShowLayer kind={playing} sink={showSink} />}

      {model && model.hasWalls && mode !== 'plan' && mode !== 'splat' && !shown && (
        <div className="th-inset" data-scene-ui>
          <FloorPlan plan={plan} model={model} overlays={drawn} floor={view.floor} compact pano={mode === 'pano' ? state?.pano : null} handle={insetHandle} onPick={pickFromPlan} />
        </div>
      )}

      {mode === 'dollhouse' && (model?.hasWalls || (view.surface ?? 'model') !== 'model') && (
        <label className="th-cut" data-scene-ui>
          <span className="th-cut-title">Cut</span>
          <input type="range" min={0.2} max={maxH} step={0.05} value={view.cut ?? maxH} aria-label="Cut-away height in metres"
            onChange={(e) => { const v = Number(e.target.value); change({ ...view, cut: v >= maxH - 0.02 ? null : v }) }} />
          <span className="th-num">{view.cut == null ? 'full' : `${view.cut.toFixed(2)} m`}</span>
        </label>
      )}

      {multi && (mode === 'dollhouse' || mode === 'plan') && (
        <div className="th-floors" data-scene-ui role="group" aria-label="Floors">
          {mode === 'dollhouse' && <button aria-pressed={!view.floor} onClick={() => change({ ...view, floor: null })}>All</button>}
          {floorOrder.map((f) => (
            <button key={f.id} aria-pressed={view.floor === f.id || (mode === 'plan' && !view.floor && f.id === plan.floors[0].id)} onClick={() => change({ ...view, floor: f.id })}>{f.label ?? `Floor ${(f.sequence ?? 0) + 1}`}</button>
          ))}
          {mode === 'dollhouse' && (
            <label className="th-explode"><span>Pull apart</span>
              <input type="range" min={0} max={1} step={0.01} value={view.explode ?? 0} onChange={(e) => change({ ...view, explode: Number(e.target.value) })} />
            </label>
          )}
        </div>
      )}

      {mode === 'pano' && view.wipe != null && state?.hasEmpty && (
        <div className="th-wipe" data-scene-ui style={{ left: `${view.wipe * 100}%` }} onPointerDown={dragWipe} role="slider" tabIndex={0}
          aria-label="Furnished and empty divider" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(view.wipe * 100)}
          onKeyDown={(e) => { const d = e.key === 'ArrowLeft' ? -0.03 : e.key === 'ArrowRight' ? 0.03 : 0; if (d) change({ ...view, wipe: Math.min(0.98, Math.max(0.02, view.wipe! + d)) }) }}>
          <span className="th-wipe-tag th-wipe-l">Furnished</span><span className="th-wipe-tag th-wipe-r">Empty</span><span className="th-wipe-grip" />
        </div>
      )}

      {lens && mode !== 'splat' && (
        <div className="th-legend" data-ramp={lens.ramp}>
          <span className="th-legend-title">{lens.legend.title}</span>
          <span className="th-legend-bar" />
          <span className="th-legend-ends th-num"><span>{lens.legend.min}</span><span>{lens.legend.unit ?? ''}</span><span>{lens.legend.max}</span></span>
        </div>
      )}

      {mode === 'splat' && state && view.env !== 'aerial' && (
        <p className="th-note">
          {state.splat.status === 'missing' ? 'No drone capture for this scan.'
            : state.splat.splats ? <>Drone capture: <span className="th-num">{(state.splat.splats / 1e6).toFixed(2)}M</span> of <span className="th-num">{(state.splat.total / 1e6).toFixed(1)}M</span> Gaussians loaded, a sample</>
            : 'Loading the drone capture'}
        </p>
      )}
      {state?.noWalls && mode === 'dollhouse' && <p className="th-note">This scan has no wall measurements. Showing its photo plan and scan positions; click a position to look around.</p>}
    </div>
  )
}
