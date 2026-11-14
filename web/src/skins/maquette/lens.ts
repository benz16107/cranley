import type { Doc, Overlay } from '../../core/index.ts'

/** The sheet on top is a lens: only its tool's marks are laid on the model. Core hands the scene every tool's
    overlays for a scan at once, without their tool (core-requests.md, Maquette 1), so the same objects are picked by
    walking the document in core's order. If the two lists ever disagree, everything is shown, as core would. */
export function lensOverlays<T>(doc: Doc, sid: string, tool: string | undefined, all: T[]): T[] {
  if (!tool) return all
  const out: T[] = []
  let i = 0
  for (const o of doc.overlays) {
    if (o.sid && o.sid !== sid) continue
    const v: Overlay = o.overlay
    if ((v.kind === 'route' && v.floor === 'geo') || (v.kind === 'pins' && v.pins.every((p) => 'geo' in p.anchor))) continue
    if (o.tool === tool && all[i]) out.push(all[i])
    i++
  }
  return i === all.length ? out : all
}
