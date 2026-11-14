import { useMemo, useState, type ComponentProps, type ReactNode } from 'react'
import { Menu } from '@base-ui/react/menu'
import { Popover } from '@base-ui/react/popover'
import { Tooltip } from '@base-ui/react/tooltip'
import type { Source, Status } from '../../../core/index.ts'
import { family } from '../lib/tools.ts'
import { int } from '../lib/format.ts'
import { ICONS } from './icons.ts'

export type IconName = keyof typeof ICONS
export function Icon({ name, size = 15 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 256 256" fill="currentColor" aria-hidden="true" style={{ flex: 'none' }}><path d={ICONS[name]} /></svg>
}

/** The mark: a door leaf and its swing, as a doorway is drawn on a floor plan. */
export function Mark({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true" style={{ flex: 'none' }}>
      <path d="M3 17V3M3 17h14" strokeWidth="1.7" />
      <path d="M3 3a14 14 0 0 1 14 14" strokeWidth="1.1" strokeDasharray="2 2.4" />
    </svg>
  )
}

/* ---------- status ---------- */
const STATUS_WORD: Record<Status, string> = { pass: 'Pass', warn: 'Caution', fail: 'Fail', unknown: 'Not measured' }
export const statusWord = (s: Status) => STATUS_WORD[s]
/** Status is never colour alone: circle passes, triangle cautions, square fails, a dashed ring is not measured. */
export function StatusGlyph({ status, size = 9 }: { status: Status; size?: number }) {
  return (
    <svg className="glyph" data-status={status} width={size} height={size} viewBox="0 0 10 10" role="img" aria-label={STATUS_WORD[status]}>
      {status === 'pass' && <circle cx="5" cy="5" r="4.6" fill="currentColor" />}
      {status === 'warn' && <path d="M5 0.4 9.9 9.6H0.1Z" fill="currentColor" />}
      {status === 'fail' && <rect x="0.4" y="0.4" width="9.2" height="9.2" fill="currentColor" />}
      {status === 'unknown' && <circle cx="5" cy="5" r="3.9" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="1.6 1.4" />}
    </svg>
  )
}
export function St({ status, children }: { status: Status; children?: ReactNode }) {
  return <span className="st" data-status={status}><StatusGlyph status={status} size={8} /><span aria-hidden="true">{children ?? STATUS_WORD[status]}</span></span>
}
/** A run or a step: waiting, working, done, failed. */
export function RunState({ state, children }: { state: 'pending' | 'active' | 'running' | 'done' | 'failed'; children?: ReactNode }) {
  const s = state === 'active' ? 'running' : state
  return (
    <span className="rs" data-state={s}>
      {s === 'running' ? <i className="ring" /> : s === 'done' ? <Icon name="check" size={12} /> : s === 'failed' ? <Icon name="close" size={12} /> : <Icon name="clock" size={12} />}
      {children ?? (s === 'running' ? 'Working' : s === 'done' ? 'Done' : s === 'failed' ? 'Failed' : 'Waiting')}
    </span>
  )
}

/* ---------- where a number came from ---------- */
const LAYER: Record<Source['layer'], [short: string, long: string]> = {
  matterport: ['Scan', 'Interior scan (Matterport)'], vexcel: ['Aerial', 'Aerial survey (Vexcel)'], costar: ['Record', 'Property record (CoStar)'],
  drone: ['Drone', 'Drone capture'], model: ['Model', 'Model judgement'],
  phone: ['Phone', 'Captured on site with a phone'],
}
const METHOD: Record<Source['method'], [short: string, long: string]> = {
  geometry: ['Geo', 'Calculated from geometry'], vision: ['Vis', 'Read from a photo by a vision model'], lookup: ['Look', 'Looked up, not measured'], simulation: ['Sim', 'Simulated'],
  sensor: ['Sens', 'Read by the phone\'s sensors'], manual: ['Tape', 'Measured on site and typed in'],
}
const CONF = { high: 3, medium: 2, low: 1 } as const
export const sourceText = (s: Source) => `${LAYER[s.layer]?.[1] ?? s.layer}, ${(METHOD[s.method]?.[1] ?? s.method).toLowerCase()}`
/** Every measured number carries one: which data layer, which method, how confident. Opens the full note.
    `plain` is the same mark without the popover, for inside a row that is itself a button. */
export function SourceChip({ source, plain }: { source: Source; plain?: boolean }) {
  const n = CONF[source.confidence] ?? 0, layer = LAYER[source.layer] ?? [source.layer, source.layer], method = METHOD[source.method] ?? [source.method, source.method]
  const said = `Source: ${layer[1]}, ${method[1]}, ${source.confidence} confidence`
  const mark = <>{layer[0]}·{method[0]}<span className="pips" aria-hidden="true">{[1, 2, 3].map((i) => <i key={i} className={i > n ? 'off' : ''} />)}</span></>
  if (plain) return <span className="src" title={source.note ? `${said}. ${source.note}` : said}><span className="sr">{said}</span><span aria-hidden="true" style={{ display: 'contents' }}>{mark}</span></span>
  return (
    <Popover.Root>
      {/* a chip in a clickable table row opens its note, not the row */}
      <Popover.Trigger className="src" aria-label={said} onClick={(e) => e.stopPropagation()}>{mark}</Popover.Trigger>
      <Popover.Portal><Popover.Positioner sideOffset={6} align="start" style={{ zIndex: 60 }}><Popover.Popup className="pop">
        <dl className="kv"><dt>Layer</dt><dd>{layer[1]}</dd><dt>Method</dt><dd>{method[1]}</dd><dt>Confidence</dt><dd style={{ textTransform: 'capitalize' }}>{source.confidence}</dd></dl>
        {source.note && <p className="dim" style={{ marginTop: 8, fontSize: 'var(--text-xs)' }}>{source.note}</p>}
      </Popover.Popup></Popover.Positioner></Popover.Portal>
    </Popover.Root>
  )
}

/* ---------- tools ---------- */
export const toolHue = (id: string) => `var(--tool-${family(id).hue})`
const code = (title: string) => { const w = title.replace(/[^A-Za-z ]/g, '').split(/\s+/).filter(Boolean); return ((w[0]?.[0] ?? '') + (w[1]?.[0] ?? w[0]?.[1] ?? '')).toUpperCase() }
/** A tool's key: two letters on its family's hue. */
export function ToolKey({ id, title }: { id: string; title: string }) {
  return <span className="toolkey" style={{ background: toolHue(id) }} aria-hidden="true">{code(title)}</span>
}

/** Resolve a design token to [r, g, b, a] (0 to 255) for canvases that cannot read CSS variables. */
export function tokenRgba(name: string): [number, number, number, number] {
  const probe = document.createElement('i')
  probe.style.color = `var(${name})`
  document.body.append(probe)
  const m = getComputedStyle(probe).color.match(/[\d.]+/g)!.map(Number)
  probe.remove()
  return [m[0], m[1], m[2], Math.round((m[3] ?? 1) * 255)]
}
export const tokenCss = (name: string) => { const [r, g, b, a] = tokenRgba(name); return `rgba(${r},${g},${b},${a / 255})` }

/* ---------- small controls ---------- */
export function Tip({ label, kbd, children }: { label: string; kbd?: string; children: React.ReactElement }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger render={children} />
      <Tooltip.Portal><Tooltip.Positioner sideOffset={6} style={{ zIndex: 70 }}><Tooltip.Popup className="tip">{label}{kbd && <span className="kbd">{kbd}</span>}</Tooltip.Popup></Tooltip.Positioner></Tooltip.Portal>
    </Tooltip.Root>
  )
}
export function IconBtn({ icon, label, kbd, className = 'btn icon quiet', size, ...rest }: { icon: IconName; label: string; kbd?: string; size?: number } & Omit<ComponentProps<'button'>, 'children'>) {
  return <Tip label={label} kbd={kbd}><button type="button" className={className} aria-label={label} {...rest}><Icon name={icon} size={size} /></button></Tip>
}
export function Seg<T extends string>({ value, onChange, options, label, compact }: { value: T; onChange: (v: T) => void; label: string; compact?: boolean; options: { id: T; label: string; icon?: IconName; disabled?: boolean; title?: string }[] }) {
  return (
    <div className="seg" role="group" aria-label={label} data-compact={compact || undefined}>
      {options.map((o) => <button key={o.id} type="button" aria-pressed={value === o.id} disabled={o.disabled} title={o.title ?? (compact ? o.label : undefined)} aria-label={o.label} onClick={() => onChange(o.id)}>{o.icon && <Icon name={o.icon} size={14} />}<span>{o.label}</span></button>)}
    </div>
  )
}
export function Empty({ icon, title, children, action }: { icon: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return <div className="empty"><span className="ico"><Icon name={icon} /></span><b>{title}</b>{children && <p>{children}</p>}{action}</div>
}
export function Stats({ items }: { items: { label: string; value: ReactNode; unit?: string }[] }) {
  return <dl className="stats">{items.map((s) => <div key={s.label}><dt>{s.label}</dt><dd>{s.value}{s.unit && <small>{s.unit}</small>}</dd></div>)}</dl>
}
export function Copy({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [done, setDone] = useState(false)
  return <IconBtn icon={done ? 'check' : 'copy'} label={done ? 'Copied' : label} className="btn icon quiet sm" size={13} onClick={() => { void navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1400) }) }} />
}
/** A button that opens a menu. Children are Menu.Item, Menu.CheckboxItem and so on. */
export function MenuBtn({ trigger, children, align = 'start', side = 'bottom' }: { trigger: React.ReactElement; children: ReactNode; align?: 'start' | 'end' | 'center'; side?: 'bottom' | 'top' | 'right' }) {
  return (
    <Menu.Root>
      <Menu.Trigger render={trigger} />
      <Menu.Portal><Menu.Positioner sideOffset={4} align={align} side={side} style={{ zIndex: 60 }}><Menu.Popup className="menu">{children}</Menu.Popup></Menu.Positioner></Menu.Portal>
    </Menu.Root>
  )
}
export { Menu }

