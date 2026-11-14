/* The arithmetic behind the phone's instruments. Pure, so it runs under `node --test`: no DOM, no sensors. */

const DEG = 180 / Math.PI
export type Vec = { x: number; y: number; z: number }

/** Tilt of the phone from the gravity vector the motion sensor reports, in degrees. `long` is the tilt of the
    phone's long axis (top edge up is one sign, bottom edge up the other), `short` of its short axis. iOS and Android
    report gravity with opposite signs, so a sign here means nothing between phones; a slope is read from the size,
    or from two readings on the same phone turned end for end. */
export function tilt(g: Vec): { long: number; short: number } {
  const n = Math.hypot(g.x, g.y, g.z) || 1
  const c = (v: number) => Math.asin(Math.max(-1, Math.min(1, v / n))) * DEG
  return { long: c(g.y), short: c(g.x) }
}

export const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0)
export function spread(xs: number[]): number {
  if (xs.length < 2) return 0
  const m = mean(xs)
  return Math.sqrt(mean(xs.map((x) => (x - m) ** 2)))
}

/** The mean of compass headings, which wrap at 360 (350 and 10 average to 0, not 180), and how far they scatter. */
export function headingMean(degs: number[]): { mean: number; spread: number } {
  if (!degs.length) return { mean: 0, spread: 180 }
  const s = mean(degs.map((d) => Math.sin(d / DEG))), c = mean(degs.map((d) => Math.cos(d / DEG)))
  const r = Math.min(1, Math.hypot(s, c))
  return { mean: (Math.atan2(s, c) * DEG + 360) % 360, spread: Math.sqrt(-2 * Math.log(Math.max(r, 1e-9))) * DEG }
}
/** Android gives `alpha`, counter-clockwise from north; a compass heading runs clockwise. */
export const headingFromAlpha = (alpha: number) => (360 - alpha + 360) % 360
const POINTS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
export const compassPoint = (deg: number) => POINTS[Math.floor(((deg % 360) + 11.25) / 22.5) % 16]

/** A-weighting in dB at a frequency (IEC 61672-1), 0 dB at 1 kHz. */
export function aWeight(f: number): number {
  const f2 = f * f
  const ra = (12194 ** 2 * f2 * f2) / ((f2 + 20.6 ** 2) * Math.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * (f2 + 12194 ** 2))
  return 20 * Math.log10(ra) + 2.0
}
/** The same curve as three second-order filters, for the browser's BiquadFilterNode: the double pole at 20.6 Hz, the
    poles at 107.7 and 737.9 Hz, the double pole at 12194 Hz. Web Audio takes Q for these filter types in dB. */
export const A_STAGES = [
  { type: 'highpass' as const, frequency: 20.6, q: 0.5 },
  { type: 'highpass' as const, frequency: Math.sqrt(107.7 * 737.9), q: Math.sqrt(107.7 * 737.9) / (107.7 + 737.9) },
  { type: 'lowpass' as const, frequency: 12194, q: 0.5 },
].map((s) => ({ ...s, qDb: 20 * Math.log10(s.q) }))
export const A_GAIN_DB = 2.0

/* The microphone's samples run from -1 to 1 and nothing says what sound pressure "1" is on a given phone.
   120 dB is where a typical digital MEMS microphone clips; the server states the error this leaves (about 10 dB). */
export const FULL_SCALE_DB = 120
/** Equivalent level from mean squares of A-weighted samples, one per window. */
export const leq = (meanSquares: number[]) => 10 * Math.log10(Math.max(mean(meanSquares), 1e-12)) + FULL_SCALE_DB
export const level = (meanSquare: number) => 10 * Math.log10(Math.max(meanSquare, 1e-12)) + FULL_SCALE_DB

/** One fix from several: those within twice the best accuracy, averaged. */
export type Fix = { lat: number; lon: number; accuracy_m: number | null; altitude_m: number | null; altitude_accuracy_m: number | null; samples: number }
export function bestFix(fixes: Omit<Fix, 'samples'>[]): Fix | null {
  if (!fixes.length) return null
  const best = Math.min(...fixes.map((f) => f.accuracy_m ?? 1e9))
  const good = fixes.filter((f) => (f.accuracy_m ?? 1e9) <= best * 2)
  const alt = good.filter((f) => f.altitude_m != null)
  const accs = alt.map((f) => f.altitude_accuracy_m).filter((a): a is number => a != null)
  return { lat: mean(good.map((f) => f.lat)), lon: mean(good.map((f) => f.lon)), accuracy_m: best < 1e9 ? best : null,
    altitude_m: alt.length ? mean(alt.map((f) => f.altitude_m!)) : null, altitude_accuracy_m: accs.length ? Math.min(...accs) : null, samples: good.length }
}

/** A length typed in centimetres or inches, as metres. Null for anything that is not a positive number. */
export function toMetres(text: string, unit: 'cm' | 'in'): number | null {
  const v = Number(text.replace(',', '.'))
  return Number.isFinite(v) && v > 0 ? +(v * (unit === 'cm' ? 0.01 : 0.0254)).toFixed(4) : null
}
export const fmtLength = (m: number, unit: 'cm' | 'in') => (unit === 'cm' ? `${+(m * 100).toFixed(1)} cm` : `${+(m / 0.0254).toFixed(2)} in`) // as typed: 0.25 in is a step limit
