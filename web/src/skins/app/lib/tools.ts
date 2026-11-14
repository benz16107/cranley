import { useMemo } from 'react'
import { CITIES, useCatalog, useToolCatalog } from '../../../core/index.ts'
import type { ICONS } from '../design/icons.ts'

/* Tool families, and the parts of a tool's manifest the catalogue shows.
   Stand-in: no field on a tool says its family, and CatalogTool does not carry what a tool needs (core-requests.md,
   App 5). This map names the 50 tools the server lists on 2026-11-14; a tool it does not know falls under "Other". */
export type Family = 'access' | 'flood' | 'fire' | 'office' | 'record' | 'site' | 'database' | 'phone' | 'other'
export const FAMILIES: { id: Family; label: string; icon: keyof typeof ICONS; hue: number }[] = [
  { id: 'access', label: 'Access', icon: 'wheelchair', hue: 1 },
  { id: 'flood', label: 'Flood', icon: 'drop', hue: 2 },
  { id: 'fire', label: 'Fire', icon: 'fire', hue: 3 },
  { id: 'office', label: 'Office and units', icon: 'office', hue: 4 },
  { id: 'record', label: 'Record versus reality', icon: 'record', hue: 5 },
  { id: 'site', label: 'Site', icon: 'site', hue: 6 },
  { id: 'database', label: 'Database', icon: 'database', hue: 7 },
  { id: 'phone', label: 'On site', icon: 'camera', hue: 8 },
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
  phone: 'field_check floor_height photo_measure slope_check window_check noise_level walkthrough where_am_i',
}
const OF = new Map(Object.entries(IN).flatMap(([f, ids]) => ids.split(' ').map((id) => [id, f as Family])))
export const familyOf = (tool: string): Family => OF.get(tool) ?? 'other'
export const family = (tool: string) => FAMILIES.find((f) => f.id === familyOf(tool))!

const LAYER: Record<string, string> = {
  'matterport.walls': 'Wall outline', 'matterport.rooms': 'Rooms', 'matterport.room_labels': 'Room names', 'matterport.openings': 'Doors and windows',
  'matterport.panos': '360° photos', 'matterport.panoramas': '360° photos', 'matterport.defurnished': 'Empty-room photos', 'matterport.geo': 'Scan position', 'matterport.index': 'Scan index',
  'vexcel.ortho': 'Aerial photo', 'vexcel.oblique': 'Angled aerial photos', 'vexcel.property': 'Aerial property facts', 'vexcel.elevation': 'Ground heights', 'vexcel.dtm': 'Ground heights',
  'vexcel.dsm': 'Roof heights', 'vexcel.footprint': 'Building footprint', 'costar.property': 'Property record', 'costar.listing': 'Listing', 'drone.photos': 'Drone photos', 'drone.splat': 'Drone capture',
  'threshold.facts': 'Facts database', 'threshold.facts.rooms': 'Room descriptions', 'threshold.measures': 'Measures table', 'osm.streets': 'Street map',
}
/** A manifest's input title ("Floor Height M") as a label: sentence case, without the unit it repeats. */
const inputLabel = (t: string) => { const s = t.replace(/ (M|M2|Ft2|Kw|Min|Pct|Km)$/, '').toLowerCase(); return s.charAt(0).toUpperCase() + s.slice(1) }
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
  /** It cannot run without a scan. */
  needsScan: boolean
  /** The inputs a person can set when starting it by hand, the ones to show first leading. */
  fields: Field[]
  /** Starting it by hand opens the form first: it has no scan to run on, or needs something no question asks for. */
  form: boolean
}

/* ---------- starting a tool by hand: its manifest's inputs as form fields ---------- */
export type Field = {
  id: string; label: string; about: string
  kind: 'text' | 'long' | 'number' | 'choice' | 'toggle' | 'room' | 'capture' | 'criteria' | 'point' | 'reading'
  required: boolean
  /** Shown up front; the rest sit under "More settings". */
  first: boolean
  options?: string[]; unit?: string; min?: number; max?: number; whole?: boolean
  /** What the tool uses when the field is left alone. */
  fallback?: string | number | boolean
  /** A value to start from when the tool has no default of its own. */
  start?: string | number | boolean
}
/* What a person is offered first, where the manifest alone does not say: which inputs lead, and a value to start
   from so the tool can run as it opens. Stand-in until a manifest carries this (core-requests.md, App 6). */
