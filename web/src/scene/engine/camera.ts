// Camera arithmetic with no three.js and no DOM, so it runs under `node --test`: the free rectangle of view.frame,
// and compass bearings against the rig's azimuth (the angle of the camera's position around its target, scan frame).
import type { View } from '../types.ts'

const RAD = Math.PI / 180

/** The free rectangle: its size, and how far its centre is from the canvas centre (CSS px, y down). */
export function freeRect(w: number, h: number, frame: View['frame']) {
  const f = frame ?? {}, l = f.left ?? 0, r = f.right ?? 0, t = f.top ?? 0, b = f.bottom ?? 0
  return { w: Math.max(40, w - l - r), h: Math.max(40, h - t - b), dx: (l - r) / 2, dy: (t - b) / 2 }
}
/** The rig azimuth at which the camera looks toward a compass bearing. `yaw` is the scan frame's rotation to east/north, degrees. */
export const azOfBearing = (bearing: number, yaw: number) => (90 - bearing - yaw) * RAD - Math.PI
/** The compass bearing (0..360, 0 north, clockwise) the camera looks toward at a rig azimuth. */
export const bearingOfAz = (az: number, yaw: number) => (((90 - (az + Math.PI) / RAD - yaw) % 360) + 360) % 360
/** Contract 3's panorama direction (yaw counter-clockwise from +x, pitch up) as the rig's azimuth and polar angle. */
export const lookAngles = (l: { yaw_deg: number; pitch_deg: number }) => ({ az: l.yaw_deg * RAD + Math.PI, pol: Math.PI / 2 + l.pitch_deg * RAD })
