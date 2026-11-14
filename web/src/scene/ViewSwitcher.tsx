// The choices that are not a mode: what the building is drawn from, what stands around it, and how it is drawn.
// The scene mounts it over the picture; a look may mount its own controls instead (<BuildingScene switcher={false}>)
// and edit the same View fields.
import type { ScanPlan, View } from './types.ts'

export interface ViewSwitcherProps {
  plan: Pick<ScanPlan, 'geo' | 'panos' | 'walls' | 'has'>
  view: View
  onChange: (v: View) => void
  /** This scan has an interior splat, so "Splat" is offered. */
  interior?: boolean
  className?: string
}

export function ViewSwitcher({ plan, view, onChange, interior, className }: ViewSwitcherProps) {
  const outside = view.mode === 'dollhouse' || view.mode === 'splat', doll = view.mode === 'dollhouse'
  if (!outside) return null
  const placed = !!(plan.geo as { lat?: number } | null | undefined)?.lat
  const seg = <T extends string>(label: string, value: T, options: [T, string, string?][], set: (v: T) => void, off?: string) => (
    <div className="th-seg" role="group" aria-label={label} title={off}>
      <span className="th-seg-label">{label}</span>
      {options.map(([id, name, tip]) => <button key={id} aria-pressed={value === id} disabled={!!off && id !== options[0][0]} title={tip} onClick={() => set(id)}>{name}</button>)}
    </div>
  )
  const surface = view.surface === 'splat' && !interior ? 'scan' : view.surface ?? 'model'
  return (
    <div className={`th-views ${className ?? ''}`} data-scene-ui>
      {doll && seg<NonNullable<View['surface']>>('Building', surface, [['model', 'Measured', 'Walls, doors and windows as measured in the plan'], ['scan', 'Photoreal', 'The scanned rooms in photo colour, baked from the panoramas'],
        ...(interior ? [['splat', 'Splat', 'A Gaussian splat of the rooms, trained from the panoramas'] as ['splat', string, string]] : [])], (s) => onChange({ ...view, surface: s }))}
      {seg('Around it', view.env ?? 'studio', [['studio', 'Nothing'], ['aerial', 'Real site', 'The real surroundings: the drone capture where there is one, and the aerial survey']], (env) => onChange({ ...view, env }), placed ? undefined : 'This scan has no position, so it cannot be placed on its site')}
      {surface === 'model' && plan.walls.length > 0 && (
        <button className="th-toggle" aria-pressed={view.style === 'xray'} title={doll ? 'Walls as glass, so results read through them' : 'Show the measured model inside the drone capture'}
          onClick={() => onChange({ ...view, style: view.style === 'xray' ? 'solid' : 'xray' })}>X-ray</button>
      )}
      {doll && plan.panos.length > 0 && <button className="th-toggle" title="Fly in from above and land in a room" onClick={() => onChange({ ...view, tour: (view.tour ?? 0) + 1 })}>Fly in</button>}
    </div>
  )
}