const START: Record<string, { first?: string[]; values?: Record<string, string | number | boolean> }> = {
  city_census: { first: ['preset', 'city', 'kind'], values: { preset: 'wheelchair_homes' } },
  similar_rooms: { first: ['query', 'label', 'city', 'min_area_m2'], values: { query: 'A sunlit kitchen with an island' } },
  facts_query: { values: { question: 'How many scans of each kind are in each city?', sql: 'SELECT city, kind, count(*) AS scans\nFROM threshold.scan\nGROUP BY city, kind\nORDER BY scans DESC' } },
  measure_search: { first: ['criteria', 'city', 'kind'], values: { criteria: 'wheelchair_bath == 1\nfloors == 1' } },
  field_audit: { first: ['sample', 'deep_top'], values: { sample: 12, deep_top: 3 } },
  noise_level: { first: ['readings'] },
  slope_check: { first: ['reading_deg', 'mode'] },
  where_am_i: { first: ['geo'] },
}
const SKIP = new Set(['scan', 'place', 'scans', 'opening', 'points', 'points_from', 'near', 'within_km'])
const KIND: Record<string, Field['kind']> = { capture: 'capture', criteria: 'criteria', readings: 'reading', geo: 'point', room: 'room', fire_room: 'room' }
function fieldsOf(tool: string, props: Record<string, Record<string, unknown>>, required: string[]): Field[] {
  const hint = START[tool], out: Field[] = []
  for (const [id, p] of Object.entries(props)) {
    if (SKIP.has(id)) continue
    const t = { ...p, ...(p.anyOf as Record<string, unknown>[] | undefined)?.find((x) => x.type !== 'null') }
    if (id === 'city') t.enum = Object.values(CITIES).map((c) => c.name) // the two cities there are, not free text
    const kind: Field['kind'] | null = KIND[id] ?? (Array.isArray(t.enum) ? 'choice' : t.type === 'boolean' ? 'toggle' : t.type === 'number' || t.type === 'integer' ? 'number' : t.type === 'string' ? (id === 'sql' || id === 'text' ? 'long' : 'text') : null)
    if (!kind) continue // lists and nested objects are left to the tool's own defaults
    const need = required.includes(id), dflt = p.default
    out.push({
      id, kind, label: inputLabel(String(p.title ?? id)), about: String(p['x-ask'] ?? p.description ?? ''), required: need,
      first: hint?.first ? hint.first.includes(id) : need || typeof p['x-ask'] === 'string' || hint?.values?.[id] != null,
      options: t.enum as string[] | undefined, unit: p['x-unit'] as string | undefined, whole: t.type === 'integer',
      min: (t.minimum ?? t.exclusiveMinimum) as number | undefined, max: (t.maximum ?? t.exclusiveMaximum) as number | undefined,
      fallback: dflt == null || typeof dflt === 'object' ? undefined : (dflt as Field['fallback']), start: hint?.values?.[id],
    })
  }
  return out.sort((a, b) => Number(b.first) - Number(a.first) || (hint?.first ? hint.first.indexOf(a.id) - hint.first.indexOf(b.id) : 0))
}

type Raw = { id: string; requires?: { layer: string; need: string }[]; overlays?: string[]; blocks?: string[]; examples?: string[]; annotations?: { cost?: string }
  inputs?: { properties?: Record<string, Record<string, unknown>>; required?: string[] } }

/** The catalogue, with what each tool needs and makes. */
export function useTools(): ToolInfo[] {
  const list = useToolCatalog(), raw = useCatalog((s) => s.tools) as unknown as Raw[]
  return useMemo(() => list.map((t) => {
    const m = raw.find((r) => r.id === t.id), props = m?.inputs?.properties ?? {}, need = m?.inputs?.required ?? []
    const fields = fieldsOf(t.id, props, need)
    return {
      id: t.id, title: t.title, summary: (t.summary ?? '').replace(/^Planned, not built yet\. /, ''), planned: t.planned, family: familyOf(t.id),
      needs: (m?.requires ?? []).map((r) => ({ layer: r.layer, label: layerName(r.layer), required: r.need === 'required' })),
      asks: Object.values(props).map((p) => p['x-ask']).filter((x): x is string => typeof x === 'string'),
      inputs: Object.entries(props).filter(([k]) => k !== 'scan').map(([k, p]) => ({ id: k, label: inputLabel(String(p.title ?? k)), about: String(p.description ?? ''), unit: p['x-unit'] as string | undefined,
        fallback: p.default == null || typeof p.default === 'object' ? undefined : p.default === true ? 'yes' : p.default === false ? 'no' : String(p.default) })),
      draws: m?.overlays ?? [], blocks: m?.blocks ?? [], examples: m?.examples ?? [],
      slow: m?.annotations?.cost === 'slow', onScan: !m || 'scan' in props || 'place' in props,
      needsScan: !m || need.includes('scan') || need.includes('place'), fields,
      form: !!m && (!('scan' in props || 'place' in props) || t.id in START || fields.some((f) => f.required && typeof props[f.id]?.['x-ask'] !== 'string')),
    }
  }), [list, raw])
}
