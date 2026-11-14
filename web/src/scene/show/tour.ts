// A camera tour of findings: down from above the street, then to each piece of evidence in turn, holding on it
// while its one line is read aloud and shown as a caption. The stops and their lines come from the `tour` tool; the
// player writes no words of its own.
import * as THREE from 'three'
import { anchorPoint } from '../model.ts'
import { h, type LabelSpec } from '../engine/labels.ts'
import type { Vec3 } from '../types.ts'
import type { Player, ShowCtx, ShowSpec, TourStop } from './types.ts'

const SETTLE_S = 0.2    // a mode or floor change reaches the engine through the look; wait for it before flying
const HOLD_MIN_S = 2.6
const speech = () => (typeof speechSynthesis === 'undefined' ? null : speechSynthesis)
/** How long a line takes to read: the fallback when the browser never says the speech ended. */
const readTime = (line: string) => Math.max(HOLD_MIN_S, line.split(/\s+/).length * 0.33 + 1.2)

export class TourShow implements Player {
  group = null
  labels: LabelSpec[] = []
  private stops: TourStop[] = []
  private i = -1; private phase: 'idle' | 'settle' | 'fly' | 'say' = 'idle'; private t = 0
  private playing = false; private seekN = -1; private voice = true
  private spoken = false; private said = false; private heard = false // asked to speak; finished speaking; the browser did start speaking
  private key = ''

  private ctx: ShowCtx
  constructor(ctx: ShowCtx) { this.ctx = ctx }

  set(spec: ShowSpec) {
    const stops = spec.stops ?? [], key = stops.map((s) => s.id).join('|')
    this.voice = spec.voice ?? true
    if (key !== this.key) { this.key = key; this.stops = stops; this.i = -1; this.phase = 'idle'; this.hush() }
    if (spec.seek && spec.seek.n !== this.seekN) { this.seekN = spec.seek.n; if (stops.length) this.go(Math.min(Math.max(spec.seek.step, 0), stops.length - 1)) }
    if (spec.playing !== this.playing) {
      this.playing = spec.playing
      if (this.playing && stops.length && (this.i < 0 || (this.i >= stops.length - 1 && this.phase === 'idle'))) this.open()
      else if (this.playing) speech()?.resume(); else speech()?.pause()
    }
    this.report()
  }

  /** The establishing shot: up over the building before the first stop. */
  private open() {
    const p = this.ctx.home(), rig = this.ctx.rig
    this.ctx.setView({ mode: 'dollhouse', floor: null })
    rig.flyTo({ target: p.target, az: p.az + 0.7, pol: 0.6, dist: this.ctx.aerial() ? 240 : p.dist * 2.2, fov: p.fov }, 900)
    this.go(0)
  }

  private go(i: number) {
    this.hush()
    this.i = i; this.phase = 'settle'; this.t = 0; this.spoken = false; this.said = false; this.heard = false
    const s = this.stops[i], m = this.ctx.model, a = s.anchor
    if (a && 'pano' in a) this.ctx.setView({ mode: 'pano', pano: a.pano, look: { yaw_deg: a.yaw_deg, pitch_deg: a.pitch_deg } })
    else {
      const at = a ? anchorPoint(m, a) : null
      this.ctx.setView({ mode: 'dollhouse', floor: at && m.plan.floors.length > 1 ? m.plan.floors[at.floor].id : null })
    }
    this.mark(); this.report()
  }

  /** A chip on the evidence itself, so the eye lands where the line points. */
  private mark() {
    const s = this.stops[this.i], m = this.ctx.model, a = s?.anchor
    let pos: Vec3 | null = null, floor = 0
    if (a && 'pano' in a) {
      const p = m.plan.panos.find((q) => q.id === a.pano), yaw = (a.yaw_deg * Math.PI) / 180, pitch = (a.pitch_deg * Math.PI) / 180
      if (p) { pos = [p.position[0] + 2.2 * Math.cos(pitch) * Math.cos(yaw), p.position[1] + 2.2 * Math.cos(pitch) * Math.sin(yaw), p.position[2] + 2.2 * Math.sin(pitch)]; floor = m.floorOf.get(p.floor ?? '') ?? 0 }
    } else if (a) { const at = anchorPoint(m, a); if (at) { pos = at.point; floor = at.floor } }
    this.labels = pos ? [{ id: `tour.${s.id}`, pos, floor, make: () => { const el = h('div', 'th-chip th-chip-tour', h('span', 'th-chip-text', s.title)); el.dataset.status = s.status; return el } }] : []
    this.ctx.relabel()
  }

