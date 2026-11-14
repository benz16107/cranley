// One camera for every view. A pose is an orbit around a target; a panorama is the same orbit with distance ~0.
import * as THREE from 'three'

export interface Pose { target: THREE.Vector3; az: number; pol: number; dist: number; fov: number }

/** cubic-bezier(x1, y1, x2, y2) as a function of time 0..1 */
export function bezier(x1: number, y1: number, x2: number, y2: number) {
  const f = (a: number, b: number, t: number) => 3 * a * (1 - t) * (1 - t) * t + 3 * b * (1 - t) * t * t + t * t * t
  return (x: number) => {
    let lo = 0, hi = 1
    for (let i = 0; i < 24; i++) { const mid = (lo + hi) / 2; if (f(x1, x2, mid) < x) lo = mid; else hi = mid }
    return f(y1, y2, (lo + hi) / 2)
  }
}
export const easeInOut = bezier(0.77, 0, 0.175, 1) // on-screen movement
export const easeOut = bezier(0.23, 1, 0.32, 1)    // things arriving

const wrap = (a: number) => a - Math.round(a / (2 * Math.PI)) * 2 * Math.PI
export const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

export class Rig {
  camera = new THREE.PerspectiveCamera(32, 1, 0.05, 2000)
  pose: Pose = { target: new THREE.Vector3(), az: -2.1, pol: 0.9, dist: 30, fov: 32 }
  goal: Pose = { ...this.pose, target: new THREE.Vector3() }
  limits = { minPol: 0.02, maxPol: 1.52, minDist: 1, maxDist: 400, minFov: 28, maxFov: 100 }
  private tween: { from: Pose; to: Pose; t: number; dur: number } | null = null
  private spin = { az: 0, pol: 0 } // angular velocity kept after a drag is released

  /** Designed move to a pose. Starts from wherever the camera is now, so it can be interrupted by another move. */
  flyTo(to: Partial<Pose>, ms = 1000) {
    const from = { ...this.pose, target: this.pose.target.clone() }
    const full: Pose = { ...this.goal, ...to, target: (to.target ?? this.goal.target).clone() }
    full.az = from.az + wrap(full.az - from.az)
    this.goal = { ...full, target: full.target.clone() }
    this.spin.az = this.spin.pol = 0
    if (reducedMotion() || ms <= 0) { this.pose = full; this.tween = null; this.apply(); return }
    this.tween = { from, to: full, t: 0, dur: ms / 1000 }
  }

  /** Direct manipulation: the goal changes and the camera follows it within a few frames. */
  nudge(fn: (g: Pose) => void, throwSpin?: { az: number; pol: number }) {
    if (this.tween) { this.goal = { ...this.pose, target: this.pose.target.clone() }; this.tween = null }
    fn(this.goal)
    const l = this.limits
    this.goal.pol = Math.min(l.maxPol, Math.max(l.minPol, this.goal.pol))
    this.goal.dist = Math.min(l.maxDist, Math.max(l.minDist, this.goal.dist))
    this.goal.fov = Math.min(l.maxFov, Math.max(l.minFov, this.goal.fov))
    this.spin = throwSpin ?? { az: 0, pol: 0 }
  }

  get moving() { return !!this.tween }

  /** Advance. Returns true while the camera is still moving. */
  update(dt: number): boolean {
    const p = this.pose
    if (this.tween) {
      const tw = this.tween
      tw.t = Math.min(1, tw.t + dt / tw.dur)
      const k = easeInOut(tw.t), { from, to } = tw
      p.target.lerpVectors(from.target, to.target, k)
      p.az = from.az + (to.az - from.az) * k
      p.pol = from.pol + (to.pol - from.pol) * k
      p.dist = Math.exp(Math.log(from.dist) + (Math.log(to.dist) - Math.log(from.dist)) * k) // zoom is felt in ratios
      p.fov = from.fov + (to.fov - from.fov) * k
      if (tw.t >= 1) this.tween = null
      this.apply()
      return true
    }
    const g = this.goal, l = this.limits
    if (Math.abs(this.spin.az) + Math.abs(this.spin.pol) > 1e-4) {
      g.az += this.spin.az * dt
      g.pol = Math.min(l.maxPol, Math.max(l.minPol, g.pol + this.spin.pol * dt))
      const decay = Math.exp(-dt * 4.5)
      this.spin.az *= decay; this.spin.pol *= decay
    }
    const k = 1 - Math.exp(-dt * 16)
    const err = p.target.distanceTo(g.target) / Math.max(g.dist, 0.5) + Math.abs(g.az - p.az) + Math.abs(g.pol - p.pol) + Math.abs(Math.log(g.dist / p.dist)) + Math.abs(g.fov - p.fov) * 0.01
    if (err < 1e-4) return false
    p.target.lerp(g.target, k)
    p.az += (g.az - p.az) * k; p.pol += (g.pol - p.pol) * k; p.fov += (g.fov - p.fov) * k
    p.dist = Math.exp(Math.log(p.dist) + Math.log(g.dist / p.dist) * k)
    this.apply()
    return true
  }

  apply() {
    const { target, az, pol, dist, fov } = this.pose, c = this.camera
    const sp = Math.sin(pol), cp = Math.cos(pol)
    c.position.set(target.x + dist * sp * Math.cos(az), target.y + dist * sp * Math.sin(az), target.z + dist * cp)
    c.up.set(-cp * Math.cos(az), -cp * Math.sin(az), sp) // stays valid looking straight down
    c.lookAt(target)
    c.fov = fov
    c.near = Math.max(0.03, dist * 0.02)
    c.far = dist * 12 + 600
    c.updateProjectionMatrix()
    c.updateMatrixWorld()
  }

  /** Pixels per metre on a plane through the target, facing the camera. */
  pxPerMetre(viewH: number, depth = this.pose.dist) { return viewH / 2 / (Math.max(depth, 1e-3) * Math.tan((this.pose.fov * Math.PI) / 360)) }
}
