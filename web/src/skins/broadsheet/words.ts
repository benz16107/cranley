/* How the page is worded. Every number here arrives in a block and is printed as it is: these functions choose
   which fact leads and how it is formatted, and do no arithmetic that changes a result. Pure, so it runs under
   `node --test`. */
import type { Block, Check, Metric, Source, Status } from '../../core/index.ts'

/** The kind of story a tool writes. It decides the page's rhythm: which fact leads, how checks are set, the figure. */
export type Family = 'access' | 'flood' | 'fire' | 'office' | 'truth' | 'site' | 'data' | 'general'
const FAMILIES: Record<Exclude<Family, 'general'>, string[]> = {
  flood: ['flood_rehearsal', 'valuables_height', 'storm_plan', 'flood'],
  fire: ['fire_preplan', 'egress_routes', 'life_safety_census', 'smoke_clock', 'size_up_quiz', 'fire'],
  access: ['step_free_route', 'turning_space', 'bathroom_clearance', 'furniture_fit', 'stretcher_route', 'robot_fit', 'door_widths', 'curb_to_door', 'aging_in_place', 'stairs_count', 'access', 'fit_through'],
  office: ['room_labeller', 'office_fit', 'amenity_census', 'unit_compare', 'takeoff_bid', 'room_census', 'storage_space', 'property_coverage', 'turn'],
  truth: ['record_vs_reality', 'listing_claims', 'daylight', 'field_audit', 'derived_fields', 'record'],
  site: ['roof_facts', 'loading_docks', 'truck_access', 'parking_count', 'path_to_water', 'risk_sheet', 'daycare_capacity'],
  data: ['city_census', 'similar_rooms', 'facts_query', 'measure_search'],
}
export const familyOf = (tool: string): Family =>
  (Object.keys(FAMILIES) as Exclude<Family, 'general'>[]).find((f) => FAMILIES[f].includes(tool)) ?? 'general'

/** A number as the page prints it: digits by size, never more than two decimals. */
export const num = (v: number | null | undefined) =>
  v == null ? 'not measured' : new Intl.NumberFormat('en-US', { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2 }).format(v)
/** A limit is something a person set or a standard states: printed as given, to the millimetre. */
export const limit = (v: number, u?: string) => `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(v)}${unitOf(u) ? `\u00a0${unitOf(u)}` : ''}`
/** Units as printed. A bare count or score needs no unit after it. */
export const unitOf = (u: string | undefined) => (u === 'm2' ? 'm²' : u === 'ft2' ? 'ft²' : u === 'count' || u === 'score' ? '' : u ?? '')
/** A year is not a quantity: no thousands separator. */
export const plain = (v: number) => String(v)
export const withUnit = (v: number | null | undefined, u?: string) => (v == null ? 'not measured' : `${num(v)}${unitOf(u) ? ` ${unitOf(u)}` : ''}`)
export const ms = (t: number) => (t < 1000 ? `${Math.round(t)} ms` : `${(t / 1000).toFixed(1)} s`)

const WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']
/** A count the way a headline sets it: words to ten, digits after. */
export const word = (n: number) => (Number.isInteger(n) && n >= 0 && n <= 10 ? WORDS[n] : n.toLocaleString('en-US'))
export const plural = (n: number, one: string, many = one + 's') => (n === 1 ? one : many)

export const STATUS_WORD: Record<Status, string> = { pass: 'Passes', warn: 'Close call', fail: 'Does not pass', unknown: 'Not measured' }
const LAYER: Record<Source['layer'], string> = { matterport: 'Scan', vexcel: 'Aerial survey', costar: 'Property record', drone: 'Drone capture', model: 'Model' }
const METHOD: Record<Source['method'], string> = { geometry: 'geometry', vision: 'read from photos', lookup: 'looked up', simulation: 'simulation' }
/** Where a number came from and how sure it is, as one line. */
export const sourceLine = (s: Source) => `${LAYER[s.layer] ?? s.layer} ${METHOD[s.method] ?? s.method} · ${s.confidence} confidence`

/** The fact a story leads with: one measured number, what it measures, and what it is held against. */
export type Lead = { label: string; value: number; unit: string; need: number | null; status: Status; source: Source | null; finding: string | null }

const first = <T extends Block['type']>(blocks: Block[], type: T) => blocks.find((b): b is Extract<Block, { type: T }> => b.type === type)

/** A failing or close check that has both a measurement and a limit leads; otherwise the tool's first metric does.
    Checks arrive worst first and metrics in the tool's own order, so the tool decides what matters. */
export function leadOf(blocks: Block[]): Lead | null {
  const status = first(blocks, 'VerdictHeader')?.status ?? 'unknown'
  const check = first(blocks, 'CheckList')?.checks.find((c: Check) => c.measured != null && c.threshold != null && c.threshold !== 0 && (c.status === 'fail' || c.status === 'warn'))
  if (check) return { label: check.rule, value: check.measured!, unit: check.unit, need: check.threshold, status: check.status, source: null, finding: check.findings[0] ?? null }
  const metric = first(blocks, 'MetricRow')?.metrics.find((m: Metric) => m.value != null)
  if (metric) return { label: metric.label, value: metric.value!, unit: metric.unit, need: null, status, source: metric.source, finding: null }
  return null
}

/** What the limit is called, by the kind of story. */
export function needLine(family: Family, need: number, unit: string): string {
  const n = limit(need, unit)
  return family === 'truth' ? `The record says ${n}.` : family === 'access' || family === 'fire' ? `You need ${n}.` : `The limit is ${n}.`
}

/** Tools write "Rule, Room: detail". The headline takes the part before the colon; the rest is the standfirst's. */
export const headOf = (label: string) => label.split(': ')[0]

/** Headline size by length, so a long verdict still fits the column. */
export const headSize = (text: string) => (text.length > 120 ? 'xs' : text.length > 70 ? 's' : text.length > 34 ? 'm' : 'l')

/** A verdict as a headline and a standfirst: the first sentence leads, the rest follows. A long first clause before a
    semicolon stands as the headline by itself. Decimal points are not sentence ends. The words are the tool's own. */
export function splitVerdict(text: string): [head: string, rest: string] {
  const semi = text.indexOf('; ')
  if (semi >= 40) return [text.slice(0, semi) + '.', text.slice(semi + 2).replace(/^./, (c) => c.toUpperCase())]
  const stop = text.search(/[.!?]\s+\S/)
  return stop < 0 ? [text, ''] : [text.slice(0, stop + 1), text.slice(stop + 1).trim()]
}

/** A media reference "<sid>/<pano>/<face>" or "<sid>/<name>", in parts. A bare id belongs to the finding's own scan. */
export function mediaParts(ref: string, sid: string | null): { sid: string; a: string; b?: string } | null {
  const p = ref.split('/')
  if (p.length >= 2) return { sid: p[0], a: p[1], b: p[2] }
  return sid ? { sid, a: p[0] } : null
}
