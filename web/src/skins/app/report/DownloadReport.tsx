import { useState } from 'react'
import { toast } from 'sonner'
import { Icon, Menu, MenuBtn } from '../design/ui.tsx'

/** Report kinds the server prints (server/threshold/report KINDS). No kind: every tool this investigation ran. */
const KINDS = [
  { id: '', label: 'Everything in this investigation' },
  { id: 'accessibility', label: 'Accessibility audit' },
  { id: 'fire', label: 'Fire safety pre-plan' },
  { id: 'fitout', label: 'Fit-out and occupancy' },
] as const

export function reportUrl(workspace: string, opts: { kind?: string; sid?: string; format?: 'pdf' | 'html' } = {}) {
  const q = new URLSearchParams()
  if (opts.kind) q.set('kind', opts.kind)
  if (opts.sid) q.set('sid', opts.sid)
  const s = q.toString()
  return `/api/report/${encodeURIComponent(workspace)}.${opts.format ?? 'pdf'}${s ? `?${s}` : ''}`
}

async function save(url: string, name: string) {
  const r = await fetch(url)
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `The server answered ${r.status}`)
  const blob = await r.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000)
}

/** "Download report": the investigation (or one building of it) as the PDF a business keeps. */
export function DownloadReport({ workspace, sid, name, disabled }: { workspace: string; sid?: string; name?: string; disabled?: boolean }) {
  const [busy, setBusy] = useState(false)
  const run = (kind: string, label: string) => {
    setBusy(true)
    const base = (name || 'Cranley').replace(/[^\w ]+/g, '').trim() || 'Cranley'
    const file = `${base.toLowerCase().includes(label.toLowerCase()) ? base : `${base} ${label}`}.pdf`
    toast.promise(save(reportUrl(workspace, { kind, sid }), file).finally(() => setBusy(false)), {
      loading: `Printing the ${label.toLowerCase()}`,
      success: `Saved ${file}`,
      error: (e: Error) => ({ message: 'The report was not printed', description: e.message }),
    })
  }
  return (
    <MenuBtn align="end" trigger={
      <button type="button" className="btn" disabled={!workspace || busy || disabled} title={disabled ? 'Run a tool first: the report is made of its findings' : 'A PDF of the findings, the plan and what was not checked'}>
        <Icon name="record" size={14} />{busy ? 'Printing…' : 'Download report'}
      </button>
    }>
      <div className="mh">PDF report{sid ? ' of this building' : ''}</div>
      {KINDS.map((k) => <Menu.Item key={k.id} onClick={() => run(k.id, k.id ? k.label : 'Site report')}>{k.label}</Menu.Item>)}
      <hr />
      <Menu.Item onClick={() => window.open(reportUrl(workspace, { sid, format: 'html' }), '_blank', 'noopener')}><Icon name="external" />Open as a web page</Menu.Item>
    </MenuBtn>
  )
}
