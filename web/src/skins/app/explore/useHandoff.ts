import { useEffect, useMemo, useRef, useState } from 'react'
import { cameraOf, fetchPlan, fetchSite, stand, type Pose, type ScanPlan, type SceneCamera, type SceneState, type SceneView, type Stand } from '../../../core/index.ts'
import { useWorld } from './WorldMap.tsx'

/* The hand-off between the map and the building scene, both in one rectangle.

   In: the map flies to a camera the scene can hold (the building whole, on its site), the scene is told to stand
   at the same camera behind it, and when both are there and the scene has its surroundings it fades in over the
   map. Then the scene carries on in to the building, and opens it. Out: when the person pulls the scene back past
   a range, the map is put at the scene's camera and the scene fades out. The two pictures are the same city mesh
   through the same lens, so the swap is a cross-fade between two drawings of one view.

   map       the map is in front
   approach  a scan was opened from the map: the map is flying to the hand-off camera, the scene loads behind it
   ready     the scene is in front
   leaving   the scene is fading out over the map */
export type Phase = 'map' | 'approach' | 'ready' | 'leaving'
/** The building page sets `frame: { left: -100, right: 20 }`, which puts its picture's centre 60 px left of the
    middle. The same shift on the map, as MapLibre's padding. */
const PAD = { top: 0, bottom: 0, left: 0, right: 120 }
const GIVE_UP_MS = 14000
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
type Bound = { plan: ScanPlan; setView: (fn: (v: SceneView) => SceneView) => void }

