import { panoFace, type Anchor, type Finding, type Pt, type ScanPlan, type Status } from '../../core/index.ts'

/* Plain helpers of this look: words, number formatting, and where things are on a plan. No components here. */

export const STATUS_WORD: Record<Status, string> = { pass: 'Pass', warn: 'Caution', fail: 'Fail', unknown: 'Not measured' }

/** A number as it was given, with only as many digits as its size needs. Nothing is recomputed. */
export const fmt = (v: number | null | undefined, digits?: number) =>
  v == null ? 'not measured' : new Intl.NumberFormat('en', { maximumFractionDigits: digits ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2) }).format(v)
export const ms = (t: number) => (t < 1000 ? `${Math.round(t)} ms` : `${(t / 1000).toFixed(1)} s`)
export const street = (address: string | null | undefined) => (address ?? '').split(',')[0]
export const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

const mid = (ps: Pt[]): Pt => [ps.reduce((s, p) => s + p[0], 0) / ps.length, ps.reduce((s, p) => s + p[1], 0) / ps.length]

/** Where an anchor is on the plan, in metres, or null (a map anchor, another scan, an id the plan lacks). */
export function anchorPoint(plan: ScanPlan, a: Anchor | null | undefined): Pt | null {
  if (!a || !('sid' in a) || a.sid !== plan.sid) return null
  if ('point' in a) return [a.point[0], a.point[1]]
  if ('opening' in a) return plan.openings.find((o) => o.id === a.opening)?.center ?? null
  if ('room' in a) { const r = plan.rooms.find((x) => x.id === a.room); return r?.polygon.length ? mid(r.polygon) : null }
  if ('wall' in a) { const w = plan.walls.find((x) => x.id === a.wall); return w ? mid([w.a, w.b]) : null }
  const p = plan.panos.find((x) => x.id === a.pano)
  return p ? [p.position[0], p.position[1]] : null
}

/** A finding's photograph. Contract 3: a panorama ref is "<sid>/<pano>/<face>"; the fixtures give the position alone. */
export function findingPhoto(f: Finding): string | null {
  const m = f.media?.find((x) => x.kind === 'pano'), sid = f.anchor && 'sid' in f.anchor ? f.anchor.sid : null
  const [a, b, c] = m?.ref.split('/') ?? []
  return m && b ? panoFace(a, b, c ? Number(c) : 1) : m && sid ? panoFace(sid, m.ref) : null
}
