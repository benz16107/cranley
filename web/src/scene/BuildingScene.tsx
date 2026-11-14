// <BuildingScene plan overlays view onPick />: everything that shows a building. The shell never reaches into three.js.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Engine, type FrameInfo, type SceneState } from './engine/Engine.ts'
import { FloorPlan, type FloorPlanHandle } from './FloorPlan.tsx'
import { isKnownOverlay, type Model } from './model.ts'
import { useSceneLink } from './store.ts'
import type { Overlay, Pick, ScanPlan, View } from './types.ts'
import './scene.css'

export interface BuildingSceneProps {
  plan: ScanPlan
  overlays?: Overlay[]
  view?: View
  onPick?: (p: Pick) => void
  /** Called when the person changes the view from inside the scene: walking to a scan position, dragging the cut. */
  onViewChange?: (v: View) => void
  /** Where /api lives. Empty means same origin. */
  api?: string
  className?: string
}
type Of<K extends string> = Extract<Overlay, { kind: K }>
const NO_OVERLAYS: Overlay[] = []
const DEFAULT_VIEW: View = { mode: 'dollhouse' }
const niceLength = (m: number) => [0.5, 1, 2, 5, 10, 20, 50].find((v) => v >= m) ?? 100

export function BuildingScene({ plan, overlays = NO_OVERLAYS, view: viewProp = DEFAULT_VIEW, onPick, onViewChange, api = '', className }: BuildingSceneProps) {
  const host = useRef<HTMLDivElement>(null), engine = useRef<Engine | null>(null)
  const planLayer = useRef<HTMLDivElement>(null), planHandle = useRef<FloorPlanHandle>(null), insetHandle = useRef<FloorPlanHandle>(null)
  const scaleBar = useRef<HTMLDivElement>(null), scaleText = useRef<HTMLSpanElement>(null)
  const [state, setState] = useState<SceneState | null>(null)
  const [model, setModel] = useState<Model | null>(null)
  const [view, setView] = useState(viewProp)
  const [seen, setSeen] = useState(viewProp)
  if (seen !== viewProp) { setSeen(viewProp); setView(viewProp) } // the outside can always say "look here"
  const cb = useRef({ onPick, onViewChange })
  useEffect(() => { cb.current = { onPick, onViewChange } })
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
    const e = new Engine(host.current!, plan, { api, onPick: (p) => cb.current.onPick?.(p), onViewChange: change, onState: setState, onFrame })
    engine.current = e; setModel(e.model)
    useSceneLink.setState({ hover: null, selected: null })
    return () => { e.dispose(); engine.current = null }
  }, [plan, api, change])
  useEffect(() => { engine.current?.setOverlays(overlays) }, [overlays, model])
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
        if (e.key === 'Escape' && mode === 'pano') change({ ...view, mode: 'dollhouse' })
        else if (k[e.key]) { engine.current?.step(...k[e.key]); e.preventDefault() }
      }}>
      <div ref={planLayer} className="th-plan">
        {model && <FloorPlan plan={plan} model={model} overlays={overlays} floor={view.floor} measures={view.measures} pano={state?.pano} driven handle={planHandle} onPick={pickFromPlan} />}
        <div className="th-scalebar"><div ref={scaleBar} /><span ref={scaleText} className="th-num" /></div>
      </div>

      {state?.loading && <div className="th-loading" role="status" aria-label="Loading" style={mode === 'splat' ? { ['--p' as string]: state.splat.progress } : undefined} data-known={mode === 'splat'} />}

      {model && model.hasWalls && mode !== 'plan' && mode !== 'splat' && (
        <div className="th-inset" data-scene-ui>
          <FloorPlan plan={plan} model={model} overlays={overlays} floor={view.floor} compact pano={mode === 'pano' ? state?.pano : null} handle={insetHandle} onPick={pickFromPlan} />
        </div>
      )}

      {mode === 'dollhouse' && model?.hasWalls && (
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

      {mode === 'splat' && state && (
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
