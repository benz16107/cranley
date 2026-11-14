/* Where a value came from, said the way a person would say it. Pure, so it runs under `node --test`. */

const FROM: Record<string, string> = { matterport: 'the scan', vexcel: 'aerial photos', costar: 'the property record', drone: 'the drone capture', model: 'a model', phone: 'your phone' }

/** "Measured from the scan", "Seen in aerial photos", "From the property record". The layer and the method are the
    result's own; only the wording is ours. An unknown layer or method is named as it came. */
export function sourceWords(s: { layer: string; method: string }): string {
  const from = FROM[s.layer] ?? s.layer
  switch (s.method) {
    case 'geometry': return `Measured from ${from}`
    case 'vision': return s.layer === 'matterport' ? 'Seen in the scan’s photos' : s.layer === 'phone' ? 'Seen in your phone’s photo' : s.layer === 'model' ? 'Read from photos by a model' : `Seen in ${from}`
    case 'lookup': return s.layer === 'costar' ? 'From the property record' : `Looked up in ${from}`
    case 'simulation': return s.layer === 'model' ? 'Simulated' : `Simulated from ${from}`
    case 'sensor': return s.layer === 'phone' ? 'Read on site by your phone' : `Read by a sensor, ${from}`
    case 'manual': return 'Measured on site by hand'
    default: return `From ${from}, ${s.method}`
  }
}

/** Do these values all come from one place, in one way, with one confidence? Then the place is said once. */
export const oneSource = (all: { layer: string; method: string; confidence: string; note?: string }[]) =>
  all.length > 0 && all.every((s) => s.layer === all[0].layer && s.method === all[0].method && s.confidence === all[0].confidence && (s.note ?? '') === (all[0].note ?? ''))

/** A list of checks, split for showing: the ones that need the person's attention (failed, or a caution) stay in
    view; the ones that passed or could not be measured go behind a fold, with a line that says what is in it. A short
    list with nothing to attend to is shown whole. */
export function splitChecks<C extends { status: string }>(checks: C[]): { shown: C[]; folded: C[]; summary: string } {
  const needs = checks.filter((c) => c.status === 'fail' || c.status === 'warn'), rest = checks.filter((c) => c.status !== 'fail' && c.status !== 'warn')
  if (!rest.length || (!needs.length && rest.length <= 4)) return { shown: checks, folded: [], summary: '' }
  const pass = rest.filter((c) => c.status === 'pass').length, unknown = rest.length - pass
  const parts = [pass ? `${pass} passed` : '', unknown ? `${unknown} not measured` : ''].filter(Boolean).join(', ')
  return { shown: needs, folded: rest, summary: needs.length ? `${rest.length} more ${rest.length === 1 ? 'check' : 'checks'}: ${parts}` : `${rest.length} checks: ${parts}` }
}
