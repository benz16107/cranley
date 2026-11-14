// The choices that are not a mode: what the building is drawn from, what stands around it, and how it is drawn.
// The scene mounts it over the picture; a look may mount it in its own toolbar instead (<BuildingScene switcher={false}>).
// It only edits the View, so it works wherever the view lives.
import type { ScanPlan, View } from './types.ts'

export interface ViewSwitcherProps {
  plan: Pick<ScanPlan, 'geo' | 'panos' | 'walls' | 'has'>
  view: View
  onChange: (v: View) => void
  className?: string
}

export function ViewSwitcher({ plan, view, onChange, className }: ViewSwitcherProps) {
  const outside = view.mode === 'dollhouse' || view.mode === 'splat', doll = view.mode === 'dollhouse'
  if (!outside) return null
  const placed = !!(plan.geo as { lat?: number } | null | undefined)?.lat
  const seg = <T extends string>(label: string, value: T, options: [T, string, string?][], set: (v: T) => void, off?: string) => (
    <div className="th-seg" role="group" aria-label={label} title={off}>
      <span className="th-seg-label">{label}</span>
      {options.map(([id, name, tip]) => <button key={id} aria-pressed={value === id} disabled={!!off && id !== options[0][0]} title={tip} onClick={() => set(id)}>{name}</button>)}
    </div>
  )
  return (
    <div className={`th-views ${className ?? ''}`} data-scene-ui>
      {doll && seg('Building', view.surface ?? 'model', [['model', 'Measured', 'Walls, doors and windows as measured in the plan'], ['scan', 'Scanned', "Matterport's scanned mesh, coloured from the panoramas"]], (surface) => onChange({ ...view, surface, showcase: false }))}
      {seg('Around it', view.env ?? 'studio', [['studio', 'Nothing'], ['aerial', 'Real site', 'The real surroundings, from the aerial survey']], (env) => onChange({ ...view, env, showcase: false }), placed ? undefined : 'This scan has no position, so it cannot be placed on its site')}
      {(view.surface ?? 'model') === 'model' && plan.walls.length > 0 && (
        <button className="th-toggle" aria-pressed={view.style === 'xray'} title={doll ? 'Walls as glass, so results read through them' : 'Show the measured model inside the drone capture'}
          onClick={() => onChange({ ...view, style: view.style === 'xray' ? 'solid' : 'xray' })}>X-ray</button>
      )}
      {doll && plan.panos.length > 0 && <button className="th-toggle" title="Fly in from above and land in a room" onClick={() => onChange({ ...view, showcase: false, tour: (view.tour ?? 0) + 1 })}>Fly in</button>}
      {doll && <button className="th-toggle" aria-pressed={!!view.showcase} title="Matterport's own dollhouse, floor plan and walk" onClick={() => onChange({ ...view, showcase: !view.showcase })}>Matterport</button>}
    </div>
  )
}
