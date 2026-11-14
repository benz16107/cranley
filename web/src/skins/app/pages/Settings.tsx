import { Switch } from '@base-ui/react/switch'
import { useCatalog, useToolCatalog, useWorkspace } from '../../../core/index.ts'
import { Copy, Icon, Seg } from '../design/ui.tsx'
import { useSeen } from '../lib/pending.ts'
import { Learned } from '../shell/RunPanel.tsx'
import { SHORTCUTS } from '../shell/Shell.tsx'
import { useTheme, type Theme } from '../shell/theme.ts'
import { useUi } from '../shell/store.ts'

export function Settings() {
  const { theme, setTheme } = useTheme()
  const follow = useWorkspace((s) => s.follow), setFollow = useWorkspace((s) => s.setFollow)
  const id = useWorkspace((s) => s.doc.id)
  const live = useCatalog((s) => s.live), tools = useToolCatalog()
  const seen = useSeen((s) => Object.keys(s.all).length)
  const { rail, setRail } = useUi()
  const clear = (prefix: string) => { try { for (const k of Object.keys(localStorage)) if (k.startsWith(prefix)) localStorage.removeItem(k) } catch { /* nothing kept */ } window.location.reload() }
  return (
    <div className="page"><div className="inner narrow settings">
      <section className="card">
        <header><h2>Appearance</h2></header>
        <div className="set"><div><b>Colour scheme</b><p>Light is ink on paper. Dark is a blueprint. The 3D view reloads when this changes.</p></div>
          <Seg label="Colour scheme" value={theme} onChange={(t: Theme) => setTheme(t)} options={[{ id: 'system', label: 'System', icon: 'monitor' }, { id: 'light', label: 'Light', icon: 'sun' }, { id: 'dark', label: 'Dark', icon: 'moon' }]} /></div>
        <div className="set"><div><b>Narrow sidebar</b><p>Icons only, to give the map and the building more room.</p></div><Switch.Root className="switch" checked={rail} onCheckedChange={setRail} aria-label="Narrow sidebar"><Switch.Thumb className="knob" /></Switch.Root></div>
      </section>
      <section className="card">
        <header><h2>Agent</h2></header>
        <div className="set"><div><b>Follow the agent’s view</b><p>When the agent looks at a finding, go to that building or that point on the map. Turn it off to stay where you are while it works.</p></div><Switch.Root className="switch" checked={follow} onCheckedChange={setFollow} aria-label="Follow the agent’s view"><Switch.Thumb className="knob" /></Switch.Root></div>
        <div className="set"><div><b>Server</b><p>{live == null ? 'Checking.' : live ? `Connected. ${tools.length} tools listed.` : 'Not answering. Starting points play back a recorded composition.'}</p></div><span className="rs" data-state={live ? 'done' : 'pending'}><Icon name={live ? 'check' : 'clock'} size={12} />{live ? 'Connected' : live == null ? 'Checking' : 'Scripted'}</span></div>
      </section>
      <section className="card">
        <header><h2>What has been learned</h2><p className="grow">Answers and changed settings the tools reuse. Each can be undone.</p></header>
        <Learned />
      </section>
      <section className="card">
        <header><h2>Your data</h2></header>
        <div className="body stack">
          <p>There is no sign-in. The open investigation is kept on the Threshold server under an id held in this browser, so a reload shows the same work. Anyone using this browser sees it.</p>
          <p>What you type in a brief or to the agent is sent to the Threshold server and to the language model it uses. Tool results are also written to the project’s facts database. Building data comes from interior scans (Matterport), aerial surveys (Vexcel) and property records (CoStar), used under the event’s terms.</p>
          <p className="muted">There are no terms of service or privacy policy yet. Do not put personal details in a brief beyond what the question needs.</p>
        </div>
        <div className="set"><div><b>Open investigation</b><p className="row"><span className="num">{id || 'none'}</span>{id && <Copy text={id} label="Copy the id" />}</p></div></div>
        <div className="set"><div><b>Investigations listed in this browser</b><p>{seen} listed. Clearing the list does not delete them from the server.</p></div><button className="btn" disabled={!seen} onClick={() => clear('threshold.app.investigations')}>Clear the list</button></div>
        <div className="set"><div><b>Layout choices</b><p>Table columns, the sidebar and the agent panel.</p></div><button className="btn" onClick={() => clear('threshold.app.')}>Reset</button></div>
      </section>
      <section className="card">
        <header><h2>Keyboard</h2></header>
        <div className="body"><dl className="keys">{SHORTCUTS.map(([k, w]) => <div key={k}><dt>{k.split(' ').map((x, i) => (x === 'then' ? <span key={i} className="muted">then</span> : <span key={i} className="kbd">{x}</span>))}</dt><dd>{w}</dd></div>)}</dl></div>
      </section>
    </div></div>
  )
}
