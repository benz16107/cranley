import { Component, lazy, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { CameraInfo, Mode, Overlay as SceneOverlay, Pick, ScanPlan as ScenePlan, View } from '../scene/types.ts'
import type { SceneState as EngineState } from '../scene/engine/Engine.ts'
import type { BuildingSceneProps } from '../scene/BuildingScene.tsx'
import { fetchPlan } from './api.ts'
import { replayDemo } from './agent.ts'
import { setQuery, useRoute } from './router.ts'
import { useWorkspace, userOp } from './store.ts'
import type { Anchor, Finding, ScanPlan } from './types.ts'

/* The bridge between the workspace and <BuildingScene> (web/src/scene, shared by every look). A skin never reaches
   into three.js and never builds scene props by hand: useBuildingView(sid) gives it the plan, the props to spread on
   <Scene>, the modes this scan has and the setters. What the scene looks like is the skin's, through --scene-* CSS
   variables (scene/tokens.css) and a className. */

/** The scene component, loaded on demand (three.js is large). Render it inside <Suspense>. */
export const Scene = lazy(() => import('../scene/BuildingScene.tsx').then((m) => ({ default: m.BuildingScene })))
export type SceneMode = Mode
export type SceneView = View
export type SceneProps = BuildingSceneProps
/** What `onCamera` reports: bearing, pitch, range and fov, and where the focused thing is on screen. */
export type SceneCamera = CameraInfo
/** What `onState` reports: the mode, whether it is loading, the drone capture's progress. */
export type SceneState = EngineState

/** Looking at a finding: the building view frames its anchor and whatever lists it can mark it as current. */
export function focusFinding(f: Finding | undefined) {
  if (!f?.anchor) return
  userOp({ op: 'camera.focus', anchor: f.anchor, finding: f.id })
}
export function focusAnchor(anchor: Anchor) { userOp({ op: 'camera.focus', anchor }) }

/** The floor an anchor is on, or null (a point, a map anchor, an id the plan does not have). */
export function anchorFloor(plan: ScanPlan, a: Anchor | null | undefined): string | null {
  if (!a || !('sid' in a)) return null
  if ('opening' in a) return plan.openings.find((o) => o.id === a.opening)?.floor ?? null
  if ('room' in a) return plan.rooms.find((r) => r.id === a.room)?.floor ?? null
  if ('wall' in a) return plan.walls.find((w) => w.id === a.wall)?.floor ?? null
  if ('pano' in a) return plan.panos.find((p) => p.id === a.pano)?.floor ?? null
  return null
}

/** A fault inside the 3D view stays inside it: the rest of the look keeps working. `fallback` is the skin's to draw.
    Give it `key={view.sceneKey}` so a new scan or a retry starts clean. */
export class SceneBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(e: unknown) { console.error('[scene]', e) }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

const MODES: Mode[] = ['dollhouse', 'plan', 'pano', 'splat']
const isMode = (v: string | null): v is Mode => MODES.includes(v as Mode)

/** One scan in the building view: its plan, and everything <Scene> needs, kept in step with the workspace. */
export function useBuildingView(sid: string) {
  const [plan, setPlan] = useState<ScanPlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tries, setTries] = useState(0)
  const { q } = useRoute()
  // what the person chose: mode, floor, cut, position. The mode and position are in the URL (?v, ?p), so a link or
  // a change of look opens the same view.
  const [look, setLook] = useState<View>(() => { const v = q.get('v'); return isMode(v) ? { mode: v, pano: q.get('p') ?? undefined } : { mode: 'dollhouse' } })
  const doc = useWorkspace((s) => s.doc)
  const shown = useRef(sid)
  useEffect(() => {
    let on = true
    setPlan(null); setError(null)
    if (shown.current !== sid) { shown.current = sid; setLook({ mode: 'dollhouse' }) } // another scan starts from the outside
    fetchPlan(sid).then((p) => on && setPlan(p), (e: Error) => on && setError(e.message))
    return () => { on = false }
  }, [sid, tries])
  useEffect(() => { setQuery({ v: look.mode === 'dollhouse' ? null : look.mode, p: look.mode === 'pano' ? look.pano : null }) }, [look.mode, look.pano])
  useEffect(() => { if (q.get('demo') === 'access') replayDemo(sid) }, [sid, q])

  // what is given in map coordinates (an outdoor path, a pin on the roof) is the map's to draw, not the building's
  const overlays = useMemo(() => doc.overlays.filter((o) => !o.sid || o.sid === sid).map((o) => o.overlay)
    .map((o) => (o.kind === 'pins' ? { ...o, pins: o.pins.filter((p) => !('geo' in p.anchor)) } : o))
    .filter((o) => !(o.kind === 'route' && o.floor === 'geo') && !(o.kind === 'pins' && !o.pins.length)), [doc.overlays, sid])
  const cam = doc.camera && 'sid' in doc.camera.anchor && doc.camera.anchor.sid === sid ? doc.camera.anchor : null
  const kept = doc.shortlist.some((s) => s.sid === sid)
  // Where the camera is told to look: its floor comes up, and a panorama anchor means "stand there and look that way".
  const camKey = cam ? JSON.stringify(cam) : ''
  useEffect(() => {
    if (!plan || !cam) return
    const floor = anchorFloor(plan, cam)
    setLook((v) => ('pano' in cam ? { ...v, mode: 'pano', pano: cam.pano } : { ...v, mode: v.mode === 'pano' || v.mode === 'splat' ? 'dollhouse' : v.mode, floor: floor && plan.floors.length > 1 ? floor : v.floor }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camKey, plan])
  const view = useMemo<View>(() => ({ ...look, focus: cam && !('point' in cam && cam.point.every((n) => n === 0)) ? cam : null }), [look, camKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const onPick = (p: Pick) => {
    if (p.kind === 'pano') return // the scene walks there itself
    const anchor: Anchor | undefined = p.kind === 'pin'
      ? overlays.flatMap((o) => (o.kind === 'pins' ? o.pins : [])).find((x) => x.id === p.id)?.anchor
      : p.kind === 'room' ? { sid, room: p.id } : p.kind === 'opening' ? { sid, opening: p.id } : { sid, wall: p.id }
    if (!anchor) return
    const same = (a: Anchor | null) => !!a && JSON.stringify({ ...a, sid }) === JSON.stringify({ ...anchor, sid })
    const f = doc.findings.find((x) => same(x.anchor))
    if (f) focusFinding(f); else focusAnchor({ ...anchor, sid } as Anchor)
  }
  const sceneProps: SceneProps | null = plan && {
    plan: plan as unknown as ScenePlan, // one ScanPlan, read through the scene's own (wider) type
    overlays: overlays as SceneOverlay[], view, onPick, onViewChange: ({ focus: _f, ...v }) => setLook(v),
  }
  return {
    plan, error, retry: () => setTries((t) => t + 1),
    /** The modes this scan can show: no drone capture means no 'splat', no positions means no 'pano'. */
    modes: plan ? MODES.filter((m) => (m !== 'splat' || plan.has.splat) && (m !== 'pano' || plan.panos.length > 0)) : [],
    mode: look.mode,
    setMode: (m: Mode) => setLook((v) => ({ ...v, mode: m, pano: m === 'pano' ? v.pano ?? plan?.panos[0]?.id : v.pano })),
    /** The whole view (floor, cut, pull-apart, wipe, measures) for a skin that draws its own scene controls. */
    view: look, setView: setLook,
    /** Spread on <Scene>, inside <SceneBoundary key={sceneKey}>. Null until the plan has loaded. */
    sceneProps, sceneKey: `${sid}:${tries}`,
    /** The overlays for this scan in the scan's frame: the same list the scene gets, for a skin's own plan drawing. */
    overlays,
    kept, toggleKeep: () => plan && userOp(kept ? { op: 'shortlist.remove', sid } : { op: 'shortlist.add', item: { sid, name: plan.name, address: plan.address ?? '' } }),
  }
}