/* ---------- data table: sort, choose columns, select a row, show more ---------- */
export type Col<T> = {
  id: string; label: string
  /** Right-aligned: a number. */
  num?: boolean
  width?: number | string
  /** The value a click on the header sorts by. Missing: not sortable. */
  sort?: (row: T) => number | string | null | undefined
  cell: (row: T) => ReactNode
  /** Hidden until the person turns it on. */
  off?: boolean
  /** Always shown. */
  fixed?: boolean
}
const colsKey = (id: string) => `threshold.app.cols.${id}`
/** Which columns are shown, remembered per table, and the button that chooses them. */
export function useColumns<T>(id: string, cols: Col<T>[]) {
  const [hidden, setHidden] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(colsKey(id)) ?? 'null') ?? cols.filter((c) => c.off).map((c) => c.id) } catch { return cols.filter((c) => c.off).map((c) => c.id) } })
  const toggle = (col: string) => setHidden((h) => { const next = h.includes(col) ? h.filter((x) => x !== col) : [...h, col]; try { localStorage.setItem(colsKey(id), JSON.stringify(next)) } catch { /* not remembered */ } return next })
  const shown = useMemo(() => cols.filter((c) => c.fixed || !hidden.includes(c.id)), [cols, hidden])
  const chooser = (
    <MenuBtn align="end" trigger={<button type="button" className="btn sm quiet" aria-label="Choose columns"><Icon name="columns" size={14} />Columns</button>}>
      <div className="mh">Columns</div>
      {cols.filter((c) => !c.fixed).map((c) => (
        <Menu.CheckboxItem key={c.id} checked={!hidden.includes(c.id)} onCheckedChange={() => toggle(c.id)} closeOnClick={false}>
          <span className="mi-check"><Menu.CheckboxItemIndicator><Icon name="check" size={12} /></Menu.CheckboxItemIndicator></span>{c.label}
        </Menu.CheckboxItem>
      ))}
    </MenuBtn>
  )
  return { shown, chooser }
}

