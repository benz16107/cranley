import type { Block, Doc, Op, Panel, Question, Source, Status, ToolRef } from './types.ts'

/* The agent server's side of the workspace. The server owns the document (docs/contracts/workspace.md): blocks name
   runs and findings by id, runs carry their ToolResult. The shell renders its own Doc, with the numbers already in
   each block. toDoc() is the one place that reads the server's shape; nothing here computes or rewrites a number.
   shortcut: after each server event the whole document is fetched again instead of applying ops in a second reducer;
   upgrade to an op reducer if a turn ever streams more than a few events a second. */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type J = Record<string, any> // server JSON, read defensively
export type Manifest = { id: string; title: string; summary: string; status: 'ready' | 'planned'; inputs: { properties?: Record<string, J>; required?: string[] } }
export type Names = (sid: string) => { name: string; address: string } | undefined

const WORST: Record<Status, number> = { fail: 0, warn: 1, unknown: 2, pass: 3 }
const SRC: Source = { layer: 'matterport', method: 'geometry', confidence: 'medium' }
const shown = (v: unknown) => (v === true ? 'Yes' : v === false ? 'No' : (v as string | number))
export const typeOf = (input: J) => input.type ?? input.anyOf?.find((a: J) => a.type && a.type !== 'null')?.type
const placeLabel = (p: J | null | undefined) => (p?.address ?? (p?.property_id ? `Property ${p.property_id}` : p?.geo ? 'A point on the map' : ''))

export function toQuestion(q: J): Question {
  const input = q.input ?? {}, type = typeOf(input)
  const hint = !q.answered && q.answer != null ? q.answer : input.default
  return {
    id: q.id, text: q.text, pref: q.key, tool: q.tools?.[0], unit: input['x-unit'],
    kind: input.enum || type === 'boolean' ? 'choice' : type === 'number' || type === 'integer' ? 'number' : 'text',
    options: input.enum ?? (type === 'boolean' ? ['Yes', 'No'] : undefined),
    answer: q.answered ? shown(q.answer) : undefined, hint: hint != null && typeof hint !== 'object' ? shown(hint) : undefined,
  }
}

function toBlocks(p: J, runs: Map<string, J>, ws: J, names: Names): Block[] {
  const out: Block[] = []
  const pick = (all: J[] | undefined, ids: string[]) => ids.map((id) => all?.find((m) => m.id === id)).filter((m): m is J => !!m)
  for (const b of (p.blocks ?? []) as J[]) {
    const run = runs.get(b.run ?? p.run), res = run?.result
    switch (b.type) {
      case 'VerdictHeader':
        if (res) out.push({ type: b.type, status: res.verdict.status, text: res.verdict.text })
        else if (run?.error) out.push({ type: b.type, status: 'unknown', text: run.error })
        break
      case 'MetricRow': { const ms = pick(res?.metrics, b.metrics ?? []); if (ms.length) out.push({ type: b.type, metrics: ms as never }); break }
      case 'CheckList': {
        const cs = ((res?.checks ?? []) as J[]).filter((c) => (!b.checks || b.checks.includes(c.id)) && (!b.status || b.status.includes(c.status)))
          .sort((x, y) => WORST[x.status as Status] - WORST[y.status as Status]).map((c) => ({ ...c, findings: c.findings ?? [] }))
        if (cs.length) out.push({ type: b.type, checks: cs as never })
        break
      }
      case 'EvidenceStrip': out.push({ type: b.type, findings: b.findings ?? [] }); break
      case 'RankedTable': {
        const rows = ((b.rows ?? []) as string[]).map((id) => runs.get(id)).filter((r): r is J => !!r?.result)
        const metric = (r: J, id: string) => (r.result.metrics as J[] | undefined)?.find((m) => m.id === id)
        if (rows.length) out.push({ type: b.type, source: rows[0].result.metrics?.[0]?.source ?? SRC,
          columns: (b.columns as J[]).map((c) => ({ id: c.metric, label: c.label, unit: metric(rows[0], c.metric)?.unit || undefined, better: c.better })),
          rows: rows.map((r) => ({ id: r.id, label: (r.sid && names(r.sid)?.name) || r.sid || placeLabel(r.place), status: r.result.verdict.status,
            anchor: r.sid ? { sid: r.sid, point: [0, 0, 0] } : undefined, values: Object.fromEntries((b.columns as J[]).map((c) => [c.metric, metric(r, c.metric)?.value ?? null])) })) })
        break
      }
      case 'MiniChart': {
        const ms = pick(res?.metrics, b.metrics ?? []).filter((m) => m.value != null)
        if (ms.length) out.push({ type: b.type, title: b.title, unit: ms[0].unit, source: ms[0].source, bars: ms.map((m) => ({ label: m.label, value: m.value })) })
        break
      }
      case 'FloorPlanMini': out.push({ type: b.type, sid: b.sid }); break
      case 'Controls': {
        const controls = ((b.controls ?? []) as J[]).map((c) => {
          const v = run?.inputs?.[c.input] ?? ws.prefs?.[c.pref]?.value
          return { id: c.pref ?? `input:${b.tool}:${c.input}`, label: c.label, kind: c.kind, min: c.min ?? undefined, max: c.max ?? undefined, step: c.step ?? undefined, unit: c.unit ?? undefined, options: c.options ?? undefined,
            value: c.kind === 'toggle' ? !!v : c.kind === 'slider' ? (typeof v === 'number' ? v : c.min ?? 0) : String(v ?? c.options?.[0] ?? '') }
        })
        if (controls.length) out.push({ type: b.type, controls })
        break
      }
      case 'AssumptionChips': {
        const as = ((res?.assumptions ?? []) as J[]).filter((a) => a.value != null).map((a) => ({ id: a.id, label: a.label, value: a.value, unit: a.unit ?? undefined, editable: !!a.editable }))
        if (as.length) out.push({ type: b.type, assumptions: as })
        break
      }
      case 'StepLog': if (run?.steps?.length) out.push({ type: b.type, steps: (run.steps as string[]).map((label, i) => ({ id: String(i), label })) }); break
      case 'Note': out.push({ type: b.type, text: b.text }); break
      case 'ActionBar': if (res?.actions?.length) out.push({ type: b.type, actions: res.actions }); break
    }
  }
  return out
}

