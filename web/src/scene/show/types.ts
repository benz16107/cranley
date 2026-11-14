// A "show" is something played on the building over time: a real storm's water, a modelled fire's smoke, or a
// camera tour of findings. The scene plays it; a look drives it through View.show and reads ShowState back.
import type * as THREE from 'three'
import type { Model } from '../model.ts'
import type { Tokens } from '../tokens.ts'
import type { Anchor, Status, View } from '../types.ts'
import type { Dollhouse } from '../engine/dollhouse.ts'
import type { LabelSpec } from '../engine/labels.ts'
import type { Rig } from '../engine/rig.ts'

/** One stop of a tour: where to look and the one line to say. `line` is a finding's own words, never written here. */
export interface TourStop { id: string; title: string; line: string; status: Status; anchor: Anchor | null }

export interface ShowSpec {
  kind: 'flood' | 'fire' | 'tour'
  playing: boolean
  /** Change `n` to jump to `step`. */
  seek?: { n: number; step: number } | null
  /** Fire: the Smoke clock's run with bedroom doors open (the default) or closed. */
  doors?: 'open' | 'closed'
  /** Tour: the stops, in order. */
  stops?: TourStop[]
  /** Tour: read each line aloud with the browser's speech synthesis (the default). */
  voice?: boolean
}

export interface SourceLine { what: string; confidence: string; text: string }
export interface LossItem { id: string; name: string; room_label: string; height_m: number; wet_at: number; cost_class: string | null; fixture: boolean; utility: boolean }
export interface SmokeRow { id: string; label: string; fire: boolean; layer_m: number; ceiling_m: number | null; upper_c: number; untenable_s: number | null; cause: string | null; lost: boolean }

export interface ShowState {
  kind: ShowSpec['kind']
  status: 'loading' | 'ready' | 'missing'
  /** Why it cannot play here, in the server's words. */
  reason?: string
  playing: boolean
  step: number; steps: number
  /** Where the playhead is, for a readout: a date and hour, minutes after ignition, or "3 of 6". */
  clock: string
  title: string
  sources: SourceLine[]
  flood?: { outside_m: number; inside_m: number; rooms_wet: number; items: LossItem[]; wet: number; loss_usd: [number, number] | null; list: 'loading' | 'ready' | 'none'; listNote: string }
  fire?: { rooms: SmokeRow[]; doors: 'open' | 'closed'; end: string }
  tour?: { i: number; n: number; title: string; line: string; status: Status; speaking: boolean }
}

/** What a player gets from the engine. */
export interface ShowCtx {
  api: string; sid: string; model: Model; tokens: Tokens; rig: Rig; doll: Dollhouse
  view: () => View
  /** Change the view as a person would (mode, floor, cut, focus): it goes through the look, so its controls follow. */
  setView: (patch: Partial<View>) => void
  emit: (s: ShowState) => void
  /** The player's labels, or whether it draws the water, changed: lay the overlays and labels out again. */
  relabel: () => void
  invalidate: () => void
  /** The building's whole-view pose, for a tour's opening and closing shots. */
  home: () => { target: THREE.Vector3; az: number; pol: number; dist: number; fov: number }
  aerial: () => boolean
}

export interface Player {
  group: THREE.Object3D | null
  labels: LabelSpec[]
  /** The show draws the water itself: a water overlay from a tool is held back while it plays. */
  ownsWater?: boolean
  set(spec: ShowSpec): void
  /** Advance. Returns true while a frame should be drawn. */
  update(dt: number): boolean
  setSize?(w: number, h: number): void
  /** The person took the camera: a tour pauses. */
  touched?(): void
  dispose(): void
}

export const fetchJson = <T,>(url: string): Promise<T> => fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${url} ${r.status}`))))