  private fly() {
    const s = this.stops[this.i], m = this.ctx.model, rig = this.ctx.rig, a = s.anchor
    if (a && 'pano' in a) return // the engine walks to the position and turns to the direction itself
    const at = a ? anchorPoint(m, a) : null
    if (!at) { const p = this.ctx.home(); rig.flyTo({ ...p, az: rig.pose.az + 0.5 }, 2600); return }
    const room = a && 'room' in a ? m.plan.rooms.find((r) => r.id === a.room) : null
    const dist = room ? Math.min(15, Math.max(9, Math.sqrt(room.area ?? 12) * 2.8)) : 8.5 // near enough to read a doorway, far enough that the room round it reads too
    const lift = this.ctx.doll.floorZ(at.floor) - m.floorZ[at.floor]
    rig.flyTo({ target: new THREE.Vector3(at.point[0], at.point[1], at.point[2] + lift), az: rig.pose.az + 0.55, pol: 0.74, dist, fov: this.ctx.home().fov }, this.i === 0 ? 3400 : 2300)
  }

  private say() {
    const s = this.stops[this.i], sp = speech()
    this.spoken = true; this.said = !this.voice || !sp
    if (this.voice && sp) {
      const u = new SpeechSynthesisUtterance(s.line)
      u.rate = 1.02; u.onstart = () => { this.heard = true }; u.onend = u.onerror = () => { this.said = true }
      sp.cancel(); sp.speak(u)
    }
    this.report()
  }
  private hush() { speech()?.cancel() }

  private report() {
    const s = this.stops[Math.max(this.i, 0)], n = this.stops.length
    this.ctx.emit({
      kind: 'tour', status: n ? 'ready' : 'missing', reason: n ? undefined : 'No tour for this scan yet. Run the Tour tool after other tools have findings here.',
      playing: this.playing, step: Math.max(this.i, 0), steps: Math.max(n - 1, 0), clock: n ? `${Math.max(this.i, 0) + 1} of ${n}` : '', title: 'Tour of the findings', sources: [],
      tour: s ? { i: Math.max(this.i, 0), n, title: s.title, line: s.line, status: s.status, speaking: this.phase === 'say' } : undefined,
    })
  }

  update(dt: number): boolean {
    if (!this.playing || this.i < 0 || this.phase === 'idle') return false
    const rig = this.ctx.rig, s = this.stops[this.i]
    this.t += dt
    if (this.phase === 'settle' && this.t > SETTLE_S) { this.fly(); this.phase = 'fly'; this.t = 0 }
    else if (this.phase === 'fly') {
      // the line starts as the camera closes in, not after it has stopped: it reads as one move
      if (this.t > 0.7 && !this.spoken) this.say()
      if (!rig.moving && this.t > 1.2) { this.phase = 'say'; this.t = 0; if (!this.spoken) this.say() }
    } else if (this.phase === 'say') {
      if (this.ctx.view().mode === 'dollhouse' && !rig.moving) rig.goal.az += dt * 0.035 // a slow drift keeps the picture alive
      const long = readTime(s.line)
      // on to the next stop when the line has been said; a browser with no voice never starts, and gets reading time
      if ((this.said && this.t > HOLD_MIN_S) || (!this.heard && this.t > long) || this.t > long * 2) {
        if (this.i + 1 < this.stops.length) this.go(this.i + 1)
        else { this.phase = 'idle'; this.playing = false; this.labels = []; this.ctx.relabel(); this.ctx.setView({ mode: 'dollhouse', floor: null }); rig.flyTo({ ...this.ctx.home(), az: rig.pose.az + 0.4 }, 2200); this.report() }
      }
    }
    return true
  }

  touched() { if (this.playing) { this.playing = false; speech()?.pause(); this.report() } }

  dispose() { this.hush(); this.labels = [] }
}
