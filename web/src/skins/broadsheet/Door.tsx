import { Suspense, useEffect, useMemo, useState } from 'react'
import { NEEDS, Scene, SceneBoundary, compose, fetchPlan, navigate, startOver, useBuildingView, useMapModel, useWorkspace, type SceneProps, type ScanPlan } from '../../core/index.ts'
import { Ask, StartButtons } from './Desk.tsx'
import { Fig, Mark, reduced, useFree } from './parts.tsx'
import { plural } from './words.ts'

/* The front page: one fact, one line to write on, and a real house cut open on the paper. After the sentence, the
   page is composed in view: sections arrive with their reasons, then the questions they need answered. */

/** A house from the feed to put on the front page: the first of a few with a drone capture whose scan has walls. */
function useCoverHouse(): ScanPlan | null {
  const { all } = useMapModel()
  const [plan, setPlan] = useState<ScanPlan | null>(null)
  useEffect(() => {
    if (!all.length || plan) return
    let on = true
    const sids = all.filter((b) => b.splat && b.metro === 'hou').flatMap((b) => b.scans.filter((s) => s.kind === 'home' && s.rooms >= 9 && s.rooms <= 18).slice(0, 1)).slice(0, 4).map((s) => s.sid)
    void (async () => { for (const sid of sids) { const p = await fetchPlan(sid).catch(() => null); if (!on) return; if (p && p.walls.length >= 20) { setPlan(p); return } } })()
    return () => { on = false }
  }, [all, plan])
  return plan
}

function CoverFigure({ sid }: { sid: string }) {
  const v = useBuildingView(sid)
  const setView = v.setView, ready = !!v.plan
  useEffect(() => { if (ready) setView((x) => ({ ...x, mode: 'dollhouse', cut: 1.3 })) }, [ready, setView])
  const free = useFree(false), base = v.sceneProps?.view
  const view = useMemo<SceneProps['view']>(() => base && { ...base, frame: free }, [base, free])
  if (!v.sceneProps) return <div className="state"><i className="unset" /><i className="unset" /></div>
  return (
    <Suspense fallback={<div className="state"><i className="unset" /><i className="unset" /></div>}>
      <SceneBoundary key={v.sceneKey} fallback={<div className="state"><p>The house on this page did not draw.</p></div>}><Scene {...v.sceneProps} view={view} className="bs-scene" /></SceneBoundary>
    </Suspense>
  )
}

export function DoorPage() {
  const { all, state } = useMapModel()
  const doc = useWorkspace((s) => s.doc)
  const [text, setText] = useState('')
  const house = useCoverHouse()
  const composing = !!doc.brief
  const open = doc.questions.filter((q) => q.answer == null)
  const settled = composing && doc.questions.length > 0
  const doors = house?.openings.filter((o) => o.type === 'doorway').length ?? 0
  return (
    <div className="page cover" data-plate="paper">
      <div className="col">
        {!composing ? (
          <>
            <p className="kicker cap">Houston and Los Angeles</p>
            <h1 className="head xl">{state === 'ready' ? <><Mark>{all.length.toLocaleString('en-US')}</Mark> buildings, measured from the inside.</> : state === 'error' ? 'The building list did not load.' : <span className="reading">Counting the buildings</span>}</h1>
            <p className="deck">Say who you are and what you need. An agent picks the measuring tools, runs them on the scans and shows its working.</p>
            <form className="sayline" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void compose(text.trim()) }}>
              <label htmlFor="say" className="cap">In one sentence</label>
              <input id="say" value={text} onChange={(e) => setText(e.target.value)} placeholder="I use a wheelchair and I am choosing a house" autoComplete="off" autoFocus={!reduced()} />
              <button className="btn" disabled={!text.trim()}>Begin</button>
            </form>
            <ol className="starters" aria-label="Or start from one of these">
              {NEEDS.map((n, i) => (
                <li key={n.id}><button title={`Runs on: ${n.runsOn}`} onClick={() => void compose(n.sentence, n.id)}><span className="no">{i + 1}</span><span><b>{n.who}</b> {n.need}</span></button></li>
              ))}
            </ol>
            <p style={{ marginTop: '1.5rem' }}><button className="link" onClick={() => navigate('/map')}>Skip this and open the map</button></p>
          </>
        ) : (
          <>
            <p className="kicker cap"><span>Your brief</span>{!settled && <span className="reading">Composing the page</span>}</p>
            <h1 className="said">“{doc.brief!.text}”</h1>
            {!!doc.brief!.limits?.length && <p className="deck" style={{ fontSize: '1.25rem' }}>{doc.brief!.limits.join(' ')}</p>}
            <section className="sec" aria-labelledby="sections-h">
              <h2 id="sections-h">Sections for this</h2>
              <ol className="picked" aria-live="polite">
                {doc.tools.map((t, i) => <li key={t.id} className="set"><span className="no">{String(i + 1).padStart(2, '0')}</span><span><b>{t.title}</b><span>{t.reason}</span></span></li>)}
                {!settled && <li><span className="no">{String(doc.tools.length + 1).padStart(2, '0')}</span><span className="writing" style={{ marginTop: '0.5rem' }}><i className="unset" /><i className="unset" /></span></li>}
              </ol>
            </section>
            {settled && (
              <section className="sec set" aria-labelledby="before-h">
                <h2 id="before-h">Before the work starts</h2>
                <div className="asks" style={{ marginTop: '1rem' }}>{doc.questions.map((q) => <Ask key={q.id} q={q} />)}</div>
                <div className="row" style={{ marginTop: '1.25rem' }}><StartButtons open={open.length} /></div>
              </section>
            )}
            {!settled && <div className="row" style={{ marginTop: '1.5rem' }}><button className="link" onClick={() => { startOver(); navigate('/', {}, { replace: true }) }}>Start over</button></div>}
          </>
        )}
      </div>
      <div className="stage">{house ? <CoverFigure sid={house.sid} /> : <div className="state"><i className="unset" /><i className="unset" /></div>}</div>
      {house && (
        <figure className="figbar">
          <Fig n={1}>{(house.address ?? house.name).split(',')[0]}, {house.city}, cut open at 1.3 m. Drawn from {house.walls.length} walls and {doors} {plural(doors, 'doorway')} in its scan.</Fig>
          <div className="views"><button className="open" onClick={() => navigate(`/scan/${house.sid}`)}>Open this house</button></div>
        </figure>
      )}
    </div>
  )
}
