/* Generated from workspace.schema.json by server/threshold/agent/export.py. Do not edit. */

/**
 * Contract 5. `workspace` is the document, `op` one of the sixteen operations, `log_entry` what the SSE
 * stream and the op log carry, `block` one panel block, plus Contract 3 (`tool_result`) and the tool manifest.
 */
export interface WorkspaceContract {
  workspace: Workspace;
  op:
    | BriefSet
    | QuestionAsk
    | QuestionAnswer
    | ToolEnable
    | ToolDisable
    | RunStart
    | RunFinish
    | FindingAdd
    | LayerUpsert
    | OverlayUpsert
    | PanelUpsert
    | CameraFocus
    | PlanSet
    | PrefSet
    | ShortlistAdd
    | ShortlistRemove;
  log_entry: LogEntry;
  block:
    | VerdictHeader
    | MetricRow
    | CheckList
    | EvidenceStrip
    | RankedTable
    | MiniChart
    | FloorPlanMini
    | Controls
    | AssumptionChips
    | StepLog
    | Note
    | ActionBar;
  tool_result: ToolResult;
  manifest: Manifest;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Workspace".
 */
export interface Workspace {
  schema: "workspace/1";
  id: string;
  profile?: string;
  created?: number;
  updated?: number;
  brief?: Brief;
  questions?: Question[];
  tools?: ToolEntry[];
  runs?: Run[];
  findings?: WsFinding[];
  layers?: Layer[];
  overlays?: WsOverlay[];
  panels?: Panel[];
  camera?: Camera | null;
  plan?: PlanStep[];
  prefs?: {
    [k: string]: Pref;
  };
  shortlist?: ShortlistItem[];
}
export interface Brief {
  /**
   * What the person said, in their words
   */
  text?: string;
  /**
   * One line: who they are and what they need
   */
  summary?: string;
  persona?: string | null;
  scope?: Scope;
  /**
   * Answers keyed by preference key (x-pref)
   */
  facts?: {
    [k: string]: unknown;
  };
}
export interface Scope {
  sids?: string[];
  address?: string | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Question".
 */
export interface Question {
  id: string;
  /**
   * Preference key the answer fills
   */
  key: string;
  text: string;
  tools: string[];
  /**
   * JSON Schema of the answer (type, minimum, maximum, x-unit)
   */
  input: {
    [k: string]: unknown;
  };
  answer?: {
    [k: string]: unknown;
  };
  answered?: boolean;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ToolEntry".
 */
export interface ToolEntry {
  id: string;
  enabled?: boolean;
  reason?: string;
  by?: "agent" | "user" | "system";
  status?: "ready" | "planned";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Run".
 */
export interface Run {
  id: string;
  tool: string;
  sid?: string | null;
  inputs?: {
    [k: string]: unknown;
  };
  /**
   * input -> preference key it came from
   */
  inputs_from?: {
    [k: string]: string;
  };
  plan_step?: string | null;
  status?: "running" | "done" | "error" | "skipped";
  started?: number | null;
  finished?: number | null;
  steps?: string[];
  summary?: string;
  error?: string | null;
  result?: ToolResult | null;
  /**
   * A preference this run used changed after it finished
   */
  stale?: boolean;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ToolResult".
 */
export interface ToolResult {
  tool?: string;
  scope: ScanScope | AddressScope | ScansScope;
  verdict: Verdict;
  metrics?: Metric[];
  checks?: Check[];
  findings?: Finding[];
  overlays?: (LensOverlay | RuleOverlay | PinsOverlay | RouteOverlay | WaterOverlay | BoxOverlay)[];
  assumptions?: Assumption[];
  actions?: Action[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ScanScope".
 */
export interface ScanScope {
  sid: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "AddressScope".
 */
export interface AddressScope {
  address: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ScansScope".
 */
export interface ScansScope {
  sids: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Verdict".
 */
export interface Verdict {
  status: "pass" | "warn" | "fail" | "unknown";
  text: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Metric".
 */
export interface Metric {
  id: string;
  label: string;
  value: number | null;
  unit: string;
  source: Source;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Source".
 */
export interface Source {
  layer: "matterport" | "vexcel" | "costar" | "drone" | "model";
  method: "geometry" | "vision" | "lookup" | "simulation";
  confidence: "high" | "medium" | "low";
  note?: string | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Check".
 */
export interface Check {
  id: string;
  rule: string;
  measured: number | null;
  threshold: number | null;
  unit: string;
  status: "pass" | "warn" | "fail" | "unknown";
  standard?: string | null;
  findings?: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Finding".
 */
export interface Finding {
  id: string;
  title: string;
  status: "pass" | "warn" | "fail" | "unknown";
  detail: string;
  anchor: PointAnchor | RoomAnchor | OpeningAnchor | WallAnchor | PanoAnchor | GeoAnchor | null;
  source: Source;
  media?: Media[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "PointAnchor".
 */
export interface PointAnchor {
  sid: string;
  /**
   * @minItems 3
   * @maxItems 3
   */
  point: [unknown, unknown, unknown];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "RoomAnchor".
 */
export interface RoomAnchor {
  sid: string;
  room: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "OpeningAnchor".
 */
export interface OpeningAnchor {
  sid: string;
  opening: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "WallAnchor".
 */
export interface WallAnchor {
  sid: string;
  wall: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "PanoAnchor".
 */
export interface PanoAnchor {
  sid: string;
  pano: string;
  yaw_deg: number;
  pitch_deg: number;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "GeoAnchor".
 */
export interface GeoAnchor {
  /**
   * [lon, lat]
   *
   * @minItems 2
   * @maxItems 2
   */
  geo: [unknown, unknown];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Media".
 */
export interface Media {
  kind: "pano" | "ortho" | "drone";
  ref: string;
  box?: [unknown, unknown, unknown, unknown] | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "LensOverlay".
 */
export interface LensOverlay {
  kind: "lens";
  /**
   * room id -> value
   */
  values: {
    [k: string]: number;
  };
  ramp: "sequential" | "status";
  legend: Legend;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Legend".
 */
export interface Legend {
  title: string;
  unit: string;
  min: number;
  max: number;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "RuleOverlay".
 */
export interface RuleOverlay {
  kind: "rule";
  select: SelectRooms | SelectRoomLabels | SelectOpenings | SelectWalls;
  style: "solid" | "dim" | "hide" | "highlight" | "pass" | "warn" | "fail";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "SelectRooms".
 */
export interface SelectRooms {
  rooms: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "SelectRoomLabels".
 */
export interface SelectRoomLabels {
  room_labels: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "SelectOpenings".
 */
export interface SelectOpenings {
  openings: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "SelectWalls".
 */
export interface SelectWalls {
  walls: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "PinsOverlay".
 */
export interface PinsOverlay {
  kind: "pins";
  pins: Pin[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Pin".
 */
export interface Pin {
  id: string;
  anchor: PointAnchor | RoomAnchor | OpeningAnchor | WallAnchor | PanoAnchor | GeoAnchor;
  label: string;
  status: "pass" | "warn" | "fail" | "unknown";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "RouteOverlay".
 */
export interface RouteOverlay {
  kind: "route";
  floor: string;
  points: [unknown, unknown, unknown][];
  chokes?: Choke[];
  label: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Choke".
 */
export interface Choke {
  /**
   * @minItems 3
   * @maxItems 3
   */
  point: [unknown, unknown, unknown];
  width: number;
  status: "pass" | "warn" | "fail" | "unknown";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "WaterOverlay".
 */
export interface WaterOverlay {
  kind: "water";
  level_m: number;
  datum?: "scan_z";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "BoxOverlay".
 */
export interface BoxOverlay {
  kind: "box";
  /**
   * @minItems 3
   * @maxItems 3
   */
  center: [unknown, unknown, unknown];
  /**
   * @minItems 3
   * @maxItems 3
   */
  size: [unknown, unknown, unknown];
  yaw_deg?: number;
  label: string;
  status: "pass" | "warn" | "fail" | "unknown";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Assumption".
 */
export interface Assumption {
  /**
   * For an editable assumption, the preference key (x-pref) that an edit sets
   */
  id: string;
  label: string;
  value: number | string | boolean | null;
  unit?: string | null;
  editable?: boolean;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Action".
 */
export interface Action {
  id: string;
  label: string;
  tool: string;
  inputs?: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "WsFinding".
 */
export interface WsFinding {
  id: string;
  title: string;
  status: "pass" | "warn" | "fail" | "unknown";
  detail: string;
  anchor: PointAnchor | RoomAnchor | OpeningAnchor | WallAnchor | PanoAnchor | GeoAnchor | null;
  source: Source;
  media?: Media[];
  run?: string | null;
  tool?: string | null;
  feedback?: Feedback | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Feedback".
 */
export interface Feedback {
  verdict: "rejected" | "confirmed";
  reason?: string | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Layer".
 */
export interface Layer {
  id: string;
  block: "PinSet" | "ParcelFill" | "Extrusion" | "ReachRing" | "RouteLine" | "OrthoPatch" | "HexDensity" | "Callout";
  /**
   * A back-end route, never data
   */
  data_ref: string;
  label?: string;
  tool?: string | null;
  run?: string | null;
  visible?: boolean;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "WsOverlay".
 */
export interface WsOverlay {
  id: string;
  sid: string;
  overlay: LensOverlay | RuleOverlay | PinsOverlay | RouteOverlay | WaterOverlay | BoxOverlay;
  tool?: string | null;
  run?: string | null;
  visible?: boolean;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Panel".
 */
export interface Panel {
  id: string;
  title: string;
  blocks: (
    | VerdictHeader
    | MetricRow
    | CheckList
    | EvidenceStrip
    | RankedTable
    | MiniChart
    | FloorPlanMini
    | Controls
    | AssumptionChips
    | StepLog
    | Note
    | ActionBar
  )[];
  tool?: string | null;
  run?: string | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "VerdictHeader".
 */
export interface VerdictHeader {
  type: "VerdictHeader";
  /**
   * Run id; shows result.verdict
   */
  run: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "MetricRow".
 */
export interface MetricRow {
  type: "MetricRow";
  run: string;
  /**
   * Metric ids in result.metrics, each shown with its source
   *
   * @maxItems 4
   */
  metrics: [] | [string] | [string, string] | [string, string, string] | [string, string, string, string];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "CheckList".
 */
export interface CheckList {
  type: "CheckList";
  run: string;
  /**
   * Check ids; null means all, worst first
   */
  checks?: string[] | null;
  /**
   * Show only these statuses; null means all
   */
  status?: ("pass" | "warn" | "fail" | "unknown")[] | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "EvidenceStrip".
 */
export interface EvidenceStrip {
  type: "EvidenceStrip";
  /**
   * Workspace finding ids; each thumbnail flies to its anchor
   */
  findings: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "RankedTable".
 */
export interface RankedTable {
  type: "RankedTable";
  title: string;
  /**
   * @maxItems 6
   */
  columns:
    | []
    | [RankedColumn]
    | [RankedColumn, RankedColumn]
    | [RankedColumn, RankedColumn, RankedColumn]
    | [RankedColumn, RankedColumn, RankedColumn, RankedColumn]
    | [RankedColumn, RankedColumn, RankedColumn, RankedColumn, RankedColumn]
    | [RankedColumn, RankedColumn, RankedColumn, RankedColumn, RankedColumn, RankedColumn];
  /**
   * Run ids, one per candidate building
   */
  rows: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "RankedColumn".
 */
export interface RankedColumn {
  /**
   * Metric id read from each row's run result
   */
  metric: string;
  label: string;
  better: "higher" | "lower";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "MiniChart".
 */
export interface MiniChart {
  type: "MiniChart";
  run: string;
  title: string;
  /**
   * Metric ids; one bar each, label and unit from the metric
   */
  metrics: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "FloorPlanMini".
 */
export interface FloorPlanMini {
  type: "FloorPlanMini";
  sid: string;
  floor?: string | null;
  /**
   * Workspace overlay ids drawn on the plan
   */
  overlays?: string[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Controls".
 */
export interface Controls {
  type: "Controls";
  tool: string;
  controls: Control[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Control".
 */
export interface Control {
  /**
   * Tool input name
   */
  input: string;
  /**
   * Preference key an edit sets (pref.set), which re-runs the tool
   */
  pref?: string | null;
  label: string;
  kind: "slider" | "select" | "toggle";
  min?: number | null;
  max?: number | null;
  step?: number | null;
  options?: string[] | null;
  unit?: string | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "AssumptionChips".
 */
export interface AssumptionChips {
  type: "AssumptionChips";
  /**
   * Shows result.assumptions; an editable chip sends pref.set with key = assumption id
   */
  run: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "StepLog".
 */
export interface StepLog {
  type: "StepLog";
  /**
   * Shows the run's steps
   */
  run: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Note".
 */
export interface Note {
  type: "Note";
  text: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ActionBar".
 */
export interface ActionBar {
  type: "ActionBar";
  /**
   * Shows result.actions; each runs its tool with its inputs
   */
  run: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Camera".
 */
export interface Camera {
  anchor: PointAnchor | RoomAnchor | OpeningAnchor | WallAnchor | PanoAnchor | GeoAnchor;
  reason?: string;
  at?: number | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "PlanStep".
 */
export interface PlanStep {
  id: string;
  text: string;
  status?: "pending" | "in_progress" | "completed";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Pref".
 */
export interface Pref {
  key: string;
  value: unknown;
  /**
   * The event it came from, said to the person
   */
  reason?: string;
  /**
   * Log seq of the op it was learned from
   */
  cause?: number | null;
  by?: "agent" | "user" | "system";
  at?: number | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ShortlistItem".
 */
export interface ShortlistItem {
  sid: string;
  note?: string;
  by?: "agent" | "user" | "system";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "BriefSet".
 */
export interface BriefSet {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "brief.set";
  text?: string | null;
  summary?: string | null;
  persona?: string | null;
  scope?: Scope1 | null;
  facts?: {
    [k: string]: unknown;
  } | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Scope".
 */
export interface Scope1 {
  sids?: string[];
  address?: string | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "QuestionAsk".
 */
export interface QuestionAsk {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "question.ask";
  question: Question;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "QuestionAnswer".
 */
export interface QuestionAnswer {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "question.answer";
  id: string;
  value: unknown;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ToolEnable".
 */
export interface ToolEnable {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "tool.enable";
  tool: string;
  reason?: string;
  status?: "ready" | "planned";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ToolDisable".
 */
export interface ToolDisable {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "tool.disable";
  tool: string;
  reason?: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "RunStart".
 */
export interface RunStart {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "run.start";
  record: Run;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "RunFinish".
 */
export interface RunFinish {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "run.finish";
  id: string;
  status: "done" | "error" | "skipped";
  summary?: string;
  steps?: string[];
  error?: string | null;
  result?: ToolResult | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "FindingAdd".
 */
export interface FindingAdd {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "finding.add";
  finding: WsFinding;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "LayerUpsert".
 */
export interface LayerUpsert {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "layer.upsert";
  layer: Layer;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "OverlayUpsert".
 */
export interface OverlayUpsert {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "overlay.upsert";
  overlay: WsOverlay;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "PanelUpsert".
 */
export interface PanelUpsert {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "panel.upsert";
  panel: Panel;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "CameraFocus".
 */
export interface CameraFocus {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "camera.focus";
  anchor: PointAnchor | RoomAnchor | OpeningAnchor | WallAnchor | PanoAnchor | GeoAnchor;
  reason?: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "PlanSet".
 */
export interface PlanSet {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "plan.set";
  steps: PlanStep[];
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "PrefSet".
 */
export interface PrefSet {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "pref.set";
  key: string;
  /**
   * null removes the preference
   */
  value: {
    [k: string]: unknown;
  };
  reason?: string;
  cause?: number | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ShortlistAdd".
 */
export interface ShortlistAdd {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "shortlist.add";
  sid: string;
  note?: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "ShortlistRemove".
 */
export interface ShortlistRemove {
  by?: "agent" | "user" | "system";
  /**
   * Agent turn or tool run this op belongs to
   */
  run?: string | null;
  op: "shortlist.remove";
  sid: string;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "LogEntry".
 */
export interface LogEntry {
  seq: number;
  at: number;
  op?:
    | (
        | BriefSet
        | QuestionAsk
        | QuestionAnswer
        | ToolEnable
        | ToolDisable
        | RunStart
        | RunFinish
        | FindingAdd
        | LayerUpsert
        | OverlayUpsert
        | PanelUpsert
        | CameraFocus
        | PlanSet
        | PrefSet
        | ShortlistAdd
        | ShortlistRemove
      )
    | null;
  /**
   * Seq of the entry this one undoes
   */
  undo?: number | null;
  /**
   * Seq of the user op this entry was learned from
   */
  cause?: number | null;
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Manifest".
 */
export interface Manifest {
  id: string;
  title: string;
  /**
   * For the person: tooltip and 'why this tool'
   */
  summary: string;
  /**
   * For the model: when to use it and what it returns
   */
  model_description: string;
  icon?: string | null;
  personas?: string[];
  requires?: Requirement[];
  /**
   * JSON Schema with x-ask, x-pref, x-source, x-unit
   */
  inputs?: {
    [k: string]: unknown;
  };
  blocks?: (
    | "VerdictHeader"
    | "MetricRow"
    | "CheckList"
    | "EvidenceStrip"
    | "RankedTable"
    | "MiniChart"
    | "FloorPlanMini"
    | "Controls"
    | "AssumptionChips"
    | "StepLog"
    | "Note"
    | "ActionBar"
  )[];
  overlays?: ("lens" | "rule" | "pins" | "route" | "water" | "box")[];
  annotations?: Annotations;
  examples?: string[];
  status?: "ready" | "planned";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Requirement".
 */
export interface Requirement {
  /**
   * e.g. matterport.rooms, matterport.openings, vexcel.ortho, costar.property
   */
  layer: string;
  need?: "required" | "optional";
  fallback?: string | null;
}
export interface Annotations {
  read_only?: boolean;
  cost?: "fast" | "slow";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Annotations".
 */
export interface Annotations1 {
  read_only?: boolean;
  cost?: "fast" | "slow";
}
/**
 * This interface was referenced by `WorkspaceContract`'s JSON-Schema
 * via the `definition` "Brief".
 */
export interface Brief1 {
  /**
   * What the person said, in their words
   */
  text?: string;
  /**
   * One line: who they are and what they need
   */
  summary?: string;
  persona?: string | null;
  scope?: Scope;
  /**
   * Answers keyed by preference key (x-pref)
   */
  facts?: {
    [k: string]: unknown;
  };
}
