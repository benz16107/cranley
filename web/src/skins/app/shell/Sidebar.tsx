import { startOver, useBuildings, useCatalog, useWorkspace } from '../../../core/index.ts'
import { Icon, IconBtn, Mark, Menu, MenuBtn, Tip, type IconName } from '../design/ui.tsx'
import { go, goInvestigation, goScan, usePlace, type Page } from '../lib/place.ts'
import { openSeen, started, statusOf, useSeen } from '../lib/pending.ts'
import { useTheme, type Theme } from './theme.ts'
import { useUi } from './store.ts'

const NAV: { page: Exclude<Page, 'building' | 'investigation'>; label: string; icon: IconName; key: string; also?: Page }[] = [
  { page: 'home', label: 'Home', icon: 'home', key: 'H' },
  { page: 'explore', label: 'Explore', icon: 'map', key: 'E', also: 'building' },
  { page: 'investigations', label: 'Investigations', icon: 'runs', key: 'I', also: 'investigation' },
  { page: 'buildings', label: 'Buildings', icon: 'keep', key: 'B' },
  { page: 'insights', label: 'Insights', icon: 'chart', key: 'N' },
  { page: 'tools', label: 'Tools', icon: 'tool', key: 'T' },
]
export const PAGE_KEYS: Record<string, (typeof NAV)[number]['page'] | 'settings'> = { h: 'home', e: 'explore', i: 'investigations', b: 'buildings', n: 'insights', t: 'tools', s: 'settings' }
const THEMES: { id: Theme; label: string; icon: IconName }[] = [{ id: 'system', label: 'Match the system', icon: 'monitor' }, { id: 'light', label: 'Light', icon: 'sun' }, { id: 'dark', label: 'Dark', icon: 'moon' }]

/** Start a new investigation: the old one stays in the list. */
export const newInvestigation = () => { startOver(); go('home') }

