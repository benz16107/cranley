/* Every type a look renders, in one file: Contracts 1, 3, 4 and 5 of docs/ARCHITECTURE.md plus the panel block
   catalog, in the form the web app shows them (blocks carry their data; serverDoc.ts fills them from the
   server's document, whose blocks name runs and findings by id). */

export type Status = 'pass' | 'warn' | 'fail' | 'unknown'

/* ---------- Contract 1: ScanPlan (the fields the shell uses) ---------- */
export type Pt = [number, number]
export type ScanPlan = {
  schema: string; sid: string; name: string; address: string; city: string; segment: string
  /** Where the scan is on the map. `yaw_deg` turns the scan frame onto east/north, counter-clockwise (settled on 40
      houses). `fit` is the per-scan check against the building footprint; trust a map position only when
      `quality.georef` is true (it is false for a unit inside a larger building, where the check cannot run). */
  geo: { lat: number; lon: number; yaw_deg: number; fit?: { rotation_deg: number; shift_m: number; iou: number; verified: boolean } | null } | null
  /** What the scan can answer. `walls_source: 'dxf'` means the walls were recovered from the drawing, not measured. */
  quality?: { walls: boolean; polygons: boolean; openings: boolean; labels: boolean; georef: boolean; walls_source?: string; walls_confidence?: string; notes?: string[] }
  has: { splat: boolean; defurnished: boolean; room_labels: boolean; openings: boolean }
  floors: { id: string; label: string; sequence: number }[]
  walls: { id: string; floor: string; a: Pt; b: Pt; type: 'wall' | 'invisible'; thickness: number; rooms: string[]; openings: string[] }[]
  openings: { id: string; wall: string; floor: string; type: 'doorway' | 'window' | 'opening'; width: number; height: number | null; center: Pt; rooms: string[] }[]
  rooms: { id: string; floor: string; label: string | null; polygon: Pt[]; area: number | null; width: number | null; depth: number | null }[]
  panos: { id: string; label: string; position: [number, number, number]; floor: string; room: string | null }[]
}

/* ---------- Contract 3: ToolResult ---------- */
export type Source = {
  /** 'phone': captured by a person on site with the phone app. Methods 'sensor' (tilt, compass, GPS, microphone) and 'manual' (measured and typed in) come with it. */
  layer: 'matterport' | 'vexcel' | 'costar' | 'drone' | 'model' | 'phone'
  method: 'geometry' | 'vision' | 'lookup' | 'simulation' | 'sensor' | 'manual'
  confidence: 'high' | 'medium' | 'low'
  note?: string
}
export type Anchor =
  | { sid: string; point: [number, number, number] }
  | { sid: string; room: string }
  | { sid: string; opening: string }
  | { sid: string; wall: string }
  | { sid: string; pano: string; yaw_deg: number; pitch_deg: number }
  | { geo: [number, number] }
export type Metric = { id: string; label: string; value: number | null; unit: string; source: Source }
export type Check = {
  id: string; rule: string; measured: number | null; threshold: number | null; unit: string; status: Status
  standard?: string | null; findings: string[]
  /** 'claim': `threshold` is what a record or a listing says, not a limit to meet. Missing means 'limit'. */
  kind?: 'limit' | 'claim'
  /** Set when the check was settled on site with the phone after the tool ran: `status` is then the on-site result.
      `scan` is the figure the tool measured from the scan; `measured` says whether `Check.measured` is now the value
      taken on site (true) or still the scan's (false: the site result came without a figure for this place). */
  site?: { scan: number | null; measured: boolean }
}
/** kind 'phone': `ref` is a capture id (or `<id>#<n>` for a video frame); its picture is `captureImage(ref)`. */
export type Media = { kind: 'pano' | 'ortho' | 'drone' | 'phone'; ref: string; box?: [number, number, number, number] | null }
export type Finding = { id: string; title: string; status: Status; detail?: string; anchor: Anchor | null; source: Source; media?: Media[] }
export type Assumption = { id: string; label: string; value: number | string | boolean; unit?: string; editable: boolean; min?: number; max?: number; step?: number }
export type Action = { id: string; label: string; tool?: string; inputs?: Record<string, unknown> }
export type ToolResult = {
  tool: string
  scope: { sid: string } | { address: string } | { sids: string[] }
  verdict: { status: Status; text: string }
  metrics: Metric[]; checks: Check[]; findings: Finding[]; overlays: Overlay[]; assumptions: Assumption[]; actions: Action[]
}

/* ---------- Contract 4: overlays ---------- */
export type Overlay =
  | { kind: 'lens'; values: Record<string, number>; ramp: 'sequential' | 'status'; legend: { title: string; unit: string; min: number; max: number } }
  | { kind: 'rule'; select: { rooms?: string[]; room_labels?: string[]; openings?: string[]; walls?: string[] }; style: 'solid' | 'dim' | 'hide' | 'highlight' | 'pass' | 'warn' | 'fail' }
  | { kind: 'pins'; pins: { id: string; anchor: Anchor; label: string; status: Status }[] }
  | { kind: 'route'; floor: string; points: [number, number, number][]; chokes: { point: [number, number, number]; width: number; status: Status }[]; label: string }
  | { kind: 'water'; level_m: number; datum: 'scan_z' }
  | { kind: 'box'; center: [number, number, number]; size: [number, number, number]; yaw_deg: number; label: string; status: Status }

