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
}

export type Pick =
  | { kind: 'room'; id: string; point: Vec3 }
  | { kind: 'opening'; id: string; point: Vec3 }
  | { kind: 'wall'; id: string; point: Vec3 }
  | { kind: 'pano'; id: string }
  | { kind: 'pin'; id: string }
