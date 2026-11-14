// One canvas, one camera, four views. The engine owns three.js; React (BuildingScene.tsx) only hands it props.
import * as THREE from 'three'
import { buildModel, centroid, isKnownOverlay, resolveStyles, STUB, type Model } from '../model.ts'
import { useSceneLink } from '../store.ts'
import { readTokens, type Tokens } from '../tokens.ts'
import type { Anchor, Mode, Overlay, Pano, Pick, ScanPlan, Vec3, View } from '../types.ts'
import { anchorPoint } from '../model.ts'
import { Dollhouse } from './dollhouse.ts'
import { h, Labels, type LabelSpec } from './labels.ts'
import { Overlays3D } from './overlays.ts'
import { PanoView } from './pano.ts'
import { reducedMotion, Rig } from './rig.ts'
import { SplatView } from './splat.ts'

export interface SceneState {
  mode: Mode; loading: boolean; pano: string | null; hasEmpty: boolean; noWalls: boolean
  splat: { status: SplatView['status']; progress: number; splats: number; total: number }
}
/** Per-frame facts the React layer applies straight to the DOM (no re-render): the plan transform and the view cone. */
export interface FrameInfo {
  plan: { presence: number; scale: number; tx: number; ty: number; floor: number }
  look: { x: number; y: number; yaw: number; fov: number } | null
  width: number; height: number
}
export interface EngineOpts {
  api: string
  onPick: (p: Pick) => void
  onViewChange: (v: View) => void
  onState: (s: SceneState) => void
  onFrame: (f: FrameInfo) => void
}

const DOLL_FOV = 32, PLAN_FOV = 14, PANO_FOV = 76

export class Engine {
  readonly model: Model
  readonly tokens: Tokens
  readonly labels: Labels
  view: View = { mode: 'dollhouse' }
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private rig = new Rig()
  private doll: Dollhouse
  private overlays3d: Overlays3D
  private pano: PanoView
  private splat: SplatView
  private overlays: Overlay[] = []
  private overlayLabels: LabelSpec[] = []
  private roomLabels: LabelSpec[]
  private w = 1; private h = 1
  private dirty = true; private raf = 0; private last = 0
  private panoPresence = { cur: 0, goal: 0 }; private planPresence = { cur: 0, goal: 0 }
  private loading = 0
  private drift = false
  private splatAimed = false
  private stateKey = ''
  private unsub: () => void
  private ro: ResizeObserver
  private pointers = new Map<number, { x: number; y: number }>()
  private drag = { moved: 0, t: 0, vx: 0, vy: 0, last: 0, button: 0 }
  private hoverAt: { x: number; y: number } | null = null
  private raycaster = new THREE.Raycaster()
  private listeners = new AbortController()
  frames = 0 // rendered frames, for the lab's frame-rate readout

