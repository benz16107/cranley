import type { ReactNode } from 'react'
import { Popover } from '@base-ui/react/popover'
import type { Source, Status } from '../../../core/index.ts'

/* Icons: Phosphor (regular), MIT. One set, drawn with currentColor. */
const ICONS = {
  search: 'm229.66 218.34l-50.07-50.06a88.11 88.11 0 1 0-11.31 11.31l50.06 50.07a8 8 0 0 0 11.32-11.32M40 112a72 72 0 1 1 72 72a72.08 72.08 0 0 1-72-72',
  close: 'M205.66 194.34a8 8 0 0 1-11.32 11.32L128 139.31l-66.34 66.35a8 8 0 0 1-11.32-11.32L116.69 128L50.34 61.66a8 8 0 0 1 11.32-11.32L128 116.69l66.34-66.35a8 8 0 0 1 11.32 11.32L139.31 128Z',
  plus: 'M224 128a8 8 0 0 1-8 8h-80v80a8 8 0 0 1-16 0v-80H40a8 8 0 0 1 0-16h80V40a8 8 0 0 1 16 0v80h80a8 8 0 0 1 8 8',
  undo: 'M224 128a96 96 0 0 1-94.71 96H128a95.38 95.38 0 0 1-65.9-26.2a8 8 0 0 1 11-11.63a80 80 0 1 0-1.67-114.78a3 3 0 0 1-.26.25L44.59 96H72a8 8 0 0 1 0 16H24a8 8 0 0 1-8-8V56a8 8 0 0 1 16 0v29.8L60.25 60A96 96 0 0 1 224 128',
  down: 'm213.66 101.66l-80 80a8 8 0 0 1-11.32 0l-80-80a8 8 0 0 1 11.32-11.32L128 164.69l74.34-74.35a8 8 0 0 1 11.32 11.32',
  sun: 'M120 40V16a8 8 0 0 1 16 0v24a8 8 0 0 1-16 0m72 88a64 64 0 1 1-64-64a64.07 64.07 0 0 1 64 64m-16 0a48 48 0 1 0-48 48a48.05 48.05 0 0 0 48-48M58.34 69.66a8 8 0 0 0 11.32-11.32l-16-16a8 8 0 0 0-11.32 11.32Zm0 116.68l-16 16a8 8 0 0 0 11.32 11.32l16-16a8 8 0 0 0-11.32-11.32M192 72a8 8 0 0 0 5.66-2.34l16-16a8 8 0 0 0-11.32-11.32l-16 16A8 8 0 0 0 192 72m5.66 114.34a8 8 0 0 0-11.32 11.32l16 16a8 8 0 0 0 11.32-11.32ZM48 128a8 8 0 0 0-8-8H16a8 8 0 0 0 0 16h24a8 8 0 0 0 8-8m80 80a8 8 0 0 0-8 8v24a8 8 0 0 0 16 0v-24a8 8 0 0 0-8-8m112-88h-24a8 8 0 0 0 0 16h24a8 8 0 0 0 0-16',
  moon: 'M233.54 142.23a8 8 0 0 0-8-2a88.08 88.08 0 0 1-109.8-109.8a8 8 0 0 0-10-10a104.84 104.84 0 0 0-52.91 37A104 104 0 0 0 136 224a103.1 103.1 0 0 0 62.52-20.88a104.84 104.84 0 0 0 37-52.91a8 8 0 0 0-1.98-7.98m-44.64 48.11A88 88 0 0 1 65.66 67.11a89 89 0 0 1 31.4-26A106 106 0 0 0 96 56a104.11 104.11 0 0 0 104 104a106 106 0 0 0 14.92-1.06a89 89 0 0 1-26.02 31.4',
  layers: 'M230.91 172a8 8 0 0 1-2.91 10.91l-96 56a8 8 0 0 1-8.06 0l-96-56A8 8 0 0 1 36 169.09l92 53.65l92-53.65a8 8 0 0 1 10.91 2.91M220 121.09l-92 53.65l-92-53.65a8 8 0 0 0-8 13.82l96 56a8 8 0 0 0 8.06 0l96-56a8 8 0 1 0-8.06-13.82M24 80a8 8 0 0 1 4-6.91l96-56a8 8 0 0 1 8.06 0l96 56a8 8 0 0 1 0 13.82l-96 56a8 8 0 0 1-8.06 0l-96-56A8 8 0 0 1 24 80m23.88 0L128 126.74L208.12 80L128 33.26Z',
  keep: 'M184 32H72a16 16 0 0 0-16 16v176a8 8 0 0 0 12.24 6.78L128 193.43l59.77 37.35A8 8 0 0 0 200 224V48a16 16 0 0 0-16-16m0 177.57l-51.77-32.35a8 8 0 0 0-8.48 0L72 209.57V48h112Z',
  follow: 'M232 120h-8.34A96.14 96.14 0 0 0 136 32.34V24a8 8 0 0 0-16 0v8.34A96.14 96.14 0 0 0 32.34 120H24a8 8 0 0 0 0 16h8.34A96.14 96.14 0 0 0 120 223.66V232a8 8 0 0 0 16 0v-8.34A96.14 96.14 0 0 0 223.66 136H232a8 8 0 0 0 0-16m-96 87.6V200a8 8 0 0 0-16 0v7.6A80.15 80.15 0 0 1 48.4 136H56a8 8 0 0 0 0-16h-7.6A80.15 80.15 0 0 1 120 48.4V56a8 8 0 0 0 16 0v-7.6a80.15 80.15 0 0 1 71.6 71.6H200a8 8 0 0 0 0 16h7.6a80.15 80.15 0 0 1-71.6 71.6M128 88a40 40 0 1 0 40 40a40 40 0 0 0-40-40m0 64a24 24 0 1 1 24-24a24 24 0 0 1-24 24',
  right: 'm221.66 133.66l-72 72a8 8 0 0 1-11.32-11.32L196.69 136H40a8 8 0 0 1 0-16h156.69l-58.35-58.34a8 8 0 0 1 11.32-11.32l72 72a8 8 0 0 1 0 11.32',
  left: 'M224 128a8 8 0 0 1-8 8H59.31l58.35 58.34a8 8 0 0 1-11.32 11.32l-72-72a8 8 0 0 1 0-11.32l72-72a8 8 0 0 1 11.32 11.32L59.31 120H216a8 8 0 0 1 8 8',
  filter: 'M40 88h33a32 32 0 0 0 62 0h81a8 8 0 0 0 0-16h-81a32 32 0 0 0-62 0H40a8 8 0 0 0 0 16m64-24a16 16 0 1 1-16 16a16 16 0 0 1 16-16m112 104h-17a32 32 0 0 0-62 0H40a8 8 0 0 0 0 16h97a32 32 0 0 0 62 0h17a8 8 0 0 0 0-16m-48 24a16 16 0 1 1 16-16a16 16 0 0 1-16 16',
} as const

