import type { ReactNode } from 'react'
import NumberFlow from '@number-flow/react'
import { Popover } from '@base-ui/react/popover'
import type { Source, Status } from '../../core/index.ts'
import { STATUS_WORD } from './lib.ts'

/* The small parts every screen of this look uses. Rules for them are in README.md. */


/** Status is never colour alone: circle passes, triangle cautions, square fails, a dashed ring is not measured. */
export function Glyph({ status, size = 11 }: { status: Status; size?: number }) {
  return (
    <svg className="mq-glyph" data-s={status} width={size} height={size} viewBox="0 0 10 10" role="img" aria-label={STATUS_WORD[status]}>
      {status === 'pass' && <circle cx="5" cy="5" r="4.6" fill="currentColor" />}
      {status === 'warn' && <path d="M5 0.4 9.9 9.6H0.1Z" fill="currentColor" />}
      {status === 'fail' && <rect x="0.4" y="0.4" width="9.2" height="9.2" fill="currentColor" />}
      {status === 'unknown' && <circle cx="5" cy="5" r="3.9" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="1.6 1.4" />}
    </svg>
  )
}

const LAYER: Record<Source['layer'], [short: string, long: string]> = {
  matterport: ['Scan', 'Interior scan (Matterport)'], vexcel: ['Aerial', 'Aerial survey (Vexcel)'], costar: ['Record', 'Property record (CoStar)'],
  drone: ['Drone', 'Drone capture'], model: ['Model', 'Model judgement'],
}
const METHOD: Record<Source['method'], [short: string, long: string]> = {
  geometry: ['measured', 'Calculated from geometry'], vision: ['seen', 'Read from a photo by a vision model'],
  lookup: ['looked up', 'Looked up, not measured'], simulation: ['simulated', 'Simulated'],
}
const PIPS = { high: 3, medium: 2, low: 1 } as const

/** Under every number: which data layer, which method, how sure. Opens the whole note. */
export function Src({ source }: { source: Source }) {
  const n = PIPS[source.confidence]
  return (
    <Popover.Root>
      <Popover.Trigger className="mq-src" aria-label={`Source: ${LAYER[source.layer][1]}, ${METHOD[source.method][1]}, ${source.confidence} confidence`}>
        {LAYER[source.layer][0]}, {METHOD[source.method][0]}
        <span className="mq-pips" aria-hidden="true">{[1, 2, 3].map((i) => <i key={i} className={i > n ? 'off' : ''} />)}</span>
      </Popover.Trigger>
      <Popover.Portal><Popover.Positioner sideOffset={6} align="start"><Popover.Popup className="mq-pop">
        <dl><dt>Layer</dt><dd>{LAYER[source.layer][1]}</dd><dt>Method</dt><dd>{METHOD[source.method][1]}</dd><dt>Confidence</dt><dd style={{ textTransform: 'capitalize' }}>{source.confidence}</dd></dl>
        {source.note && <p className="mq-dim">{source.note}</p>}
      </Popover.Popup></Popover.Positioner></Popover.Portal>
    </Popover.Root>
  )
}


/* Icons: Phosphor regular (MIT), drawn with currentColor. Words do most of the work; these are the few marks. */
const ICONS = {
  plus: 'M224 128a8 8 0 0 1-8 8h-80v80a8 8 0 0 1-16 0v-80H40a8 8 0 0 1 0-16h80V40a8 8 0 0 1 16 0v80h80a8 8 0 0 1 8 8',
  close: 'M205.66 194.34a8 8 0 0 1-11.32 11.32L128 139.31l-66.34 66.35a8 8 0 0 1-11.32-11.32L116.69 128L50.34 61.66a8 8 0 0 1 11.32-11.32L128 116.69l66.34-66.35a8 8 0 0 1 11.32 11.32L139.31 128Z',
  search: 'm229.66 218.34l-50.07-50.06a88.11 88.11 0 1 0-11.31 11.31l50.06 50.07a8 8 0 0 0 11.32-11.32M40 112a72 72 0 1 1 72 72a72.08 72.08 0 0 1-72-72',
  undo: 'M224 128a96 96 0 0 1-94.71 96H128a95.38 95.38 0 0 1-65.9-26.2a8 8 0 0 1 11-11.63a80 80 0 1 0-1.67-114.78a3 3 0 0 1-.26.25L44.59 96H72a8 8 0 0 1 0 16H24a8 8 0 0 1-8-8V56a8 8 0 0 1 16 0v29.8L60.25 60A96 96 0 0 1 224 128',
  keep: 'M184 32H72a16 16 0 0 0-16 16v176a8 8 0 0 0 12.24 6.78L128 193.43l59.77 37.35A8 8 0 0 0 200 224V48a16 16 0 0 0-16-16m0 177.57l-51.77-32.35a8 8 0 0 0-8.48 0L72 209.57V48h112Z',
  kept: 'M184 32H72a16 16 0 0 0-16 16v176a8 8 0 0 0 12.24 6.78L128 193.43l59.77 37.35A8 8 0 0 0 200 224V48a16 16 0 0 0-16-16',
  back: 'M224 128a8 8 0 0 1-8 8H59.31l58.35 58.34a8 8 0 0 1-11.32 11.32l-72-72a8 8 0 0 1 0-11.32l72-72a8 8 0 0 1 11.32 11.32L59.31 120H216a8 8 0 0 1 8 8',
  down: 'm213.66 101.66l-80 80a8 8 0 0 1-11.32 0l-80-80a8 8 0 0 1 11.32-11.32L128 164.69l74.34-74.35a8 8 0 0 1 11.32 11.32',
} as const
export function Icon({ name, size = 16 }: { name: keyof typeof ICONS; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 256 256" fill="currentColor" aria-hidden="true" style={{ flex: 'none' }}><path d={ICONS[name]} /></svg>
}

/** What is printed along the top edge of the mat: the mark, then where you are. */
export function Print({ children, onHome }: { children?: ReactNode; onHome: () => void }) {
  return (
    <header className="mq-print">
      <button className="mq-mark" onClick={onHome} aria-label="Threshold, the front door">Threshold</button>
      {children}
    </header>
  )
}

/** The one figure printed large on the mat, with what it is in capitals under it. It counts to a new value. */
export function Big({ value, unit, digits = 2, status, children }: { value: number | null; unit?: string; digits?: number; status?: Status; children: ReactNode }) {
  return (
    <div className="mq-big" data-s={status}>
      <div className="mq-big-n">{value == null ? <span className="mq-big-wait" /> : <NumberFlow value={value} format={{ maximumFractionDigits: digits }} />}{unit && <small>{unit}</small>}</div>
      <div className="mq-big-c mq-caps">{children}</div>
    </div>
  )
}