  private el: HTMLElement; private opts: EngineOpts
  constructor(el: HTMLElement, plan: ScanPlan, opts: EngineOpts) {
    this.el = el; this.opts = opts
    this.tokens = readTokens(el)
    this.model = buildModel(plan)
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    this.renderer.setClearColor(new THREE.Color().setRGB(...this.tokens.stage, THREE.SRGBColorSpace))
    this.renderer.domElement.className = 'th-canvas'
    el.prepend(this.renderer.domElement)

    this.doll = new Dollhouse(this.model, this.tokens, opts.api)
    this.doll.onChange = this.invalidate
    this.overlays3d = new Overlays3D(this.model, this.tokens, this.doll, (p) => this.emitPick(p))
    this.pano = new PanoView(opts.api, plan.sid, plan.has.defurnished)
    this.pano.onLoad = () => { this.invalidate(); this.pushState() }
    this.splat = new SplatView(this.renderer, this.scene, opts.api, plan.sid)
    this.splat.onChange = () => {
      if (this.view.mode === 'splat' && this.splat.splats && !this.splatAimed) { this.splatAimed = true; this.rig.flyTo({ target: this.splat.centre.clone() }, 700) } // flyTo keeps the orbit distance; a nudge would freeze the move mid-way
      this.invalidate(); this.pushState()
    }
    this.scene.add(this.pano.group, this.doll.group, this.overlays3d.group, this.splat.group)

    this.labels = new Labels(this.model)
    el.appendChild(this.labels.root)
    this.roomLabels = this.model.plan.rooms.filter((r) => r.polygon.length > 2 && r.label !== 'Void').map((r) => {
      const c = centroid(r.polygon), f = this.model.floorOf.get(r.floor) ?? 0
      return {
        id: `room.${r.id}`, pos: [c[0], c[1], this.model.floorZ[f] + 0.05] as Vec3, floor: f, spanM: Math.sqrt(r.area ?? 4), minPx: r.label ? 62 : 74, modes: ['doll' as const], ride: r.height ?? this.model.floorH[f], elem: this.model.roomElem.get(r.id),
        make: () => h('div', 'th-room', ...(r.label ? [h('span', 'th-room-name', r.label)] : []), ...(r.area ? [h('span', 'th-num', `${r.area.toFixed(1)} m²`)] : [])),
      }
    })

    this.applyStyles(true)
    this.setOverlays([])
    this.unsub = useSceneLink.subscribe(() => { this.applyStyles(); this.syncDots() })
    this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(el); this.resize()
    this.enterMode('dollhouse', 'dollhouse'); this.rig.flyTo(this.dollPose(), 0)
    this.bindInput()
    this.raf = requestAnimationFrame(this.frame)
    this.pushState()
    ;(el as unknown as { __engine?: Engine }).__engine = this // the lab's benchmark button finds the engine here
  }

  // ---- props -------------------------------------------------------------------------------------------------------

  setOverlays(overlays: Overlay[]) {
    this.overlays = overlays.filter(isKnownOverlay) // Contract 4: unknown kinds are ignored
    this.overlayLabels = this.overlays3d.set(this.overlays, !!this.view.measures, this.eye())
    this.labels.sync([...this.roomLabels, ...this.overlayLabels])
    this.applyStyles()
    this.invalidate()
  }

  setView(next: View) {
    const prev = this.view
    this.view = { ...next }
    const m = this.model, floorIdx = next.floor ? m.floorOf.get(next.floor) ?? null : null
    if (next.mode !== prev.mode) this.enterMode(next.mode, prev.mode)
    else if (next.mode === 'pano' && next.pano && next.pano !== this.pano.current?.id) this.goPano(next.pano, false)
    if (next.mode === 'plan' && next.floor !== prev.floor && next.mode === prev.mode) this.rig.flyTo(this.planPose(), 600)
    this.doll.setFloorShown((f) => floorIdx === null || f <= floorIdx)
    this.doll.setCut(next.mode === 'plan' ? 0 : next.cut ?? 99)
    this.doll.anim.explode.goal = next.mode === 'dollhouse' ? next.explode ?? 0 : 0
    this.pano.setWipe(next.wipe ?? null, this.w * this.renderer.getPixelRatio())
    if (!!next.measures !== !!prev.measures) this.setOverlays(this.overlays)
    if (next.focus && JSON.stringify(next.focus) !== JSON.stringify(prev.focus)) this.focusOn(next.focus)
    this.pushState(); this.invalidate()
  }

  /** Where the viewer stands when inside a panorama; null in every other view. */
  private eye() { const p = this.pano.current; return this.view.mode === 'pano' && p ? { pos: p.position, floorId: p.floor } : null }
  private panoContext() { this.doll.setEye(this.eye()); this.setOverlays(this.overlays); this.syncDots() }

  // ---- poses -------------------------------------------------------------------------------------------------------

