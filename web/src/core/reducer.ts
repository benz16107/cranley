import type { Block, BlockType, Doc, Op, Panel } from './types.ts'

export const emptyDoc = (id = 'local'): Doc => ({
  id, brief: null, questions: [], tools: [], runs: [], findings: [], layers: [], overlays: [], panels: [],
  plan: [], prefs: [], shortlist: [], camera: null, log: [],
})

const BLOCKS: ReadonlySet<BlockType> = new Set([
  'VerdictHeader', 'MetricRow', 'CheckList', 'EvidenceStrip', 'RankedTable', 'MiniChart', 'FloorPlanMini',
  'Controls', 'AssumptionChips', 'StepLog', 'Note', 'ActionBar',
])
const NOTE_MAX = 400

/** Agent output is cleaned, not trusted: unknown blocks are dropped, a metric row holds at most four, notes are capped. */
function cleanPanel(p: Panel): Panel {
  const blocks = (p.blocks ?? []).filter((b): b is Block => BLOCKS.has(b?.type)).map((b) => {
    if (b.type === 'MetricRow') return { ...b, metrics: b.metrics.slice(0, 4) }
    if (b.type === 'Note') return { ...b, text: b.text.slice(0, NOTE_MAX) }
    return b
  })
  return { ...p, blocks }
}

/** Replace the item with the same key, in place, or append. New things never reorder what is already there. */
function upsert<T>(list: T[], item: T, key: (t: T) => unknown): T[] {
  const i = list.findIndex((t) => key(t) === key(item))
  return i < 0 ? [...list, item] : list.map((t, j) => (j === i ? item : t))
}

/** The one reducer. Agent ops from the stream and user ops from the interface both pass through here. */
export function apply(doc: Doc, op: Op): Doc {
  const d = { ...doc, log: [...doc.log, op] }
  switch (op.op) {
    case 'brief.set': return { ...d, brief: op.brief }
    case 'question.ask': return { ...d, questions: upsert(d.questions, op.question, (q) => q.id) }
    case 'question.answer': return { ...d, questions: d.questions.map((q) => (q.id === op.id ? { ...q, answer: op.answer } : q)) }
    case 'tool.enable': return { ...d, tools: upsert(d.tools, { ...op.tool, by: op.by }, (t) => t.id) }
    case 'tool.disable': return {
      ...d,
      tools: d.tools.filter((t) => t.id !== op.id),
      panels: d.panels.filter((p) => p.tool !== op.id),
      overlays: d.overlays.filter((o) => o.tool !== op.id),
      layers: d.layers.filter((l) => l.tool !== op.id),
    }
    case 'run.start': return { ...d, runs: upsert(d.runs, { id: op.id, tool: op.tool, label: op.label, step: op.step, sid: op.sid, status: 'running' as const }, (r) => r.id) }
    case 'run.finish': return { ...d, runs: d.runs.map((r) => (r.id === op.id ? { ...r, status: op.status ?? 'done', ms: op.ms, summary: op.summary } : r)) }
    case 'finding.add': return { ...d, findings: upsert(d.findings, { ...op.finding, tool: op.tool, run: op.run }, (f) => f.id) }
    case 'layer.upsert': return { ...d, layers: upsert(d.layers, op.layer, (l) => l.id) }
    case 'overlay.upsert': {
      const rest = d.overlays.filter((o) => o.id !== op.id)
      if (!op.overlay) return { ...d, overlays: rest }
      return { ...d, overlays: upsert(d.overlays, { id: op.id, tool: op.tool, sid: op.sid, overlay: op.overlay }, (o) => o.id) }
    }
    case 'panel.upsert': return { ...d, panels: upsert(d.panels, cleanPanel(op.panel), (p) => p.id) }
    case 'camera.focus': return { ...d, camera: { anchor: op.anchor, finding: op.finding, by: op.by, stay: op.stay } }
    case 'plan.set': return { ...d, plan: op.steps }
    case 'pref.set': {
      const old = d.prefs.find((p) => p.key === op.key)
      const rest = d.prefs.filter((p) => p.key !== op.key)
      if (op.value === null) return { ...d, prefs: rest, runs: staleRuns(d) }
      const pref = { key: op.key, label: op.label ?? old?.label ?? op.key, value: op.value, unit: op.unit ?? old?.unit,
        from: op.from ?? old?.from ?? '', prev: old?.value, by: op.by, at: op.at ?? 0 }
      return { ...d, prefs: upsert(d.prefs, pref, (p) => p.key), runs: staleRuns(d) }
    }
    case 'shortlist.add': return { ...d, shortlist: upsert(d.shortlist, op.item, (s) => s.sid) }
    case 'shortlist.remove': return { ...d, shortlist: d.shortlist.filter((s) => s.sid !== op.sid) }
    default: return doc // an op this build does not know is ignored, not an error
  }
}

/** A changed preference makes finished results stale until their tool runs again. */
const staleRuns = (d: Doc) => d.runs.map((r) => (r.status === 'done' ? { ...r, stale: true } : r))

/** The op that takes `doc` back to how it was before `op`, in the same vocabulary. Null when there is none. */
export function inverse(before: Doc, op: Op): Op | null {
  const by = 'user' as const
  switch (op.op) {
    case 'brief.set': return before.brief ? { op: 'brief.set', by, brief: before.brief } : null
    case 'tool.enable': return before.tools.some((t) => t.id === op.tool.id) ? null : { op: 'tool.disable', by, id: op.tool.id }
    case 'tool.disable': { const t = before.tools.find((x) => x.id === op.id); return t ? { op: 'tool.enable', by, tool: t } : null }
    case 'pref.set': { const p = before.prefs.find((x) => x.key === op.key); return { op: 'pref.set', by, key: op.key, label: p?.label, value: p?.value ?? null, unit: p?.unit, from: p?.from } }
    case 'shortlist.add': return before.shortlist.some((s) => s.sid === op.item.sid) ? null : { op: 'shortlist.remove', by, sid: op.item.sid }
    case 'shortlist.remove': { const s = before.shortlist.find((x) => x.sid === op.sid); return s ? { op: 'shortlist.add', by, item: s } : null }
    case 'camera.focus': return before.camera ? { op: 'camera.focus', by, anchor: before.camera.anchor, finding: before.camera.finding } : null
    default: return null
  }
}
