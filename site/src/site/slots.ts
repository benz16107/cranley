// Every picture and clip on the site is a slot. This file says what each slot expects; the media pass fills one by
// adding a file, with no code change:
//
//   public/media/<id>.webp|png|jpg|mp4|webm        a safe visual (test scans, our own diagrams, OpenStreetMap). Committed.
//   public/media/real/<id>.webp|png|jpg|mp4|webm   the real product with sponsor content on screen. Never committed
//                                                  (public/media/real is git-ignored); used only when the site is built
//                                                  with CRANLEY_REAL_VISUALS=1, after CoStar has confirmed the website.
//
// Several files for one slot: <id>-1, <id>-2, ... The shot numbers are docs/site-plan.md's re-shoot list.
// The notes that name each slot show on the page unless the site is built with PUBLIC_SLOT_LABELS=off.
import { existsSync } from 'node:fs'

export type SlotInfo = {
  /** docs/site-plan.md re-shoot number, 'real' for a shot that only exists on sponsor data, or 'new' for one the plan does not list */
  shot: string
  title: string
  /** what must be on screen */
  expects: string
  /** T: made-up test scans. R: a RoomPlan scan we made. O: OpenStreetMap and open layers. own: our drawing or photo. real: needs CoStar's yes for the website. */
  source: 'T' | 'R' | 'O' | 'own' | 'real'
  alt: string
  caption?: string
}

export const SLOTS = {
  'hero-loop': { shot: '1', source: 'T', title: 'Hero loop, 10 s', expects: 'Type the need, the composer adds tools, an agent lane runs, the verdict, the route draws, the failing door turns red. App look on the test home, measured 3D cut open, 1440 px, light theme.', alt: 'The Cranley workspace checking a wheelchair route through the test home' },
  'building-view': { shot: 'new', source: 'T', title: '3D building view', expects: 'The Building page in the final look: a building in 3D with one tool\'s result drawn on it.', alt: 'A building in 3D in the Cranley app with a route drawn through it' },
  'result-drawer': { shot: 'new', source: 'T', title: 'Tool result', expects: 'A tool\'s result open beside the building in the final look: the verdict, the checks that failed, the source of each number.', alt: 'A tool result in the Cranley app with its verdict, checks and sources' },
  'home-composer': { shot: '2', source: 'T', title: 'Home with the composer', expects: 'Home page with the field for a need and the persona list. Fresh profile, empty Recent and Saved, footer count hidden.', alt: 'Cranley home page with the field where a person types what they need' },
  'agent-lanes': { shot: '3', source: 'T', title: 'Agent panel', expects: 'Plan todos, two parallel lanes (test home and test cafe), both paused on the smoke-simulation approval card. Cropped to the agent panel.', alt: 'The agent panel with a plan, two buildings checked in parallel and an approval card' },
  'langsmith-trace': { shot: '4', source: 'T', title: 'LangSmith trace', expects: 'The trace of the same turn, with the project\'s other runs cropped out.', alt: 'A LangSmith trace of one agent turn' },
  'live-sync': { shot: '5', source: 'T', title: 'Phone to desktop', expects: 'Desktop workspace on the test home with /m paired beside it: a door width typed on the phone updates the Door widths panel. Split-screen recording.', alt: 'A door width typed on a phone appearing in the desktop workspace' },
  'share-link': { shot: '6', source: 'T', title: 'Read-only share link', expects: 'Copy link, then the shared workspace open in a second browser.', alt: 'A workspace opened read-only from a share link' },
  renovate: { shot: '7', source: 'T', title: 'Renovate, Now and After', expects: 'Renovate on the 0.71 m bathroom door of the test home: the check flips to pass, with the cost line from the takeoff.', alt: 'The renovate tool comparing the plan now and after widening a door' },
  'pdf-report': { shot: '8', source: 'T', title: 'PDF site reports', expects: 'Accessibility, fire pre-plan and fit-out reports on the test cafe, three pages each, exported as images with the Cranley brand.', alt: 'Pages of a Cranley PDF site report for the made-up test cafe' },
  'iphone-app': { shot: '9', source: 'T', title: 'iPhone app', expects: 'Dark theme, like every screenshot on the site. The plan, then the tools run on it. Simulator on the made-up sample home now; a real phone and a scan we made later.', alt: 'The Cranley iPhone app in dark theme showing a scanned plan and the tools run on it', caption: 'The iPhone app in the simulator, on the made-up sample home: the plan from a RoomPlan export, the tools run on it, and what the scan cannot tell.' },
  'field-visit': { shot: '9', source: 'T', title: 'Site visit on the phone', expects: 'Dark theme, like every screenshot on the site. The field report flow: pick a report, the checks finish, open the PDF. Simulator on the test cafe now; a real phone later.', alt: 'The Cranley iPhone app running a fire safety site visit on the made-up test cafe', caption: 'A site visit in the simulator on the made-up test cafe: pick the report, and the checks run on the scan.' },
  'fire-preplan': { shot: '10', source: 'T', title: 'Fire pre-plan and egress', expects: 'fire_preplan and egress_routes on the test cafe: exits, longest walk, narrowest point, the plan with the route.', alt: 'A fire pre-plan with exit routes drawn on the test cafe' },
  'furniture-fit': { shot: '11', source: 'T', title: 'Furniture fit with 3D models', expects: 'A sofa through the front door and hallway of the test home, the model drawn in the measured 3D.', alt: 'A sofa model placed on the route through the test home' },
  'plan-overlay': { shot: '12', source: 'T', title: 'Plan overlay', expects: 'A feng shui grid or pet hazards drawn on the test home\'s plan.', alt: 'An overlay drawn on the plan of the test home' },
  'mcp-claude-code': { shot: '13', source: 'T', title: 'Claude Code over MCP', expects: 'The asciinema take of Claude Code calling door_widths on the test scan id. No real scan id in the prompt or the answer.', alt: 'Claude Code calling a Cranley tool over MCP in a terminal' },
  'open-map': { shot: '14', source: 'O', title: 'Neighbourhood map, open layers', expects: 'Explorer on a neutral street with the scan layer, satellite and 3D city off; a FEMA flood or transit layer on; OpenStreetMap attribution visible.', alt: 'A neighbourhood map with public flood and transit layers' },
  nearby: { shot: '15', source: 'O', title: 'Nearby places', expects: 'Parks, vets and schools round a bare point with no scan. Map only.', alt: 'A map of parks, vets and schools near a point' },
  'real-scan-3d': { shot: '16', source: 'R', title: '3D of a space we scanned', expects: 'A RoomPlan scan we made, measured 3D cut open, one route and one clearance drawn. Waits for the app on a real phone.', alt: 'A measured 3D view of a room scanned with an iPhone' },
  hardware: { shot: '17', source: 'own', title: 'The mini PC', expects: 'A photo of the machine, and a chart of training loss or steps per second from the Brush logs with no rendered scene.', alt: 'The AMD mini PC that trained the interior splats' },
  'photoreal-building': { shot: 'real', source: 'real', title: 'Photoreal building on its site', expects: 'The scanned mesh baked with its own panoramas, cut open, set in the drone capture and the 3D city.', alt: 'A photoreal scanned house cut open in its 3D city' },
  'flood-street': { shot: 'real', source: 'real', title: 'Flood in the street', expects: 'Harvey\'s measured water rising through a photoreal house, with the list of what to move first.', alt: 'Flood water rising through a scanned house' },
  'smoke-rooms': { shot: 'real', source: 'real', title: 'Smoke through the rooms', expects: 'CFAST smoke depth and heat per room in the dollhouse, with the routes that cross it in red.', alt: 'A smoke simulation filling the rooms of a scanned house' },
  'record-vs-reality': { shot: 'real', source: 'real', title: 'Record versus reality', expects: 'The listed area against the measured one, each with its source.', alt: 'A comparison of a property record with what the scan measures' },
  'measure-search': { shot: 'real', source: 'real', title: 'Search by measurement', expects: 'One query over the facts database and its ranked table.', alt: 'A ranked table of homes found by what is measured inside them' },
} satisfies Record<string, SlotInfo>

