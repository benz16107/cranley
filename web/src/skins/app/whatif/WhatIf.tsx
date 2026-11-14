import { Suspense, useEffect, useMemo, useRef, type ReactNode } from 'react'
import {
  Scene, SceneBoundary, runTool, useBuildingView, useWorkspace,
  type Block, type SceneCamera, type SceneMode, type ScanPlan, type Source,
} from '../../../core/index.ts'
import { Icon, Menu, MenuBtn, RunState, SourceChip } from '../design/ui.tsx'
import { useScheme } from '../shell/theme.ts'
import './whatif.css'

/* What if: renovations proposed or chosen here run as the `renovate` tool. Its result is an ordinary panel (verdict,
   cost, flipped checks, the ranked edits, the unit costs with their sources), and its action bar names the renovated
   plan, a `w_` scan that loads like any other. This file draws the menu and the side-by-side scene. */

const GOALS = [
  { id: 'wheelchair_ready', label: 'Wheelchair-ready home', hint: 'Doors, the route to every room, turning circles, grab bars' },
  { id: 'bathroom_route', label: 'Step-free route to the bathroom', hint: 'Doors and steps between the entrance and the bathroom' },
  { id: 'bathroom_turn', label: 'Turning circle in the bathroom', hint: 'Move or take out a bathroom wall' },
  { id: 'door_widths', label: 'Doors 32 in clear', hint: 'Every doorway but closets' },
] as const
const DOOR_36_M = 0.915 // a 36 in door: about 865 mm clear once hung
type MetricRowBlock = Extract<Block, { type: 'MetricRow' }>

/** The latest what-if on this scan: its panel, its run, and the renovated plan's scan id. */
export function useWhatIf(sid: string) {
  const panel = useWorkspace((s) => s.doc.panels.findLast((p) => p.tool === 'renovate' && p.sid === sid))
  const run = useWorkspace((s) => s.doc.runs.findLast((r) => r.tool === 'renovate' && r.sid === sid))
  const after = useMemo(() => {
    for (const b of panel?.blocks ?? []) {
      if (b.type !== 'ActionBar') continue
      const s = b.actions.map((a) => a.inputs?.scan).find((x): x is string => typeof x === 'string' && x.startsWith('w_'))
      if (s) return s
    }
    return null
  }, [panel])
  const metrics = panel?.blocks.find((b): b is MetricRowBlock => b.type === 'MetricRow')?.metrics ?? []
  return { panel, run, after, metrics, running: run?.status === 'running' }
}

const roomName = (plan: ScanPlan, id: string) => plan.rooms.find((r) => r.id === id)?.label ?? 'room'
const between = (plan: ScanPlan, rooms: string[]) => (rooms.length > 1 ? rooms.map((r) => roomName(plan, r)).join(' to ') : `${roomName(plan, rooms[0])} to outside`)
const cm = (m: number) => `${Math.round(m * 100)} cm`
const span = (w: ScanPlan['walls'][number]) => Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]) // the plan's own wall ends: a length to tell walls apart, not a result

/** The header's "What if" menu: a goal the tool plans for itself, or one edit the person picks. */
export function WhatIfMenu({ sid, plan }: { sid: string; plan: ScanPlan }) {
  const { running } = useWhatIf(sid)
  const walls = plan.quality?.walls ?? false
  // doorways a 36 in door would widen, narrowest first; walls between two rooms, one per pair of rooms (the longest)
  const doors = useMemo(() => plan.openings.filter((o) => o.type === 'doorway' && o.width != null && o.width < DOOR_36_M - 0.005 && o.width >= 0.4 && o.rooms.length)
    .sort((a, b) => (a.width ?? 0) - (b.width ?? 0)), [plan])
  const walled = useMemo(() => {
    const best = new Map<string, ScanPlan['walls'][number]>()
    for (const w of plan.walls) {
      if (w.type !== 'wall' || w.rooms.length !== 2) continue
      const k = [...w.rooms].sort().join('|'), had = best.get(k)
      if (!had || span(w) > span(had)) best.set(k, w)
    }
    return [...best.values()]
  }, [plan])
  const go = (inputs: Record<string, unknown>) => void runTool('renovate', inputs, sid)
  const trigger = (
    <button type="button" className="btn" disabled={!walls || running} title={walls ? 'Try renovations on a copy of this plan' : 'This scan has no wall graph, so there is nothing to edit'}>
      {running ? <RunState state="running">Working out the edits</RunState> : <><Icon name="split" size={13} />What if<Icon name="down" size={11} /></>}
    </button>
  )
  return (
    <MenuBtn align="end" trigger={trigger}>
      <div className="mh">What would it take</div>
      {GOALS.map((g) => (
        <Menu.Item key={g.id} onClick={() => go({ goal: g.id })} className="wi-goal">
          <span className="grow"><span>{g.label}</span><small className="muted">{g.hint}</small></span>
        </Menu.Item>
      ))}
      <Menu.Item onClick={() => go({ goal: 'wheelchair_ready', city: true })} className="wi-goal">
        <span className="grow"><span>Wheelchair-ready, and count the city</span><small className="muted">The same, then how many homes nearby would pass, on a throwaway database fork (about a minute)</small></span>
      </Menu.Item>
      <hr />
      <div className="mh">One edit</div>
      <Menu.SubmenuRoot>
        <Menu.SubmenuTrigger disabled={!doors.length}><Icon name="ruler" />Widen a door to 36 in<small>{doors.length}</small><Icon name="right" size={11} /></Menu.SubmenuTrigger>
        <Menu.Portal><Menu.Positioner sideOffset={2} alignOffset={-4} style={{ zIndex: 61 }}><Menu.Popup className="menu">
          {doors.map((o) => (
            <Menu.Item key={o.id} onClick={() => go({ goal: 'door_widths', edits: [{ op: 'widen_door', opening: o.id, width_m: DOOR_36_M }] })}>
              <span className="grow trunc">{between(plan, o.rooms)}</span><span className="num muted">{cm(o.width!)}</span>
            </Menu.Item>
          ))}
        </Menu.Popup></Menu.Positioner></Menu.Portal>
      </Menu.SubmenuRoot>
      <Menu.SubmenuRoot>
        <Menu.SubmenuTrigger disabled={!walled.length}><Icon name="trash" />Take out a wall<small>{walled.length}</small><Icon name="right" size={11} /></Menu.SubmenuTrigger>
        <Menu.Portal><Menu.Positioner sideOffset={2} alignOffset={-4} style={{ zIndex: 61 }}><Menu.Popup className="menu">
          {walled.map((w) => (
            <Menu.Item key={w.id} onClick={() => go({ goal: 'wheelchair_ready', edits: [{ op: 'remove_wall', wall: w.id }] })}>
              <span className="grow trunc">{between(plan, w.rooms)}</span><span className="num muted">{span(w).toFixed(2)} m</span>
            </Menu.Item>
          ))}
        </Menu.Popup></Menu.Positioner></Menu.Portal>
      </Menu.SubmenuRoot>
      <hr />
      <p className="wi-fine">Edits apply to a copy of the plan. The panoramas are not re-read, and costs are national averages, not a quote.</p>
    </MenuBtn>
  )
}

