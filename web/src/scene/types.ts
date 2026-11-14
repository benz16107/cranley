// Contract 1 (ScanPlan), Contract 3 (anchor) and Contract 4 (overlays) as the scene reads them.
// Source of truth: docs/ARCHITECTURE.md. Metres, scan frame, x and y on the floor, z up.

export type Vec2 = [number, number]
export type Vec3 = [number, number, number]
export type Status = 'pass' | 'warn' | 'fail' | 'unknown'

export interface Floor { id: string; label: string | null; sequence: number | null }
export interface Wall {
  id: string; floor: string; a: Vec2; b: Vec2; type: 'wall' | 'invisible' | string
  thickness: number | null; length: number; rooms: string[]; openings: string[]
}
export interface Opening {
  id: string; wall: string; floor: string; type: 'doorway' | 'window' | 'opening' | string
  width: number | null; height: number | null; sill: number | null; center: Vec2; rooms: string[]
}
export interface Room {
  id: string; floor: string; label: string | null; polygon: Vec2[]; area: number | null
  height: number | null; walls: string[]
}
export interface Pano {
  id: string; label: string | null; position: Vec3; rotation: [number, number, number, number] | null
  floor: string | null; room: string | null; neighbors: string[]
}
export interface FloorplanImage {
  floor: string; format: string; flags: string[] | null; width: number | null; height: number | null
  resolution: number | null; origin: { x: number; y: number } | null
}
export interface ScanPlan {
  schema: string; sid: string; name: string | null; address: string | null
  has: { splat: boolean; defurnished: boolean; room_labels: boolean; openings: boolean }
  floors: Floor[]; walls: Wall[]; openings: Opening[]; rooms: Room[]; panos: Pano[]; floorplans: FloorplanImage[]
  /** The compass rotation from the scan frame to east/north (Contract 1). Only `pose.bearing` reads it. */
  geo?: { yaw_deg?: number | null; fit?: { rotation_deg?: number; verified?: boolean } | null } | null
}

export type Anchor =
  | { sid?: string; point: Vec3 }
  | { sid?: string; room: string }
  | { sid?: string; opening: string }
  | { sid?: string; wall: string }
  | { sid?: string; pano: string; yaw_deg: number; pitch_deg: number }

export type RuleStyle = 'solid' | 'dim' | 'hide' | 'highlight' | 'pass' | 'warn' | 'fail'
export type Overlay =
  | { kind: 'lens'; values: Record<string, number>; ramp: 'sequential' | 'status'; legend: { title: string; unit?: string; min: number; max: number } }
  | { kind: 'rule'; select: { rooms?: string[]; room_labels?: string[]; openings?: string[]; walls?: string[] }; style: RuleStyle }
  | { kind: 'pins'; pins: { id: string; anchor: Anchor; label: string; status: Status }[] }
  | { kind: 'route'; floor: string; points: Vec3[]; chokes: { point: Vec3; width: number; status: Status }[]; label?: string }
  | { kind: 'water'; level_m: number; datum: 'scan_z' }
  | { kind: 'box'; center: Vec3; size: Vec3; yaw_deg: number; label?: string; status: Status }
  | { kind: string; [key: string]: unknown } // unknown kinds are ignored by every renderer

export type Mode = 'dollhouse' | 'plan' | 'pano' | 'splat'
export interface View {
  mode: Mode
  floor?: string | null   // show this floor and hide the ones above it; null shows all
  pano?: string | null    // scan position for mode "pano"
  focus?: Anchor | null   // move the camera to look at this
  cut?: number | null     // cut-away height in metres above each floor; null leaves walls whole
  explode?: number        // 0..1, how far stacked floors are pulled apart
  wipe?: number | null    // 0..1 screen position of the furnished | empty divider in a panorama; null is off
  measures?: boolean      // show opening widths

  // ---- where the camera puts its subject. All optional; leaving them out is the behaviour before they existed. ----
  /** The free part of the picture: CSS px in from each edge of the scene element (missing sides are 0). Everything
      outside it has interface on it. Fits and focuses use this rectangle, not the whole canvas, by shifting the
      projection (verticals stay vertical; labels, pins and picking follow). A change eases over 400 ms. */
  frame?: { top?: number; right?: number; bottom?: number; left?: number } | null
  /** Panorama only: vertical field of view in degrees, clamped to 34..96. null is the default (76). It is applied
      when it changes and when a panorama is entered; the person's own zoom then stays until it changes again. */
  fov?: number | null
  /** Panorama only: which way to look, in the scan frame as Contract 3 defines it (yaw counter-clockwise from +x,
      pitch positive looking up). Applied when it changes and when a panorama is entered; a focus on a panorama
      anchor at that position wins. The person's drag then stays until it changes again. */
  look?: { yaw_deg: number; pitch_deg: number } | null
  /** Dollhouse and splat: where the outside camera stands, in map terms. bearing: compass degrees the camera looks
      toward (0 north, clockwise; uses plan.geo, and without it 0 is the scan's +y). pitch: degrees from straight
      down (0 plan view, 90 horizon), clamped to the mode's limits. range: metres from the target, or 'fit' (the
      default) for the mode's own fitted distance. A change flies there; the person's drag then stays. */
  pose?: { bearing?: number; pitch?: number; range?: number | 'fit' } | null
  /** Dollhouse and splat: a slow turn about the target in degrees per second (positive is counter-clockwise seen
      from above). 0 stops it; leaving it out keeps the splat's own slow drift. A drag stops it until it changes. */
  orbit?: number
  /** Change this number to frame the whole building again in the current mode (after a close-up on a finding). */
  fit?: number

  // ---- what the building is drawn from and what stands around it. All optional; missing is the first value. ----
  /** Dollhouse: 'model' draws the walls and openings measured in the plan; 'scan' draws Matterport's own scanned
      mesh with colour from the panoramas (rooms, routes, pins and water still draw on it). */
  surface?: 'model' | 'scan'
  /** Dollhouse and splat: 'studio' is the building alone; 'aerial' stands it in its real surroundings (Vexcel's 3D
      city mesh, or its surface model where there is none). The surroundings close over the model as the camera
      pulls away. Needs plan.geo; without it the scene says so and stays in the studio. */
  env?: 'studio' | 'aerial'
  /** 'xray' draws the model's walls as glass, so a route or a failing room reads through them. In splat mode it
      shows the model inside the drone capture (the two share the scan frame). */
  style?: 'solid' | 'xray'
  /** Change this number to play the flight from above the neighbourhood down into a room. */
  tour?: number
  /** Matterport's own viewer over the scene, starting in its dollhouse. Nothing of ours draws inside it. */
  showcase?: boolean
}

/** What onCamera reports: the camera in the same units as `pose` and `fov`, and where `view.focus` is on screen. */
export interface CameraInfo {
  mode: Mode
  moving: boolean          // a designed flight is in progress
  bearing: number; pitch: number; range: number; fov: number
  /** view.focus in CSS px inside the scene element; visible is false behind the camera or outside the canvas. */
  focus: { x: number; y: number; visible: boolean } | null
}

export type Pick =
  | { kind: 'room'; id: string; point: Vec3 }
  | { kind: 'opening'; id: string; point: Vec3 }
  | { kind: 'wall'; id: string; point: Vec3 }
  | { kind: 'pano'; id: string }
  | { kind: 'pin'; id: string }
