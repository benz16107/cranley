// Measured against the limit, on one line: where each doorway sits and where the user's limit is.
// Anything wider than the scale is pinned to its end with an arrow. Colours come from the direction (currentColor, --scale-ground).
import type { Check } from '../core/types.ts'
import { m2 } from './data.ts'

export function Scale({ doors, limit, lo = 0.3, hi = 1.1 }: { doors: Check[]; limit: number; lo?: number; hi?: number }) {
  const x = (v: number) => `${((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * 100}%`
  return (
    <div className="scale" role="img" aria-label={`Each doorway's width against your ${limit} m`}>
      <i className="scale-need" style={{ left: x(limit) }}><b>you need {limit}</b></i>
      {doors.map((c) => (
        <i key={c.id} className="scale-d" data-s={c.status} style={{ left: x(c.measured!) }}>
          <i className="glyph" data-s={c.status} /><b>{c.rule.replace(/^Narrowest doorway on the way to the /, '').replace(' door', '')} {m2(c.measured!)}{c.measured! > hi ? ' →' : ''}</b>
        </i>
      ))}
    </div>
  )
}