/** Now and after, side by side. `children` is the page's own scene of the building as it is. The wrapper stays
    mounted when the comparison closes, so that scene is never rebuilt; open, the renovated plan loads beside it with
    the same edits marked and follows the left camera. */
export function CompareScenes({ open, sid, after, mode, cameraRef, children }: { open: boolean; sid: string; after: string | null; mode: SceneMode; cameraRef: React.MutableRefObject<((c: SceneCamera) => void) | null>; children: ReactNode }) {
  const w = useWhatIf(sid)
  const pick = (id: string) => w.metrics.find((m) => m.id === id)
  const before = pick('failing_before')
  const on = open && !!after
  return (
    <div className="wi-split" data-open={on}>
      <figure className="wi-pane">
        {on && <figcaption><b>Now</b>{before?.value != null && <span className="muted">{before.value} failing</span>}</figcaption>}
        {children}
      </figure>
      {on && <AfterPane sid={sid} after={after!} mode={mode} cameraRef={cameraRef} metric={pick} />}
    </div>
  )
}

function AfterPane({ sid, after, mode, cameraRef, metric }: { sid: string; after: string; mode: SceneMode; cameraRef: React.MutableRefObject<((c: SceneCamera) => void) | null>; metric: (id: string) => { value: number | null; source: Source } | undefined }) {
  const scheme = useScheme()
  const a = useBuildingView(after, { tools: [] })
  const overlays = useWorkspace((s) => s.doc.overlays)
  const marks = useMemo(() => overlays.filter((o) => o.tool === 'renovate' && o.sid === sid).map((o) => o.overlay), [overlays, sid])
  // the right scene follows the left one's camera, rounded so a drag does not send it a flight every frame
  const last = useRef('')
  useEffect(() => {
    cameraRef.current = (c) => {
      const pose = { bearing: Math.round(c.bearing), pitch: Math.round(c.pitch), range: Math.round(c.range * 4) / 4 }
      const k = JSON.stringify(pose)
      if (k === last.current) return
      last.current = k
      a.setView((x) => ({ ...x, pose }))
    }
    return () => { cameraRef.current = null }
  }) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { a.setView((x) => ({ ...x, cut: 1.4, surface: 'model', measures: true, frame: { top: -20, right: 20, bottom: -20, left: 20 } })) }, [after]) // eslint-disable-line react-hooks/exhaustive-deps
  // the renovated plan has no panoramas or drone capture of its own: it shows the plan or the 3D model
  useEffect(() => { a.setMode(mode === 'plan' ? 'plan' : 'dollhouse') }, [mode]) // eslint-disable-line react-hooks/exhaustive-deps
  const loaded = !!a.sceneProps
  useEffect(() => { if (!loaded) return; const t = setTimeout(a.stepBack, 400); return () => clearTimeout(t) }, [loaded]) // eslint-disable-line react-hooks/exhaustive-deps
  const cost = metric('total_cost'), fixed = metric('fixed'), left = metric('failing_after')
  return (
    <figure className="wi-pane">
      <figcaption>
        <b>After the edits</b>
        {left?.value != null && <span className="muted">{left.value} failing</span>}
        {fixed?.value != null && <span className="muted">{fixed.value} fixed</span>}
        {cost?.value != null && <span className="wi-cost"><span className="num">${Math.round(cost.value).toLocaleString('en-US')}</span><SourceChip source={cost.source} /></span>}
      </figcaption>
      {a.error && <div className="scene-state"><span className="muted small">{a.error}</span></div>}
      {!a.sceneProps && !a.error && <div className="scene-state loading" role="status"><span className="sk" /><span className="sk" /><span className="muted small">Loading the renovated plan</span></div>}
      {a.sceneProps && (
        <Suspense fallback={<div className="scene-state loading" role="status"><span className="sk" /><span className="muted small">Loading the building view</span></div>}>
          <SceneBoundary key={`${a.sceneKey}:${scheme}`} fallback={<div className="scene-state"><span className="muted small">The renovated view stopped.</span></div>}>
            <Scene {...a.sceneProps} overlays={marks as typeof a.sceneProps.overlays} className="app-scene" switcher={false} />
          </SceneBoundary>
        </Suspense>
      )}
    </figure>
  )
}