export function Icon({ name, size = 16 }: { name: keyof typeof ICONS; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 256 256" fill="currentColor" aria-hidden="true" style={{ flex: 'none' }}>
      <path d={ICONS[name]} />
    </svg>
  )
}

/** The mark: a door leaf and its swing, as a doorway is drawn on a floor plan. */
export function Mark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
      <path d="M3 17V3M3 17h14" strokeWidth="1.7" />
      <path d="M3 3a14 14 0 0 1 14 14" strokeWidth="1.1" strokeDasharray="2 2.4" />
    </svg>
  )
}

const STATUS_WORD: Record<Status, string> = { pass: 'Pass', warn: 'Caution', fail: 'Fail', unknown: 'Not measured' }

/** Status is never colour alone: circle passes, triangle cautions, square fails, an open ring is unknown. */
export function StatusGlyph({ status, size = 10 }: { status: Status; size?: number }) {
  return (
    <svg className="glyph" data-status={status} width={size} height={size} viewBox="0 0 10 10" role="img" aria-label={STATUS_WORD[status]}>
      {status === 'pass' && <circle cx="5" cy="5" r="4.6" fill="currentColor" />}
      {status === 'warn' && <path d="M5 0.4 9.9 9.6H0.1Z" fill="currentColor" />}
      {status === 'fail' && <rect x="0.4" y="0.4" width="9.2" height="9.2" fill="currentColor" />}
      {status === 'unknown' && <circle cx="5" cy="5" r="3.9" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="1.6 1.4" />}
    </svg>
  )
}
export const statusWord = (s: Status) => STATUS_WORD[s]