export type SlotId = keyof typeof SLOTS
export const LABELS = import.meta.env.PUBLIC_SLOT_LABELS !== 'off'
const REAL = process.env.CRANLEY_REAL_VISUALS === '1'
const EXT = ['webp', 'png', 'jpg', 'mp4', 'webm']
const SOURCE = { T: 'made-up test scans', R: 'a RoomPlan scan we made', O: 'OpenStreetMap and open layers', own: 'our own photo and numbers', real: 'the real product. Needs CoStar\'s yes for the website' }

/** The files that fill a slot today, real ones first when they are allowed. */
export function filesOf(id: SlotId): { src: string; video: boolean; real: boolean }[] {
  for (const [dir, real] of [['media/real', true], ['media', false]] as const) {
    if (real && !REAL) continue
    const names = [id, ...Array.from({ length: 6 }, (_, i) => `${id}-${i + 1}`)]
    const found = names.flatMap((n) => EXT.filter((e) => existsSync(`public/${dir}/${n}.${e}`)).slice(0, 1).map((e) => ({ src: `/${dir}/${n}.${e}`, video: e === 'mp4' || e === 'webm', real })))
    if (found.length) return found
  }
  return []
}

/** The note the preview shows on a slot: which shot it takes and where that shot may come from. */
export function noteOf(id: SlotId, filled: boolean, real: boolean): string {
  const s: SlotInfo = SLOTS[id]
  const what = s.shot === 'real' ? 'Real product shot' : s.shot === 'new' ? 'New shot for the home page' : `Shot ${s.shot} of the site plan`
  if (real) return `${what}: ${s.title}. Showing the real product.`
  const state = filled ? (s.source === 'real' ? 'Filled' : 'Filled with a safe visual; takes the real product after CoStar\'s yes') : s.source === 'real' ? 'Empty until CoStar confirms the website' : 'Not shot yet'
  return `${what}: ${s.title}. ${state}. Source: ${SOURCE[s.source]}. Expects: ${s.expects}`
}
