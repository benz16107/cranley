/* The whole surface a skin may use. A skin imports from this file and from nowhere else in core, and never from
   src/scene or another skin. README.md beside this file explains each part. When a skin needs something that is
   not here, it says so in its report and the integrator adds it. */

// ---- the workspace: the one document every look renders, and the one way to change it
export { useWorkspace, dispatch, userOp } from './store.ts'
export type {
  Doc, Op, OpInput, OpName, By, Brief, Question, ToolRef, Run, Panel, PlanStep, Pref, ShortlistItem, Layer,
  Block, BlockType, ToolResult, Metric, Check, Finding, Media, Assumption, Action, Source, Status, Anchor, Overlay,
  ScanPlan, Pt,
} from './types.ts'

// ---- the agent: compose, investigate, ask, run a tool. The server when it answers, scripted playback when not.
export { compose, investigate, ask, runToolHere, runTool, runAction, startOver, answerPref } from './agent.ts'
export { useCatalog, isLive, share as shareWorkspace, type Shared } from './server.ts'
export { useToolCatalog, type CatalogTool } from './tools.ts'
export { NEEDS, TOOLS, type Need } from './fixtures/catalog.ts'
export { onNotice, type Notice } from './notices.ts'

// ---- places: the URL is the state of the view
export { navigate, setQuery, useRoute, currentRoute, type Route } from './router.ts'
export { LOOKS, decodeSegment, type LookId } from './looks.ts'
export type { SwitcherPlace } from './switcher.ts'

// ---- buildings and the city map
export {
  useBuildings, CITIES, KINDS, ROOMS_MAX, search, matches, readFilters,
  type Building, type Scan, type Kind, type CityId, type Filters,
} from './buildings.ts'
export { useMapModel, geoMarks, nearestBuilding, type GeoMarks } from './place.ts'
export { Map as MapLibre, Marker } from './maplibre.ts'
export { mapStyle, type MapPalette } from './basemap.ts'

// ---- one building: the plan, panorama images, and the bridge to the shared 3D scene
export {
  fetchPlan, panoFace, panoEquirect, captureImage, floorplanImage, orthoImage, fetchScans, fetchRecord, fetchDrone, droneImage,
  fetchMeasureFields, searchMeasures, type ScanRow, type MeasureField, type MeasureHit,
  fetchFloodWet, fetchFactHistory, fetchCaptures, type FloodLevel, type FactRow, type Capture,
} from './api.ts'
export {
  Scene, SceneBoundary, useBuildingView, focusFinding, focusAnchor, anchorFloor,
  type SceneMode, type SceneView, type SceneProps, type SceneCamera, type SceneState,
} from './scene.tsx'