export function Sidebar({ onPick }: { onPick?: () => void }) {
  const { page } = usePlace()
  const rail = useUi((s) => s.rail) && !onPick
  const doc = useWorkspace((s) => s.doc)
  const seen = useSeen((s) => s.all)
  const live = useCatalog((s) => s.live)
  const shared = useCatalog((s) => !!s.shared) // a read-only link pairs no phone: there is nothing it may send to
  const count = useBuildings((s) => s.all.length)
  const { theme, setTheme } = useTheme()
  const running = doc.runs.filter((r) => r.status === 'running').length
  const recent = Object.values(seen).filter((s) => s.id !== doc.id).sort((a, b) => b.last - a.last).slice(0, 5)
  const pick = (fn: () => void) => () => { fn(); onPick?.() }
  const badge = (p: Page) => (p === 'buildings' ? doc.shortlist.length : p === 'tools' ? doc.tools.length : p === 'investigations' ? running : 0)
  const title = doc.brief?.text ?? (started(doc) ? 'Untitled investigation' : 'No investigation open')

  return (
    <nav className="side" data-rail={rail || undefined} aria-label="Main">
      <MenuBtn trigger={
        <button type="button" className="ws" aria-label={`Investigation: ${title}. Switch or start a new one.`}>
          <span className="mk"><Mark /></span>
          <span className="grow"><b>Cranley</b><span className="trunc">{title}</span></span>
          <Icon name="updown" size={13} />
        </button>}>
        <div className="mh">Current investigation</div>
        <Menu.Item onClick={pick(() => goInvestigation(doc.id))} disabled={!started(doc)}><Icon name="runs" /><span className="trunc" style={{ maxWidth: 240 }}>{title}</span><small>{started(doc) ? statusOf(doc) : ''}</small></Menu.Item>
        {recent.length > 0 && <><hr /><div className="mh">Recent in this browser</div></>}
        {recent.map((s) => <Menu.Item key={s.id} onClick={() => openSeen(s.id)}><Icon name="clock" /><span className="trunc" style={{ maxWidth: 240 }}>{s.brief || 'Untitled investigation'}</span></Menu.Item>)}
        <hr />
        <Menu.Item onClick={pick(newInvestigation)}><Icon name="plus" />New investigation</Menu.Item>
        <Menu.Item onClick={pick(() => go('investigations'))}><Icon name="table" />All investigations</Menu.Item>
      </MenuBtn>

      <ul className="nav">
        {NAV.map((n) => {
          const on = page === n.page || page === n.also, b = badge(n.page)
          const item = (
            <button type="button" aria-current={on ? 'page' : undefined} onClick={pick(() => go(n.page))} aria-label={rail ? n.label : undefined}>
              <Icon name={n.icon} size={16} /><span className="grow">{n.label}</span>
              {b > 0 && <span className="count">{n.page === 'investigations' ? `${b} running` : b}</span>}
            </button>
          )
          return <li key={n.page}>{rail ? <Tip label={n.label} kbd={`G ${n.key}`}>{item}</Tip> : item}</li>
        })}
      </ul>

      {!rail && doc.shortlist.length > 0 && (
        <div className="group">
          <h2>Saved buildings</h2>
          <ul className="nav">
            {doc.shortlist.slice(0, 6).map((s) => <li key={s.sid}><button type="button" onClick={pick(() => goScan(s.sid))}><Icon name="building" size={15} /><span className="grow trunc">{s.name}</span></button></li>)}
          </ul>
        </div>
      )}

      <div className="foot">
        {!rail && (
          <p className="conn" data-live={live === true || undefined}>
            <i aria-hidden="true" />
            <span>{live == null ? 'Connecting to the agent server' : live ? 'Agent server connected' : 'No agent server: scripted playback'}</span>
          </p>
        )}
        {!rail && count > 0 && <p className="conn muted"><span>{new Intl.NumberFormat('en').format(count)} scanned addresses</span></p>}
        <ul className="nav">
          {/* pairing a phone is part of the work, not a developer's tab: the code opens from here */}
          {!shared && <li>{(() => { const b = <button type="button" onClick={() => window.dispatchEvent(new Event('threshold:phone'))} aria-label={rail ? 'Continue on a phone' : undefined}><Icon name="camera" size={16} /><span className="grow">Continue on a phone</span></button>; return rail ? <Tip label="Continue on a phone">{b}</Tip> : b })()}</li>}
          <li>{(() => { const b = <button type="button" aria-current={page === 'settings' ? 'page' : undefined} onClick={pick(() => go('settings'))} aria-label={rail ? 'Settings' : undefined}><Icon name="gear" size={16} /><span className="grow">Settings</span></button>; return rail ? <Tip label="Settings" kbd="G S">{b}</Tip> : b })()}</li>
        </ul>
        <div className="acct">
          <MenuBtn side="top" trigger={
            <button type="button" className="who" aria-label="Account and appearance">
              <span className="av" aria-hidden="true"><Icon name="user" size={16} /></span>
              <span className="grow"><b>This browser</b><span>No sign-in yet</span></span>
            </button>}>
            <div className="mh">Appearance</div>
            <Menu.RadioGroup value={theme} onValueChange={(v) => setTheme(v as Theme)}>
              {THEMES.map((t) => <Menu.RadioItem key={t.id} value={t.id} closeOnClick={false}><span className="mi-check"><Menu.RadioItemIndicator><Icon name="check" size={12} /></Menu.RadioItemIndicator></span>{t.label}</Menu.RadioItem>)}
            </Menu.RadioGroup>
            <hr />
            <Menu.Item onClick={() => useUi.setState({ keys: true })}><Icon name="help" />Keyboard shortcuts<small>?</small></Menu.Item>
            <Menu.Item onClick={pick(() => go('settings'))}><Icon name="gear" />Settings</Menu.Item>
          </MenuBtn>
          {!onPick && <IconBtn icon="panel" label={rail ? 'Widen the sidebar' : 'Narrow the sidebar'} kbd="[" onClick={() => useUi.getState().setRail(!rail)} />}
        </div>
      </div>
    </nav>
  )
}