/* ---------- The panel block catalog (twelve blocks, each built once) ---------- */
export type Block =
  | { type: 'VerdictHeader'; status: Status; text: string }
  | { type: 'MetricRow'; metrics: Metric[] }
  | { type: 'CheckList'; checks: Check[] }
  | { type: 'EvidenceStrip'; findings: string[] }
  | { type: 'RankedTable'; /** what the table is of, when the tool says ("City census by zip code") */ title?: string; columns: { id: string; label: string; unit?: string; better?: 'higher' | 'lower' }[]; rows: { id: string; label: string; anchor?: Anchor; status?: Status; values: Record<string, number | null> }[]; source: Source }
  | { type: 'MiniChart'; title: string; unit: string; bars: { label: string; value: number; status?: Status }[]; mark?: { value: number; label: string }; source: Source }
  | { type: 'FloorPlanMini'; sid: string }
  | { type: 'Controls'; controls: { id: string; label: string; kind: 'slider' | 'toggle' | 'select'; value: number | boolean | string; min?: number; max?: number; step?: number; unit?: string; options?: string[] }[] }
  | { type: 'AssumptionChips'; assumptions: Assumption[] }
  | { type: 'StepLog'; steps: { id: string; label: string; detail?: string; ms?: number }[] }
  | { type: 'Note'; text: string }
  | { type: 'ActionBar'; actions: Action[] }
export type BlockType = Block['type']

/* ---------- Contract 5: the workspace document ---------- */
export type Brief = { text: string; facts: { id: string; label: string; value?: string }[]; /** what the person needs that no tool does, said to them */ limits?: string[]
  /** The scans the work has been narrowed to, once the agent has picked them. */
  scope?: string[] }
export type Question = { id: string; text: string; kind: 'choice' | 'number' | 'text'; options?: string[]; unit?: string; pref?: string; tool?: string; answer?: string | number; /** a value to offer: the tool's default, or what the person already said */ hint?: string | number }
export type ToolRef = { id: string; title: string; code?: string; summary?: string; reason: string; coverage?: string; by: By }
export type Run = { id: string; tool: string; label: string; step?: string; status: 'running' | 'done' | 'failed'; ms?: number; summary?: string; stale?: boolean
  /** When it started, ms since the epoch, when the server says. */
  at?: number
  /** The scan the run is about; or, for a run on a place with no scan, the place. */
  sid?: string; place?: { property_id?: number | null; address?: string | null; geo?: [number, number] | null } }
export type Panel = { id: string; tool: string; title: string; scope?: string; sid?: string; run?: string; blocks: Block[]
  /** What the panel is: a tool's result (also when missing), the agent's closing summary, a ranked comparison, or a note the agent composed. */
  role?: 'tool' | 'summary' | 'ranking' | 'note' }
export type PlanStep = { id: string; label: string; status: 'pending' | 'active' | 'done' }
/** A learned item: what it is, the event it came from, and the value to go back to. */
export type Pref = { key: string; label: string; value: number | string | boolean; unit?: string; from: string; prev?: number | string | boolean; by: By; at: number }
export type ShortlistItem = { sid: string; name: string; address: string; note?: string }
export type Layer = { id: string; tool: string; kind: string; dataRef: string }

export type Doc = {
  id: string
  brief: Brief | null
  questions: Question[]
  tools: ToolRef[]
  runs: Run[]
  findings: (Finding & { tool: string; run?: string })[]
  layers: Layer[]
  overlays: { id: string; tool: string; sid?: string; overlay: Overlay }[]
  panels: Panel[]
  plan: PlanStep[]
  prefs: Pref[]
  shortlist: ShortlistItem[]
  camera: { anchor: Anchor; finding?: string; by: By; stay?: boolean } | null
  log: Op[]
}

export type By = 'agent' | 'user'
type Meta = { by: By; at?: number; run?: string }
export type Op = Meta & (
  | { op: 'brief.set'; brief: Brief }
  | { op: 'question.ask'; question: Question }
  | { op: 'question.answer'; id: string; answer: string | number }
  | { op: 'tool.enable'; tool: Omit<ToolRef, 'by'> }
  | { op: 'tool.disable'; id: string }
  | { op: 'run.start'; id: string; tool: string; label: string; step?: string; sid?: string }
  | { op: 'run.finish'; id: string; status?: 'done' | 'failed'; ms?: number; summary?: string }
  | { op: 'finding.add'; tool: string; finding: Finding }
  | { op: 'layer.upsert'; layer: Layer }
  | { op: 'overlay.upsert'; id: string; tool: string; sid?: string; overlay: Overlay | null }
  | { op: 'panel.upsert'; panel: Panel }
  | { op: 'camera.focus'; anchor: Anchor; finding?: string; /** look at it without leaving the current place (a map anchor on a scan's page) */ stay?: boolean }
  | { op: 'plan.set'; steps: PlanStep[] }
  | { op: 'pref.set'; key: string; label?: string; value: number | string | boolean | null; unit?: string; from?: string }
  | { op: 'shortlist.add'; item: ShortlistItem }
  | { op: 'shortlist.remove'; sid: string }
)
export type OpName = Op['op']
/** An op before the sender is stamped on it. */
export type OpInput = Op extends infer O ? (O extends Op ? Omit<O, 'by'> : never) : never