/** The server's workspace document as the shell's Doc. `camera` is passed through: where the person looks is theirs. */
export function toDoc(ws: J, learned: J[], manifests: Map<string, Manifest>, names: Names, camera: Doc['camera'] = null): Doc {
  const runs = new Map<string, J>(((ws.runs ?? []) as J[]).map((r) => [r.id, r]))
  const title = (id: string) => manifests.get(id)?.title ?? id
  return {
    id: ws.id,
    brief: ws.brief?.text ? { text: ws.brief.text, facts: [], limits: ws.brief.limits ?? [] } : null,
    questions: ((ws.questions ?? []) as J[]).map(toQuestion),
    tools: ((ws.tools ?? []) as J[]).filter((t) => t.enabled !== false).map((t): ToolRef => ({ id: t.id, title: title(t.id), summary: manifests.get(t.id)?.summary, reason: t.reason ?? '',
      coverage: t.status === 'planned' ? 'Planned, not built yet' : undefined, by: t.by === 'user' ? 'user' : 'agent' })),
    runs: ((ws.runs ?? []) as J[]).map((r) => ({ id: r.id, tool: r.tool, step: r.plan_step ?? undefined, stale: !!r.stale, sid: r.sid ?? undefined, place: r.place ?? undefined,
      label: [title(r.tool), r.sid ? names(r.sid)?.name ?? r.sid : placeLabel(r.place)].filter(Boolean).join(' · '),
      status: r.status === 'running' ? 'running' : r.status === 'error' ? 'failed' : 'done',
      ms: r.started && r.finished ? (r.finished - r.started) * 1000 : undefined,
      summary: (r.error ?? (r.status === 'running' ? r.steps?.at(-1) : r.summary)) || undefined })),
    findings: ((ws.findings ?? []) as J[]).filter((f) => !f.superseded_by && f.feedback?.verdict !== 'rejected').map((f) => ({ ...f, tool: f.tool ?? '', run: f.run ?? undefined, media: f.media ?? [] })) as Doc['findings'],
    layers: [],
    overlays: ((ws.overlays ?? []) as J[]).filter((o) => o.visible !== false).map((o) => ({ id: o.id, tool: o.tool ?? '', sid: o.sid ?? undefined, overlay: o.overlay })),
    panels: ((ws.panels ?? []) as J[]).map((p): Panel => {
      const sid = runs.get(p.run)?.sid ?? (p.blocks as J[] | undefined)?.find((b) => b.type === 'FloorPlanMini')?.sid
      const id = String(p.id)
      const role = id === 'agent:summary' ? 'summary' : id === 'agent:ranked' || id.startsWith('compare:') ? 'ranking' : id.startsWith('agent:') || id.startsWith('custom:') ? 'note' : 'tool'
      return { id: p.id, tool: p.tool ?? 'agent', title: p.title, scope: sid ? names(sid)?.name : undefined, sid: sid ?? undefined, run: p.run ?? undefined, role, blocks: toBlocks(p, runs, ws, names) }
    }),
    plan: ((ws.plan ?? []) as J[]).map((s) => ({ id: s.id, label: s.text, status: s.status === 'completed' ? 'done' : s.status === 'in_progress' ? 'active' : 'pending' })),
    prefs: learned.map((l) => ({ key: l.key, label: l.text, value: '', from: l.by === 'user' ? 'You set this' : 'Learned from what you did', by: l.by === 'agent' ? 'agent' : 'user', at: (l.at ?? 0) * 1000 })),
    shortlist: ((ws.shortlist ?? []) as J[]).map((s) => ({ sid: s.sid, name: names(s.sid)?.name ?? s.sid, address: names(s.sid)?.address ?? '', note: s.note || undefined })),
    camera, log: [],
  }
}

/** A shell user op in the server's vocabulary. Null when the op stays in the browser (where the person looks). */
export function toServerOp(op: Op, ws: J | null): J | null {
  switch (op.op) {
    case 'question.answer': {
      const type = typeOf((ws?.questions as J[] | undefined)?.find((q) => q.id === op.id)?.input ?? {})
      return { op: op.op, id: op.id, value: type === 'boolean' ? op.answer === 'Yes' : type === 'integer' ? Math.round(Number(op.answer)) : type === 'number' ? Number(op.answer) : op.answer }
    }
    case 'tool.enable': return { op: op.op, tool: op.tool.id, reason: op.tool.reason }
    case 'tool.disable': return { op: op.op, tool: op.id }
    case 'pref.set': return op.key.startsWith('input:') ? null : { op: op.op, key: op.key, value: op.value, reason: op.from ?? '' }
    case 'shortlist.add': return { op: op.op, sid: op.item.sid, note: op.item.note ?? '' }
    case 'shortlist.remove': return { op: op.op, sid: op.sid }
    default: return null
  }
}
