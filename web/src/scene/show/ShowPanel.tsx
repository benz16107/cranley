// What a show says on top of the picture: the flood's loss list, the fire's room table, a tour's caption, and where
// every number came from. The transport (play, time slider) belongs to the look's toolbar; see ShowBar.
import { useEffect, useRef } from 'react'
import { mmss } from './fire.ts'
import type { ShowState } from './types.ts'

const usd = (n: number) => `$${Math.round(n).toLocaleString('en-US')}`

function Sources({ state }: { state: ShowState }) {
  if (!state.sources.length) return null
  return (
    <details className="th-show-src">
      <summary>Where these numbers come from</summary>
      <dl>{state.sources.map((s) => <div key={s.what}><dt>{s.what} <span className="th-conf" data-c={s.confidence}>{s.confidence} confidence</span></dt><dd>{s.text}</dd></div>)}</dl>
    </details>
  )
}

function Flood({ state }: { state: ShowState }) {
  const f = state.flood!, list = useRef<HTMLUListElement>(null), wet = f.wet
  // the newest wet item stays in view as the list fills
  useEffect(() => { list.current?.querySelector<HTMLElement>(`li:nth-child(${wet})`)?.scrollIntoView({ block: 'nearest' }) }, [wet])
  return (
    <section className="th-show-panel" data-scene-ui aria-label="Flood, hour by hour">
      <header><b>{state.title}</b><span className="th-num">{state.clock}</span></header>
      <dl className="th-show-facts">
        <div><dt>Above the ground outside</dt><dd className="th-num">{f.outside_m.toFixed(2)} m</dd></div>
        <div><dt>On the entry floor</dt><dd className="th-num">{f.inside_m.toFixed(2)} m</dd></div>
        <div><dt>Rooms taking water</dt><dd className="th-num">{f.rooms_wet}</dd></div>
      </dl>
      {f.list === 'ready' ? (
        <>
          <h4>What the water reaches <span className="th-num">{f.wet} of {f.items.length}</span>{f.loss_usd && f.loss_usd[1] > 0 && <span className="th-num th-show-loss">{usd(f.loss_usd[0])} to {usd(f.loss_usd[1])}</span>}</h4>
          <ul ref={list} className="th-show-list">
            {f.items.map((it, i) => (
              <li key={it.id} data-wet={i < f.wet || undefined}>
                <i /><span className="th-show-name">{it.name}</span><span className="th-show-room">{it.room_label}</span>
                <span className="th-num">{it.height_m < 0.03 ? 'on the floor' : `${it.height_m.toFixed(2)} m up`}</span>
              </li>
            ))}
          </ul>
        </>
      ) : <p className="th-show-note" role="status">{f.listNote}</p>}
      <Sources state={state} />
    </section>
  )
}

function Fire({ state }: { state: ShowState }) {
  const f = state.fire!
  return (
    <section className="th-show-panel" data-scene-ui aria-label="Fire, minute by minute">
      <header><b>{state.title}</b><span className="th-num">{state.clock} of {f.end}</span></header>
      <table className="th-show-table">
        <thead><tr><th>Room</th><th>Smoke down to</th><th>Upper layer</th><th>Lost at</th></tr></thead>
        <tbody>
          {f.rooms.map((r) => (
            <tr key={r.id} data-lost={r.lost || undefined} title={r.cause ?? undefined}>
              <td>{r.label}{r.fire && <span className="th-show-tag">fire</span>}</td>
              <td className="th-num">{r.layer_m.toFixed(2)} m</td>
              <td className="th-num">{r.upper_c} °C</td>
              <td className="th-num">{r.untenable_s == null ? 'not in the run' : mmss(r.untenable_s)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="th-show-note">Bedroom doors {f.doors}. Routes out turn red where the room they cross is lost.</p>
      <Sources state={state} />
    </section>
  )
}

export function ShowPanel({ state }: { state: ShowState }) {
  if (state.status === 'missing') return <p className="th-note th-show-missing" role="status">{state.reason}</p>
  if (state.status === 'loading') return <p className="th-note th-show-missing" role="status">Loading {state.kind === 'flood' ? 'the storm record' : state.kind === 'fire' ? 'the fire model' : 'the tour'}</p>
  if (state.kind === 'flood' && state.flood) return <Flood state={state} />
  if (state.kind === 'fire' && state.fire) return <Fire state={state} />
  if (state.kind === 'tour' && state.tour) {
    const t = state.tour
    return (
      <div className="th-caption" role="status" aria-live="polite" data-status={t.status}>
        <span className="th-caption-head"><i /><b>{t.title}</b><span className="th-num">{state.clock}</span></span>
        <span className="th-caption-line">{t.line}</span>
      </div>
    )
  }
  return null
}