type TableProps<T> = {
  cols: Col<T>[]; rows: T[]; rowKey: (row: T) => string
  onRow?: (row: T) => void; selected?: string | null
  /** Rows in the shape of what is coming. */
  loading?: boolean
  empty?: ReactNode
  /** What the rows are, for the count ("building"). */
  noun?: string
  /** Sort to start with. Missing: the order given (a ranking keeps its order until the person sorts). */
  sortBy?: { col: string; dir: 1 | -1 }
  page?: number
  foot?: ReactNode
  label: string
}
export function DataTable<T>({ cols, rows, rowKey, onRow, selected, loading, empty, noun = 'row', sortBy, page = 200, foot, label }: TableProps<T>) {
  const [sort, setSort] = useState<{ col: string; dir: 1 | -1 } | null>(sortBy ?? null)
  const [limit, setLimit] = useState(page)
  const sorted = useMemo(() => {
    const by = sort && cols.find((c) => c.id === sort.col)?.sort
    if (!by) return rows
    const val = (r: T) => by(r)
    return [...rows].sort((a, b) => {
      const x = val(a), y = val(b)
      if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1 // missing values last, either way
      return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * sort!.dir
    })
  }, [rows, sort, cols])
  const shown = sorted.slice(0, limit)
  return (
    <div className="tblwrap">
      <div className="tblscroll">
        <table className="tbl" aria-label={label}>
          <thead><tr>
            {cols.map((c) => (
              <th key={c.id} scope="col" data-col={c.id} className={c.num ? 'r' : undefined} style={{ width: c.width }} aria-sort={sort?.col === c.id ? (sort.dir === 1 ? 'ascending' : 'descending') : undefined}>
                {c.sort ? (
                  <button type="button" onClick={() => setSort(sort?.col === c.id ? (sort.dir === (c.num ? -1 : 1) ? { col: c.id, dir: c.num ? 1 : -1 } : null) : { col: c.id, dir: c.num ? -1 : 1 })}>
                    {c.label}{sort?.col === c.id && <span aria-hidden="true">{sort.dir === 1 ? '↑' : '↓'}</span>}
                  </button>
                ) : c.label}
              </th>
            ))}
          </tr></thead>
          <tbody>
            {loading && !rows.length && Array.from({ length: 8 }, (_, i) => (
              <tr key={i} className="skrow">{cols.map((c, j) => <td key={c.id}><span className="sk" style={{ width: `${[62, 38, 46, 30, 52][(i + j) % 5]}%`, marginLeft: c.num ? 'auto' : 0 }} /></td>)}</tr>
            ))}
            {shown.map((r) => {
              const k = rowKey(r)
              return (
                <tr key={k} data-click={onRow ? '' : undefined} aria-selected={selected != null ? selected === k : undefined} tabIndex={onRow ? 0 : undefined}
                  onClick={onRow && (() => onRow(r))} onKeyDown={onRow && ((e) => { if (e.key === 'Enter' && e.target === e.currentTarget) onRow(r) })}>
                  {cols.map((c) => <td key={c.id} data-col={c.id} className={c.num ? 'r' : undefined}>{c.cell(r)}</td>)}
                </tr>
              )
            })}
          </tbody>
        </table>
        {!loading && !rows.length && empty}
      </div>
      {(rows.length > 0 || foot) && (
        <div className="tblfoot">
          {rows.length > 0 && <span>{shown.length < rows.length ? `1 to ${int(shown.length)} of ${int(rows.length)} ${noun}s` : `${int(rows.length)} ${noun}${rows.length === 1 ? '' : 's'}`}</span>}
          {shown.length < rows.length && <button type="button" className="btn sm" onClick={() => setLimit(limit + page)}>Show {Math.min(page, rows.length - shown.length)} more</button>}
          {foot}
        </div>
      )}
    </div>
  )
}
