import { useMemo } from 'react'
import { useCatalog, useToolCatalog } from '../../../core/index.ts'
import type { ICONS } from '../design/icons.ts'

/* Tool families, and the parts of a tool's manifest the catalogue shows.
   Stand-in: no field on a tool says its family, and CatalogTool does not carry what a tool needs (core-requests.md,
   App 5). This map names the 42 tools the server lists on 2026-11-14; a tool it does not know falls under "Other". */
export type Family = 'access' | 'flood' | 'fire' | 'office' | 'record' | 'site' | 'database' | 'other'
export const FAMILIES: { id: Family; label: string; icon: keyof typeof ICONS; hue: number }[] = [
  { id: 'access', label: 'Access', icon: 'wheelchair', hue: 1 },
  { id: 'flood', label: 'Flood', icon: 'drop', hue: 2 },
  { id: 'fire', label: 'Fire', icon: 'fire', hue: 3 },
  { id: 'office', label: 'Office and units', icon: 'office', hue: 4 },
  { id: 'record', label: 'Record versus reality', icon: 'record', hue: 5 },
  { id: 'site', label: 'Site', icon: 'site', hue: 6 },
  { id: 'database', label: 'Database', icon: 'database', hue: 7 },
  { id: 'other', label: 'Other', icon: 'tool', hue: 8 },
]
const IN: Record<Exclude<Family, 'other'>, string> = {
  access: 'step_free_route turning_space bathroom_clearance stairs_count aging_in_place furniture_fit stretcher_route robot_fit curb_to_door door_widths measure_search access',
  flood: 'flood_rehearsal valuables_height storm_plan flood',
  fire: 'fire_preplan egress_routes life_safety_census smoke_clock size_up_quiz fire',
  office: 'room_labeller office_fit amenity_census unit_compare takeoff_bid storage_space room_census',
  record: 'record_vs_reality listing_claims daylight derived_fields field_audit property_coverage record',
  site: 'roof_facts loading_docks truck_access parking_count path_to_water risk_sheet daycare_capacity',
  database: 'city_census similar_rooms facts_query',
}
const OF = new Map(Object.entries(IN).flatMap(([f, ids]) => ids.split(' ').map((id) => [id, f as Family])))
export const familyOf = (tool: string): Family => OF.get(tool) ?? 'other'
export const family = (tool: string) => FAMILIES.find((f) => f.id === familyOf(tool))!

const LAYER: Record<string, string> = {
  'matterport.walls': 'Wall outline', 'matterport.room_labels': 'Room names', 'matterport.panos': '360° photos', 'matterport.openings': 'Doors and windows',
  'matterport.polygons': 'Room outlines', 'matterport.defurnished': 'Empty-room photos', 'vexcel.ortho': 'Aerial photo', 'vexcel.oblique': 'Angled aerial photos',
  'vexcel.property': 'Aerial property facts', 'vexcel.elevation': 'Ground heights', 'costar.record': 'Property record', 'drone.photos': 'Drone photos', 'drone.splat': 'Drone capture',
}
const layerName = (l: string) => LAYER[l] ?? l.replace(/^[a-z]+\./, '').replace(/_/g, ' ')

export type ToolInfo = {
  id: string; title: string; summary: string; planned: boolean; family: Family
  /** What it reads. `need` is 'required' or 'optional'. */
  needs: { layer: string; label: string; required: boolean }[]
  /** Questions it asks a person before it can run. */
  asks: string[]
  /** Every input, for the detail view. */
  inputs: { id: string; label: string; about: string; unit?: string; fallback?: string }[]
  draws: string[]; blocks: string[]; examples: string[]
  slow: boolean
  /** It runs on one scan (so it can be started from a building). */
  onScan: boolean
}

type Raw = { id: string; requires?: { layer: string; need: string }[]; overlays?: string[]; blocks?: string[]; examples?: string[]; annotations?: { cost?: string }
  inputs?: { properties?: Record<string, Record<string, unknown>>; required?: string[] } }

/** The catalogue, with what each tool needs and makes. */
export function useTools(): ToolInfo[] {
  const list = useToolCatalog(), raw = useCatalog((s) => s.tools) as unknown as Raw[]
  return useMemo(() => list.map((t) => {
    const m = raw.find((r) => r.id === t.id), props = m?.inputs?.properties ?? {}
    return {
      id: t.id, title: t.title, summary: (t.summary ?? '').replace(/^Planned, not built yet\. /, ''), planned: t.planned, family: familyOf(t.id),
      needs: (m?.requires ?? []).map((r) => ({ layer: r.layer, label: layerName(r.layer), required: r.need === 'required' })),
      asks: Object.values(props).map((p) => p['x-ask']).filter((x): x is string => typeof x === 'string'),
      inputs: Object.entries(props).filter(([k]) => k !== 'scan').map(([k, p]) => ({ id: k, label: String(p.title ?? k), about: String(p.description ?? ''), unit: p['x-unit'] as string | undefined,
        fallback: p.default == null || typeof p.default === 'object' ? undefined : String(p.default) })),
      draws: m?.overlays ?? [], blocks: m?.blocks ?? [], examples: m?.examples ?? [],
      slow: m?.annotations?.cost === 'slow', onScan: !m || 'scan' in props || 'place' in props,
    }
  }), [list, raw])
}
