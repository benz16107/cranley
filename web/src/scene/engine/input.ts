/** How the 3D view answers the pointer and the trackpad. Kept per browser; read on every event, so a change applies at once. */
export type Speed = 'slow' | 'normal' | 'fast'
export type Look = 'turn' | 'drag' // inside a panorama: turn the camera the way you swipe, or drag the photo along
export interface InputPrefs { zoom: Speed; look: Speed; lookDir: Look }

const KEY = 'threshold.input'
const DEFAULTS: InputPrefs = { zoom: 'normal', look: 'normal', lookDir: 'turn' }
export const SPEED: Record<Speed, number> = { slow: 0.6, normal: 1.4, fast: 2.4 }

function load(): InputPrefs {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') } } catch { return { ...DEFAULTS } }
}

export const inputPrefs: InputPrefs = load()

export function setInputPrefs(p: Partial<InputPrefs>) {
  Object.assign(inputPrefs, p)
  try { localStorage.setItem(KEY, JSON.stringify(inputPrefs)) } catch { /* kept for this page only */ }
}

/** A trackpad sends many small wheel events, often sideways too; a mouse wheel sends notches of 120. */
export function isTrackpad(e: WheelEvent): boolean {
  const w = (e as WheelEvent & { wheelDeltaY?: number }).wheelDeltaY
  if (e.deltaMode !== 0) return false
  if (e.deltaX !== 0) return true
  return w === undefined ? Math.abs(e.deltaY) < 40 : w % 120 !== 0
}