  private centre(floor = -1) {
    const b = floor >= 0 ? this.model.floorBounds[floor] : this.model.bounds
    return new THREE.Vector3((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2, floor >= 0 ? this.model.floorZ[floor] : 1)
  }
  private radius() { const b = this.model.bounds; return Math.max(4, Math.hypot(b.maxX - b.minX, b.maxY - b.minY) / 2) }
  private dollPose() {
    const tall = this.model.floorZ[this.model.floorZ.length - 1] + this.model.maxH
    // fit the footprint to the narrower of the two view angles, so a phone-shaped viewport still shows the whole building
    const half = (DOLL_FOV * Math.PI) / 360, fit = Math.min(half, Math.atan(Math.tan(half) * (this.w / this.h)))
    return { target: this.centre().setZ(tall * 0.3), az: -2.05, pol: 0.86, dist: ((this.radius() + tall * 0.25) / Math.sin(fit)) * 0.66, fov: DOLL_FOV }
  }
  private planFloor() { return (this.view.floor && this.model.floorOf.get(this.view.floor)) || 0 }
  private planPose() {
    const f = this.planFloor(), b = this.model.floorBounds[f]
    const s = Math.min(this.w / (b.maxX - b.minX + 3), this.h / (b.maxY - b.minY + 3))
    return { target: this.centre(f), az: -Math.PI / 2, pol: 0.0005, dist: this.h / 2 / (s * Math.tan((PLAN_FOV * Math.PI) / 360)), fov: PLAN_FOV }
  }

  private enterMode(mode: Mode, from: Mode) {
    const rig = this.rig, L = rig.limits, R = this.radius()
    this.drift = false
    this.panoPresence.goal = mode === 'pano' ? 1 : 0
    this.planPresence.goal = mode === 'plan' ? 1 : 0
    this.doll.anim.reveal.goal = mode === 'splat' ? 0 : 1
    this.splat.show(mode === 'splat')
    if (mode !== 'pano') { this.doll.setPanoMode(false); this.panoContext() }
    if (mode === 'dollhouse') {
      Object.assign(L, { minPol: 0.05, maxPol: 1.5, minDist: 2, maxDist: R * 9, minFov: DOLL_FOV, maxFov: DOLL_FOV })
      const p = this.dollPose()
      rig.flyTo(from === 'pano' ? { ...p, az: rig.pose.az } : from === 'splat' ? { ...p, az: rig.pose.az } : p, from === 'pano' ? 1250 : 1050)
    } else if (mode === 'plan') {
      Object.assign(L, { minPol: 0.0005, maxPol: 0.0005, minDist: 3, maxDist: R * 30, minFov: PLAN_FOV, maxFov: PLAN_FOV })
      rig.flyTo(this.planPose(), 1000)
    } else if (mode === 'pano') {
      Object.assign(L, { minPol: 0.35, maxPol: 2.8, minDist: 0.02, maxDist: 0.02, minFov: 34, maxFov: 96 })
      const start = this.view.pano ?? this.nearestPano(rig.pose.target.x, rig.pose.target.y)?.id
      if (start) this.goPano(start, true)
    } else {
      Object.assign(L, { minPol: 0.25, maxPol: 1.5, minDist: 8, maxDist: 160, minFov: DOLL_FOV, maxFov: DOLL_FOV })
      const c = this.splat.status === 'ready' ? this.splat.centre : new THREE.Vector3(0, 0, 2)
      rig.flyTo({ target: c.clone(), az: rig.pose.az, pol: 1.08, dist: 58, fov: DOLL_FOV }, 1300)
      this.drift = !reducedMotion()
    }
    this.syncDots()
  }

  private nearestPano(x: number, y: number, roomId?: string): Pano | null {
    let best: Pano | null = null, bd = Infinity
    for (const p of this.model.plan.panos) {
      if (roomId && p.room !== roomId) continue
      const d = Math.hypot(p.position[0] - x, p.position[1] - y)
      if (d < bd) { bd = d; best = p }
    }
    return best
  }

  /** Walk (or dive) to a scan position: load its faces first, then move, so the move never lands on a blank view. */
  private goPano(id: string, dive: boolean) {
    const p = this.model.plan.panos.find((q) => q.id === id)
    if (!p) return
    this.loading++; this.pushState()
    this.pano.show(p).then(() => {
      if (this.view.mode !== 'pano') return
      const rig = this.rig
      const f = this.view.focus, aim = f && 'pano' in f && f.pano === id ? f : null // "stand here and look that way"
      const az = aim ? (aim.yaw_deg * Math.PI) / 180 + Math.PI : rig.goal.az
      const pol = aim ? Math.PI / 2 + (aim.pitch_deg * Math.PI) / 180 : dive ? Math.PI / 2 : rig.goal.pol
      rig.flyTo({ target: new THREE.Vector3(...p.position), az, pol, dist: 0.02, fov: dive ? PANO_FOV : rig.goal.fov }, dive ? 1350 : 800)
      this.panoContext(); this.invalidate()
    }).catch((e) => { if ((e as Error).message !== 'superseded') console.warn('[scene] panorama failed to load', e) })
      .finally(() => { this.loading--; this.pushState() })
  }

  private focusOn(a: Anchor) {
    const at = anchorPoint(this.model, a)
    if (!at) return
    const t = new THREE.Vector3(at.point[0], at.point[1], at.point[2] + (this.doll.floorZ(at.floor) - this.model.floorZ[at.floor]))
    const rig = this.rig, mode = this.view.mode
    if (mode === 'pano') { // turn to face it
      const e = rig.pose.target
      rig.flyTo({ az: Math.atan2(e.y - t.y, e.x - t.x), pol: Math.PI / 2 + Math.atan2(t.z - e.z, Math.hypot(t.x - e.x, t.y - e.y)) }, 700)
    } else if (mode === 'plan') rig.flyTo({ target: t.setZ(this.model.floorZ[this.planFloor()]), dist: Math.min(rig.goal.dist, this.planPose().dist * 0.45) }, 800)
    else if (mode === 'dollhouse') rig.flyTo({ target: t, dist: Math.max(9, this.radius() * 0.9), pol: Math.min(rig.goal.pol, 0.8) }, 900)
  }

  // ---- styles, dots, state -----------------------------------------------------------------------------------------

  private applyStyles(instant = false) {
    const { hover, selected } = useSceneLink.getState()
    this.doll.setStyles(resolveStyles(this.model, this.overlays, this.tokens, hover, selected), instant)
    this.invalidate()
  }
  private syncDots() {
    const { hover } = useSceneLink.getState(), cur = this.pano.current, inPano = this.view.mode === 'pano'
    const near = new Set(inPano && cur ? cur.neighbors : [])
    this.doll.setDotStates((id) => (hover?.kind === 'pano' && hover.id === id ? 2 : near.has(id) ? 1 : 0))
    this.invalidate()
  }
  private pushState() {
    const s: SceneState = {
      mode: this.view.mode, loading: this.loading > 0 || (this.view.mode === 'splat' && this.splat.status === 'loading'), pano: this.pano.current?.id ?? null,
      hasEmpty: this.pano.hasEmpty, noWalls: !this.model.hasWalls,
      splat: { status: this.splat.status, progress: Math.round(this.splat.progress * 50) / 50, splats: this.splat.splats, total: this.splat.total },
    }
    const key = JSON.stringify(s)
    if (key !== this.stateKey) { this.stateKey = key; this.opts.onState(s) }
  }
  private emitPick(p: Pick) { useSceneLink.getState().setSelected(p.kind === 'pano' ? null : p); this.opts.onPick(p) }
  invalidate = () => { this.dirty = true }
  /** Keyboard: turn, tilt and zoom by steps. */
  step(turn: number, tilt: number, zoom: number) {
    const pano = this.view.mode === 'pano'
    this.rig.nudge((g) => { g.az += turn * (pano ? -0.12 : 0.12); g.pol += tilt * 0.08; if (pano) g.fov *= 1 + zoom * 0.1; else g.dist *= 1 + zoom * 0.12 })
  }

  // ---- loop --------------------------------------------------------------------------------------------------------

  private frame = (now: number) => {
    this.raf = requestAnimationFrame(this.frame)
    const dt = Math.min(0.05, (now - this.last) / 1000 || 0.016); this.last = now
    if (this.drift && this.view.mode === 'splat' && !this.rig.moving) this.rig.goal.az += dt * 0.05
    let moving = this.rig.update(dt)
    // the panorama fades in over the last stretch of the dive, and out as the camera pulls back
    const pp = this.panoPresence, target = pp.goal === 1 && this.pano.current ? Math.min(1, Math.max(0, 1.6 - this.rig.pose.dist / 3)) : 0
    if (pp.cur !== target) { pp.cur += Math.sign(target - pp.cur) * Math.min(Math.abs(target - pp.cur), dt / 0.3); moving = true }
    this.doll.setPanoMode(this.view.mode === 'pano' && pp.cur > 0.985)
    const pl = this.planPresence, planReady = pl.goal === 1 && this.rig.pose.pol < 0.02 && !this.rig.moving ? 1 : 0
    if (pl.cur !== planReady) { pl.cur += Math.sign(planReady - pl.cur) * Math.min(Math.abs(planReady - pl.cur), dt / (planReady ? 0.28 : 0.12)); moving = true }
    if (this.doll.update(dt)) moving = true
    if (this.overlays3d.update(dt)) moving = true
    if (this.pano.update(dt, pp.cur)) moving = true
    if (this.splat.update(dt)) moving = true
    if (this.hoverAt && !moving) { this.hover(this.hoverAt.x, this.hoverAt.y); this.hoverAt = null }
    if (!moving && !this.dirty) return
    this.dirty = false
    const reveal = this.doll.anim.reveal.cur
    this.doll.group.visible = reveal > 0.003; this.overlays3d.group.visible = reveal > 0.5
    this.renderer.render(this.scene, this.rig.camera)
    this.frames++
    const inPano = pp.cur > 0.5 && this.pano.current
    this.labels.update(this.rig.camera, this.w, this.h, (f) => this.doll.floorZ(f) - this.model.floorZ[f], (elem, full) => Math.min(full, this.doll.anim.cut.cur, elem !== undefined && this.doll.heightOf(elem) < 0.5 ? STUB : 99) * this.doll.anim.reveal.cur, (f) => this.doll.floorGroups[f]?.visible ?? false,
      inPano ? { eye: this.pano.current!.position, floorId: this.pano.current!.floor } : null, Math.min(reveal, 1 - pl.cur) * (pp.cur > 0.02 && pp.cur < 0.98 ? 0 : 1))
    const p = this.rig.pose, s = this.rig.pxPerMetre(this.h)
    const eye = this.rig.camera.position
    this.opts.onFrame({
      plan: { presence: pl.cur, scale: s, tx: this.w / 2 - s * p.target.x, ty: this.h / 2 + s * p.target.y, floor: this.planFloor() },
      look: this.view.mode === 'splat' ? null : { x: inPano ? p.target.x : eye.x, y: inPano ? p.target.y : eye.y, yaw: p.az + Math.PI, fov: (p.fov * Math.PI) / 180 * (this.w / this.h) },
      width: this.w, height: this.h,
    })
  }

  private resize() {
    const r = this.el.getBoundingClientRect()
    this.w = Math.max(1, r.width); this.h = Math.max(1, r.height)
    this.renderer.setSize(this.w, this.h)
    this.rig.camera.aspect = this.w / this.h; this.rig.apply()
    this.doll.setSize(this.w, this.h); this.overlays3d.setSize(this.w, this.h)
    this.pano.setWipe(this.view.wipe ?? null, this.w * this.renderer.getPixelRatio())
    this.invalidate()
  }

  // ---- input -------------------------------------------------------------------------------------------------------

  private ray(x: number, y: number) {
    const r = this.el.getBoundingClientRect()
    this.raycaster.setFromCamera(new THREE.Vector2(((x - r.left) / this.w) * 2 - 1, -((y - r.top) / this.h) * 2 + 1), this.rig.camera)
    return this.raycaster.ray
  }
  private pickAt(x: number, y: number): Pick | null {
    if (this.view.mode === 'splat' || this.planPresence.cur > 0.5) return null // the plan picks through its own SVG
    return this.doll.pick(this.ray(x, y), { pano: this.view.mode === 'pano' })
  }
  private hover(x: number, y: number) {
    const p = this.pickAt(x, y)
    useSceneLink.getState().setHover(p)
    this.el.style.cursor = p && (p.kind === 'pano' || this.view.mode !== 'pano') ? 'pointer' : ''
  }

  private bindInput() {
    const el = this.el, rig = this.rig
    const onDown = (e: PointerEvent) => {
      if ((e.target as HTMLElement).closest('[data-scene-ui]')) return // rulers, sliders and pins handle themselves
      this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
      this.drag = { moved: 0, t: performance.now(), vx: 0, vy: 0, last: performance.now(), button: e.button }
      this.drift = false
    }
    const onMove = (e: PointerEvent) => {
      const prev = this.pointers.get(e.pointerId)
      if (!prev) { // plain hover; controls and the inset plan report their own
        if (e.pointerType === 'mouse') this.hoverAt = (e.target as HTMLElement).closest('[data-scene-ui]') ? null : { x: e.clientX, y: e.clientY }
        return
      }
      const dx = e.clientX - prev.x, dy = e.clientY - prev.y, mode = this.view.mode
      const now = performance.now(), dtm = Math.max(1, now - this.drag.last); this.drag.last = now
      if (this.pointers.size === 2) { // pinch: the distance between two fingers sets the zoom
        const other = [...this.pointers.entries()].find(([id]) => id !== e.pointerId)![1]
        const d0 = Math.hypot(prev.x - other.x, prev.y - other.y), d1 = Math.hypot(e.clientX - other.x, e.clientY - other.y)
        if (d0 > 0 && d1 > 0) rig.nudge((g) => { if (mode === 'pano') g.fov *= d0 / d1; else g.dist *= d0 / d1 })
      } else {
        this.drag.moved += Math.abs(dx) + Math.abs(dy)
        if (this.drag.moved < 4) { prev.x = e.clientX; prev.y = e.clientY; return } // hysteresis: a tap is not a drag
        if (!el.hasPointerCapture(e.pointerId)) el.setPointerCapture(e.pointerId)   // only a drag takes the pointer; a tap still reaches the plan
        const pan = mode === 'plan' || this.drag.button !== 0 || e.shiftKey
        if (mode === 'pano') {
          const k = ((rig.pose.fov * Math.PI) / 180) / this.h // grab the photo: it follows the pointer
          rig.nudge((g) => { g.az += dx * k; g.pol -= dy * k })
          this.drag.vx = (dx * k) / dtm * 1000; this.drag.vy = (-dy * k) / dtm * 1000
        } else if (pan) {
          const s = rig.pxPerMetre(this.h), c = rig.camera
          const right = new THREE.Vector3().setFromMatrixColumn(c.matrixWorld, 0), up = new THREE.Vector3().setFromMatrixColumn(c.matrixWorld, 1)
          if (mode !== 'plan') up.setZ(0).normalize().multiplyScalar(1 / Math.max(0.3, Math.cos(rig.pose.pol))) // slide along the floor
          rig.nudge((g) => g.target.addScaledVector(right, -dx / s).addScaledVector(up, dy / s))
        } else {
          rig.nudge((g) => { g.az -= dx * 0.0052; g.pol -= dy * 0.0052 })
          this.drag.vx = (-dx * 0.0052) / dtm * 1000; this.drag.vy = (-dy * 0.0052) / dtm * 1000
        }
      }
      prev.x = e.clientX; prev.y = e.clientY
    }
    const onUp = (e: PointerEvent) => {
      if (!this.pointers.delete(e.pointerId)) return
      const tap = this.drag.moved < 4 && performance.now() - this.drag.t < 450
      if (tap && this.drag.button === 0) this.click(e.clientX, e.clientY, e.detail >= 2)
      else if (this.view.mode !== 'plan' && performance.now() - this.drag.last < 60 && Math.hypot(this.drag.vx, this.drag.vy) > 0.25) {
        rig.nudge(() => {}, { az: this.drag.vx * 0.55, pol: this.drag.vy * 0.55 }) // a flick keeps turning, then settles
      }
    }
    const onWheel = (e: WheelEvent) => {
      if ((e.target as HTMLElement).closest('[data-scene-ui]')) return
      e.preventDefault(); this.drift = false
      const mode = this.view.mode, k = Math.exp(e.deltaY * 0.0014)
      if (mode === 'pano') { rig.nudge((g) => (g.fov += e.deltaY * 0.035)); return }
      if (mode === 'plan') { // keep the point under the pointer still
        const r = el.getBoundingClientRect(), s = rig.pxPerMetre(this.h, rig.goal.dist)
        const wx = rig.goal.target.x + (e.clientX - r.left - this.w / 2) / s, wy = rig.goal.target.y - (e.clientY - r.top - this.h / 2) / s
        rig.nudge((g) => { g.dist *= k; const s2 = s / k; g.target.x = wx - (e.clientX - r.left - this.w / 2) / s2; g.target.y = wy + (e.clientY - r.top - this.h / 2) / s2 })
      } else rig.nudge((g) => (g.dist *= k))
    }
    const onLeave = () => { this.hoverAt = null; useSceneLink.getState().setHover(null) }
    const signal = this.listeners.signal
    el.addEventListener('pointerdown', onDown, { signal }); el.addEventListener('pointermove', onMove, { signal })
    el.addEventListener('pointerup', onUp, { signal }); el.addEventListener('pointercancel', onUp, { signal })
    el.addEventListener('wheel', onWheel, { passive: false, signal }); el.addEventListener('pointerleave', onLeave, { signal })
    el.addEventListener('contextmenu', (e) => e.preventDefault(), { signal })
  }

  private click(x: number, y: number, double: boolean) {
    const p = this.pickAt(x, y)
    if (!p) { if (this.planPresence.cur < 0.5) useSceneLink.getState().setSelected(null); return }
    this.emitPick(p)
    if (p.kind === 'pano') this.opts.onViewChange({ ...this.view, mode: 'pano', pano: p.id })
    else if (double && p.kind === 'room' && this.view.mode === 'dollhouse') { // dive into the room
      const near = this.nearestPano(p.point[0], p.point[1], p.id) ?? this.nearestPano(p.point[0], p.point[1])
      if (near) this.opts.onViewChange({ ...this.view, mode: 'pano', pano: near.id })
    }
  }

  /** Lab only: orbit for four seconds, drawing every frame, and report how long frames took. */
  benchmark(): Promise<string> {
    return new Promise((done) => {
      const times: number[] = [], start = performance.now()
      let prev = start
      const gl = this.renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info')
      const tick = (now: number) => {
        times.push(now - prev); prev = now
        this.rig.nudge((g) => (g.az += 0.012)); this.invalidate()
        if (now - start < 4000) { requestAnimationFrame(tick); return }
        times.shift(); times.sort((a, b) => a - b)
        const avg = times.reduce((a, b) => a + b, 0) / times.length
        done(`${(1000 / avg).toFixed(0)} fps average, 95th percentile frame ${times[Math.floor(times.length * 0.95)].toFixed(1)} ms, ${times.length} frames, ${this.model.plan.walls.length} walls, ${this.renderer.info.render.triangles} triangles, ${ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown GPU'}`)
      }
      requestAnimationFrame(tick)
    })
  }

  dispose() {
    cancelAnimationFrame(this.raf); this.unsub(); this.ro.disconnect(); this.listeners.abort()
    this.doll.dispose(); this.pano.dispose(); this.splat.dispose()
    this.renderer.dispose(); this.renderer.domElement.remove(); this.labels.root.remove()
  }
}
