// What is hovered and selected, shared by the dollhouse, the floor plan and the panorama so they follow each other.
// shortcut: one store per page, so two BuildingScenes side by side share hover; make it per instance when compare lands.
import { create } from 'zustand'
import type { Pick } from './types.ts'

interface SceneLink { hover: Pick | null; selected: Pick | null; setHover: (p: Pick | null) => void; setSelected: (p: Pick | null) => void }
const same = (a: Pick | null, b: Pick | null) => a?.kind === b?.kind && a?.id === b?.id

export const useSceneLink = create<SceneLink>((set, get) => ({
  hover: null, selected: null,
  setHover: (p) => { if (!same(p, get().hover)) set({ hover: p }) },
  setSelected: (p) => { if (!same(p, get().selected)) set({ selected: p }) },
}))
