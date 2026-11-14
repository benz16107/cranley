// The hand-off between the map and the building scene. Both draw the same city mesh with the same lens (32° tall);
// this file says where the scene's camera is in the map's terms and back, so the two pictures can be made to agree
// at the moment one replaces the other. No three.js here: plain numbers, tested under `node --test`.
import { buildModel } from '../scene/model.ts'
import type { ScanPlan, Vec2 } from '../scene/types.ts'

/** The scene's lens: both cameras must use it (Engine.ts DOLL_FOV). */
export const FOV = 32
const RAD = Math.PI / 180
const TAN = Math.tan((FOV / 2) * RAD)
/** What the server says about standing a scan in the world (`/api/world/<sid>/site`). */
export interface Site {
  available: boolean
  anchor: { lat: number; lon: number }
  scan_to_enu: { rot_deg: number; t: [number, number]; verified: boolean }
  floor_above_ground_m: number
}
/** A camera as the scene's `pose` and `onCamera` give it: compass bearing it looks toward, degrees from straight
    down, metres from its target. */
export interface Pose { bearing: number; pitch: number; range: number }
/** A scan's place in the world, worked out once: its anchor, where the scene's camera target is, and the ranges at
    which the hand-off happens. East/north metres are about the anchor; `up` is above the ground beside the building. */
export interface Stand {
  anchor: { lat: number; lon: number }
  target: { e: number; n: number; up: number }
  /** Where the ground is sampled round the building, as the scene samples it. */
  ring: [number, number][]
  /** The range at which the scene frames the whole building. */
  fit: number
  /** The hand-off range: far enough that the scene still draws the building whole, as the map does. */
  enter: number
  /** Zooming the scene out past this returns to the map. */
  leave: number
  verified: boolean
}

/** The scene's own numbers for a plan (Engine.ts: centre(), radius(), dollPose()), in the world. */
export function stand(plan: ScanPlan, site: Site, view: { w: number; h: number }): Stand {
  const m = buildModel(plan), b = m.bounds
  const cx = (b.minX + b.maxX) / 2, cy = (b.minY + b.maxY) / 2
  // floors stand at their own scan z, and the ground outside is just under the lowest floor that is not a basement
  const base = m.floorZ[0], tall = m.floorZ[m.floorZ.length - 1] + m.maxH - base, ground = m.floorZ[m.groundFloor] - site.floor_above_ground_m
  const radius = Math.max(4, Math.hypot(b.maxX - b.minX, b.maxY - b.minY) / 2)
  const { rot_deg, t } = site.scan_to_enu, c = Math.cos(rot_deg * RAD), s = Math.sin(rot_deg * RAD)
  const enu = (x: number, y: number): Vec2 => [c * x - s * y + t[0], s * x + c * y + t[1]]
  const [e, n] = enu(cx, cy), r = radius + 3
  const fitAngle = Math.min(Math.atan(TAN), Math.atan(TAN * (view.w / view.h)))
  const fit = ((radius + tall * 0.25) / Math.sin(fitAngle)) * 0.86
  // the scene opens the building inside 2.1 fits (with 12% of slack): the hand-off stays outside that
  const enter = Math.min(500, Math.max(110, fit * 2.1 * 1.25))
  return {
    anchor: site.anchor, target: { e, n, up: base + tall * 0.3 - ground },
    ring: Array.from({ length: 16 }, (_, i) => enu(cx + Math.cos((i / 16) * 2 * Math.PI) * r, cy + Math.sin((i / 16) * 2 * Math.PI) * r)),
    fit, enter, leave: Math.min(545, Math.max(enter * 1.3, 400)), verified: site.scan_to_enu.verified,
  }
}

const WGS_A = 6378137, WGS_E2 = 6.69437999014e-3
/** Metres on the ground per radian of longitude and of mercator y at a latitude, on the WGS84 ellipsoid. Web
    Mercator's own sphere is 0.4% off north to south here, which is 1.4 m at the edge of a patch of city mesh. */
export function groundScale(lat: number): { east: number; north: number } {
  const sl = Math.sin(lat * RAD), cl = Math.cos(lat * RAD), w = 1 - WGS_E2 * sl * sl
  return { east: (WGS_A / Math.sqrt(w)) * cl, north: ((WGS_A * (1 - WGS_E2)) / w ** 1.5) * cl }
}
/** A point east/north of an anchor as longitude and latitude. Linear in Web Mercator about the anchor, which is how
    CityMesh draws its tiles, so a camera placed by this sees them where they are drawn. */
export function lngLatOf(anchor: { lat: number; lon: number }, e: number, n: number): [number, number] {
  const g = groundScale(anchor.lat)
  const y = Math.log(Math.tan(Math.PI / 4 + (anchor.lat * RAD) / 2)) + n / g.north
  return [anchor.lon + e / g.east / RAD, (2 * Math.atan(Math.exp(y)) - Math.PI / 2) / RAD]
}

/** Where the camera itself is for a pose about a stand's target: longitude, latitude and metres above the ground. */
export function cameraOf(st: Stand, p: Pose): { lngLat: [number, number]; altitude: number; bearing: number; pitch: number } {
  const sp = Math.sin(p.pitch * RAD), back = p.range * sp
  const e = st.target.e - back * Math.sin(p.bearing * RAD), n = st.target.n - back * Math.cos(p.bearing * RAD)
  return { lngLat: lngLatOf(st.anchor, e, n), altitude: st.target.up + p.range * Math.cos(p.pitch * RAD), bearing: p.bearing, pitch: p.pitch }
}

/** The range that shows the same ground as a map zoom (512 px tiles) on a canvas `h` px tall, and back. */
export const rangeOfZoom = (zoom: number, lat: number, h: number) => ((h / 2 / TAN) * 78271.51696 * Math.cos(lat * RAD)) / 2 ** zoom
export const zoomOfRange = (range: number, lat: number, h: number) => Math.log2(((h / 2 / TAN) * 78271.51696 * Math.cos(lat * RAD)) / range)