export function useHandoff(sid: string | null, stage: HTMLElement | null, onLeave: () => void) {
  const map = useWorld((s) => s.map)
  const [phase, setPhase] = useState<Phase>(sid ? 'ready' : 'map') // a link straight to a scan opens on the building
  const [landed, setLanded] = useState(true) // the map's flight to the building is over: the scene may load
  const now = useRef<Phase>(phase); now.current = phase
  const s = useRef<{ stand: Stand | null; pose: Pose | null; bound: Bound | null; cam: SceneCamera | null; aerial: boolean; flown: boolean; world: number; posed: boolean; since: number }>(
    { stand: null, pose: null, bound: null, cam: null, aerial: false, flown: false, world: 0, posed: false, since: 0 })
  const leave = useRef(onLeave); leave.current = onLeave
  useEffect(() => { if (stage) (stage as unknown as { __hand?: unknown }).__hand = s.current }, [stage]) // check scripts read the hand-off's state here
  const before = useRef<string | null>(sid)

  /** Stand the scene at the hand-off camera, once it and the camera are both known. */
  const pose = () => {
    const x = s.current
    if (now.current !== 'approach' || x.posed || !x.bound || !x.pose) return
    x.posed = true
    const p = x.pose
    x.bound.setView((v) => ({ ...v, mode: 'dollhouse', env: 'aerial', pose: p }))
  }
  const reveal = () => {
    if (now.current !== 'approach') return
    setPhase('ready')
    const x = s.current, p = x.pose
    // the scene is in front: carry on in to the building, which opens on the way
    if (new URLSearchParams(location.search).has('app_hold')) return // a check script compares the two pictures at this camera
    if (p && x.bound) setTimeout(() => x.bound?.setView((v) => ({ ...v, pose: { bearing: p.bearing, pitch: p.pitch, range: 'fit' } })), reduced() ? 0 : 420)
  }
  /** Both cameras are in place and the scene has drawn its surroundings: swap. */
  const check = () => {
    const x = s.current, p = x.pose, c = x.cam
    if (now.current !== 'approach') return
    if (performance.now() - x.since > GIVE_UP_MS) { reveal(); return }
    const mesh = useWorld.getState().mesh
    if (!p || !c || !x.flown || !x.world || performance.now() - x.world < 1300) return
    if (mesh && mesh.status !== 'none' && !(mesh.key === `sid:${before.current}` && mesh.status === 'ready')) return // the map still draws its roaming patch, not this scan's
    const turn = Math.abs(((c.bearing - p.bearing + 540) % 360) - 180)
    if (!c.moving && Math.abs(c.range - p.range) < p.range * 0.01 && turn < 0.3 && Math.abs(c.pitch - p.pitch) < 0.3) reveal()
  }

  // A scan is opened, changed or closed.
  useEffect(() => {
    const was = before.current; before.current = sid
    const x = s.current
    Object.assign(x, { stand: null, pose: null, cam: null, flown: false, world: 0, posed: false, since: performance.now() })
    if (!sid) { setPhase('map'); setLanded(true); return }
    const m = useWorld.getState().map, fromMap = was == null && !!m
    setPhase(fromMap ? 'approach' : 'ready'); setLanded(!fromMap)
    const land = () => { x.flown = true; setLanded(true) }
    let on = true
    Promise.all([fetchPlan(sid), fetchSite(sid)]).then(([plan, site]) => {
      const map = useWorld.getState().map, mesh = useWorld.getState().mesh
      if (!on) return
      if (!site.available || !map || !stage) { land(); if (now.current === 'approach') setPhase('ready'); return } // no place in the world: a plain fade
      const r = stage.getBoundingClientRect()
      const st = x.stand = stand(plan as never, site, { w: r.width, h: r.height })
      void mesh?.want({ sid }, st.ring)
      mesh?.setShown(true)
      const p = x.pose = { bearing: map.getBearing(), pitch: Math.min(76, Math.max(map.getPitch(), 50)), range: st.enter }
      const cam = cameraOf(st, p)
      const to = { ...map.calculateCameraOptionsFromCameraLngLatAltRotation(cam.lngLat, cam.altitude, p.bearing, p.pitch), padding: PAD }
      if (now.current !== 'approach' || reduced()) { map.jumpTo(to); land() }
      else {
        map.once('moveend', land)
        const far = map.getZoom() < 15.5 || !map.getBounds().contains(to.center as [number, number])
        if (far) map.flyTo({ ...to, duration: 2400, curve: 1.3, essential: true }); else map.easeTo({ ...to, duration: 1000, essential: true })
      }
      pose()
    }, () => { if (on) { land(); if (now.current === 'approach') setPhase('ready') } })
    return () => { on = false }
  }, [sid, stage]) // eslint-disable-line react-hooks/exhaustive-deps

  // A link that opened on a building: put the map behind it once there is a map, so zooming out lands somewhere.
  useEffect(() => {
    const x = s.current
    if (!map || now.current !== 'ready' || !x.stand || x.flown) return
    const p = { bearing: 0, pitch: 55, range: x.stand.enter }, cam = cameraOf(x.stand, p)
    map.jumpTo({ ...map.calculateCameraOptionsFromCameraLngLatAltRotation(cam.lngLat, cam.altitude, p.bearing, p.pitch), padding: PAD }); x.flown = true
  }, [map, phase])

  useEffect(() => {
    if (phase !== 'approach') return
    const t = setInterval(check, 120)
    return () => clearInterval(t)
  }, [phase]) // eslint-disable-line react-hooks/exhaustive-deps

  /** What the building page is given: it reports the scene's camera and state here, and hands over its view. */
  const host = useMemo(() => ({
    bind: (b: Bound | null) => { s.current.bound = b; if (b) pose() },
    onState: (st: SceneState) => {
      const x = s.current
      x.aerial = st.site || st.world.status === 'ready'
      // its surroundings are in, and the drone capture too where the house is drawn from one
      const drawn = st.world.status === 'missing' || (st.world.status === 'ready' && (!st.site || st.splat.status === 'ready' || st.splat.status === 'missing'))
      if (!x.world && drawn) x.world = performance.now()
    },
    onCamera: (c: SceneCamera) => {
      const x = s.current
      x.cam = c
      const st = x.stand, m = useWorld.getState().map
      if (now.current !== 'ready' || !st || !m || c.moving || (c.mode !== 'dollhouse' && c.mode !== 'splat')) return
      if (c.range < (x.aerial ? st.leave : st.leaveAlone)) return
      // pulled right back: the map takes over at the scene's own camera
      const cam = cameraOf(st, { bearing: c.bearing, pitch: Math.min(c.pitch, 79), range: c.range })
      m.jumpTo({ ...m.calculateCameraOptionsFromCameraLngLatAltRotation(cam.lngLat, cam.altitude, cam.bearing, cam.pitch), padding: PAD })
      setPhase('leaving')
      setTimeout(() => leave.current(), reduced() ? 0 : 300)
    },
  }), []) // eslint-disable-line react-hooks/exhaustive-deps

  return { phase, host, hold: phase === 'approach' && !landed }
}
