import type { Field } from './tools.ts'

/* What a person typed into the form that starts a tool, checked and turned into the tool's inputs. Pure, so it runs
   under `node --test`. */
const CRITERION = /^([\w.]+)\s*(>=|<=|==|!=|>|<)\s*(.+)$/

/** What is wrong with a field as typed, or null. */
export function problem(f: Field, v: string | boolean | undefined): string | null {
  if (f.kind === 'toggle') return null
  const s = String(v ?? '').trim()
  if (!s) return f.required ? 'Needed to run' : null
  if (f.kind === 'number' || f.kind === 'reading') {
    const n = Number(s)
    if (!Number.isFinite(n) || (f.whole && !Number.isInteger(n))) return f.whole ? 'A whole number' : 'A number'
    if (f.min != null && n < f.min) return `At least ${f.min}`
    if (f.max != null && n > f.max) return `At most ${f.max}`
  }
  if (f.kind === 'point' && !/^-?\d+(\.\d+)?[,\s]+-?\d+(\.\d+)?$/.test(s)) return 'Latitude, then longitude: 29.7604, -95.3698'
  if (f.kind === 'criteria' && s.split('\n').some((l) => l.trim() && !CRITERION.test(l.trim()))) return 'One per line, as: floors == 1'
  return null
}
/** A field's value as the tool takes it; undefined leaves the input to the tool's default. */
export function encode(f: Field, v: string | boolean | undefined): unknown {
  if (f.kind === 'toggle') return v === (f.fallback ?? false) ? undefined : v
  const s = String(v ?? '').trim()
  if (!s || s === String(f.fallback ?? '')) return undefined
  if (f.kind === 'number') return Number(s)
  if (f.kind === 'reading') return [{ leq_dba: Number(s), seconds: 30 }] // one level typed in; the phone app sends one per room
  if (f.kind === 'point') { const [lat, lon] = s.split(/[,\s]+/).map(Number); return [lon, lat] }
  if (f.kind === 'criteria') return s.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => { const [, measure, op, value] = l.match(CRITERION)!; return { measure, op, value: Number.isFinite(Number(value)) ? Number(value) : value } })
  return s
}
