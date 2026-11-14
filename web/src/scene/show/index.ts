// The engine's one handle on whatever is playing on the building (View.show). At most one show at a time.
import * as THREE from 'three'
import type { LabelSpec } from '../engine/labels.ts'
import { FireShow } from './fire.ts'
import { FloodShow } from './flood.ts'
import { TourShow } from './tour.ts'
import type { Player, ShowCtx, ShowSpec } from './types.ts'

export type { ShowSpec, ShowState, TourStop } from './types.ts'
export type { ShowCtx } from './types.ts'

export class Shows {
  group = new THREE.Group()
  private player: Player | null = null
  private kind: ShowSpec['kind'] | null = null
  private w = 1; private h = 1

  private ctx: ShowCtx; private onKind: () => void
  /** `onKind` is called when a show starts or ends, so the engine can lay out overlays and labels again. */
  constructor(ctx: ShowCtx, onKind: () => void) { this.ctx = ctx; this.onKind = onKind }

  get labels(): LabelSpec[] { return this.player?.labels ?? [] }
  get ownsWater() { return !!this.player?.ownsWater }
  get active() { return this.kind }

  set(spec: ShowSpec | null | undefined) {
    const kind = spec?.kind ?? null
    if (kind !== this.kind) {
      if (this.player) { if (this.player.group) this.group.remove(this.player.group); this.player.dispose() }
      this.kind = kind
      this.player = kind === 'flood' ? new FloodShow(this.ctx) : kind === 'fire' ? new FireShow(this.ctx) : kind === 'tour' ? new TourShow(this.ctx) : null
      if (this.player?.group) this.group.add(this.player.group)
      this.player?.setSize?.(this.w, this.h)
      this.onKind()
    }
    if (spec) this.player?.set(spec)
  }

  update(dt: number) { return this.player?.update(dt) ?? false }
  setSize(w: number, h: number) { this.w = w; this.h = h; this.player?.setSize?.(w, h) }
  touched() { this.player?.touched?.() }
  dispose() { this.player?.dispose(); this.player = null }
}