const LAYER: Record<Source['layer'], [short: string, long: string]> = {
  matterport: ['Scan', 'Interior scan (Matterport)'],
  vexcel: ['Aerial', 'Aerial survey (Vexcel)'],
  costar: ['Record', 'Property record (CoStar)'],
  drone: ['Drone', 'Drone capture'],
  model: ['Model', 'Model judgement'],
}
const METHOD: Record<Source['method'], [short: string, long: string]> = {
  geometry: ['Geo', 'Calculated from geometry'],
  vision: ['Vis', 'Read from a photo by a vision model'],
  lookup: ['Look', 'Looked up, not measured'],
  simulation: ['Sim', 'Simulated'],
}
const CONF = { high: 3, medium: 2, low: 1 } as const

/** Every number carries one of these: which data layer, which method, how confident. Opens the full note. */
export function SourceChip({ source }: { source: Source }) {
  const n = CONF[source.confidence]
  return (
    <Popover.Root>
      <Popover.Trigger className="src" aria-label={`Source: ${LAYER[source.layer][1]}, ${METHOD[source.method][1]}, ${source.confidence} confidence`}>
        {LAYER[source.layer][0]}·{METHOD[source.method][0]}
        <span className="pips" aria-hidden="true">{[1, 2, 3].map((i) => <i key={i} className={i > n ? 'off' : ''} />)}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={6} align="start">
          <Popover.Popup className="pop">
            <dl>
              <dt>Layer</dt><dd>{LAYER[source.layer][1]}</dd>
              <dt>Method</dt><dd>{METHOD[source.method][1]}</dd>
              <dt>Confidence</dt><dd style={{ textTransform: 'capitalize' }}>{source.confidence}</dd>
            </dl>
            {source.note && <p style={{ marginTop: 8, color: 'var(--ink-2)' }}>{source.note}</p>}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}

/* One hue per tool. Known tools keep a fixed slot; any other id hashes into the eight. */
const HUE_SLOT: Record<string, number> = { access: 1, flood: 2, fire: 3, office_fit: 4, record: 5, fit_through: 7, turn: 6, childproof: 8 }
export function toolHue(id: string): string {
  let slot = HUE_SLOT[id]
  if (!slot) { let h = 0; for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0; slot = (h % 8) + 1 }
  return `var(--tool-${slot})`
}
/** Two letters, as a drawing set codes its disciplines (A, S, FP). Taken from the title unless the manifest gives one. */
export function toolCode(title: string): string {
  const w = title.replace(/[^A-Za-z ]/g, '').split(/\s+/).filter(Boolean)
  return ((w[0]?.[0] ?? '') + (w[1]?.[0] ?? w[0]?.[1] ?? '')).toUpperCase()
}
export function ToolKey({ id, title, code }: { id: string; title: string; code?: string }) {
  return <span className="toolkey num" style={{ background: toolHue(id) }} aria-hidden="true">{code ?? toolCode(title)}</span>
}

/** Resolve a design token to an [r, g, b, a] tuple (0 to 255) for canvases that cannot read CSS variables. */
export function tokenRgba(name: string): [number, number, number, number] {
  const probe = document.createElement('i')
  probe.style.color = `var(${name})`
  document.body.append(probe)
  const m = getComputedStyle(probe).color.match(/[\d.]+/g)!.map(Number)
  probe.remove()
  return [m[0], m[1], m[2], Math.round((m[3] ?? 1) * 255)]
}
export const tokenCss = (name: string) => { const [r, g, b, a] = tokenRgba(name); return `rgba(${r},${g},${b},${a / 255})` }

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label style={{ display: 'grid', gap: 6 }}><span className="label">{label}</span>{children}</label>
}
