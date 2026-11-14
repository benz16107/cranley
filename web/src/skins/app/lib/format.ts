/* Display formatting only. Nothing here changes a value a tool produced. */
export const num = (v: number | null | undefined, digits?: number) =>
  v == null ? '–' : new Intl.NumberFormat('en', { maximumFractionDigits: digits ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2) }).format(v)
export const int = (v: number) => new Intl.NumberFormat('en').format(v)
export const dur = (ms: number | null | undefined) => (ms == null ? '' : ms < 1000 ? `${Math.round(ms)} ms` : ms < 60_000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`)
export const plural = (n: number, one: string, many = one + 's') => `${int(n)} ${n === 1 ? one : many}`
const rel = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
export function ago(ts: number, now = Date.now()) {
  const s = Math.round((ts - now) / 1000), a = Math.abs(s)
  return a < 45 ? 'just now' : a < 3600 ? rel.format(Math.round(s / 60), 'minute') : a < 86_400 ? rel.format(Math.round(s / 3600), 'hour') : rel.format(Math.round(s / 86_400), 'day')
}
export const clock = (ts: number) => new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(ts)
