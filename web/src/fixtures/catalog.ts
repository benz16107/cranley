import type { Question, ToolRef } from '../workspace/types.ts'
import type { CityId } from '../map/buildings.ts'

/* Fixtures: the tool list and the starting points the front door offers when the agent server is not running.
   The real list comes from GET /api/tools. No building data lives here. */

type Tool = Omit<ToolRef, 'reason' | 'by'>
export const TOOLS: Record<string, Tool> = {
  access: { id: 'access', title: 'Step-free access', code: 'AC', summary: 'Traces the way in from the entrance and measures every doorway on it.', coverage: 'Any scan with a wall outline' },
  fit_through: { id: 'fit_through', title: 'Will it fit', code: 'WF', summary: 'Carries a box of a given size from the entrance to a room and reports where it sticks.', coverage: 'Any scan with a wall outline' },
  record: { id: 'record', title: 'Listed versus measured', code: 'LM', summary: 'Sets what the listing says beside what the scan measures.', coverage: 'Scans with a property record' },
  flood: { id: 'flood', title: 'Flood rehearsal', code: 'FL', summary: 'Raises a named storm’s water through the house and lists what it reaches.', coverage: 'Houses with a drone capture' },
  fire: { id: 'fire', title: 'Fire pre-plan', code: 'FP', summary: 'Lays out entrances, search routes and hose stretches for a crew.', coverage: 'Any scan with a wall outline' },
  office_fit: { id: 'office_fit', title: 'Office fit', code: 'OF', summary: 'Seats a team room by room and counts what is left over.', coverage: 'Office suites' },
  turn: { id: 'turn', title: 'Unit turn scope', code: 'UT', summary: 'Takes off floor and wall areas by room to price the work between tenants.', coverage: 'Apartment units' },
}

export type Need = {
  id: string; who: string; need: string; sentence: string; city: CityId; runsOn: string
  tools: [id: string, reason: string][]
  questions: Question[]
  scripted?: boolean
}
export const NEEDS: Need[] = [
  { id: 'wheelchair', who: 'A wheelchair user', need: 'choosing an apartment', city: 'hou', runsOn: 'Apartment units', scripted: true,
    sentence: 'I use a power wheelchair and I am choosing a one-bedroom apartment.',
    tools: [
      ['access', 'You use a wheelchair, so every doorway on the way in has to clear your chair.'],
      ['fit_through', 'A power chair needs room to turn. That is the same clearance check with your chair as the box.'],
      ['record', 'A listing that says "accessible" is making a claim. This sets it beside the measurements.'],
    ],
    questions: [
      { id: 'chair', text: 'How wide a doorway do you need?', kind: 'choice', options: ['0.76 m', '0.815 m', '0.86 m', '0.915 m'], pref: 'access.door_clear', tool: 'access' },
      { id: 'turn', text: 'Do you need to turn right around in the bathroom?', kind: 'choice', options: ['Yes', 'No'], pref: 'access.turning_needed', tool: 'access' },
    ] },
  { id: 'fire', who: 'A fire captain', need: 'pre-planning an apartment complex', city: 'hou', runsOn: 'Apartment units and shared rooms',
    sentence: 'I am a fire captain pre-planning an apartment complex in my district.',
    tools: [['fire', 'A pre-plan is the layout, the ways in and the hose stretch, drawn before the call.'], ['access', 'The same route check tells you whether a stretcher makes each turn.']],
    questions: [{ id: 'hose', text: 'How long is your pre-connected hose line?', kind: 'choice', options: ['45 m', '60 m', '75 m'], pref: 'fire.hose', tool: 'fire' }] },
  { id: 'flood', who: 'A Houston homeowner', need: 'getting ready before a hurricane', city: 'hou', runsOn: 'Houses with a drone capture',
    sentence: 'I own a house in Houston and a hurricane is forecast for this week.',
    tools: [['flood', 'Water height matters room by room. This raises it through your floor plan.'], ['record', 'The year built and the listed floor area set what the flood numbers are compared with.']],
    questions: [{ id: 'storm', text: 'Which flood should I rehearse?', kind: 'choice', options: ['0.3 m', '0.6 m', '1.2 m'], pref: 'flood.level', tool: 'flood' }] },
  { id: 'office', who: 'An office tenant', need: 'checking that a suite fits the team', city: 'la', runsOn: 'Office suites',
    sentence: 'We are a team of 24 looking for an office suite in Los Angeles.',
    tools: [['office_fit', 'Head count against measured rooms is the question a floor area cannot answer.'], ['record', 'The listed rentable area is often larger than the usable rooms.']],
    questions: [{ id: 'heads', text: 'How many people need a desk?', kind: 'number', unit: 'people', pref: 'office.heads', tool: 'office_fit' }] },
  { id: 'manager', who: 'A property manager', need: 'scoping a unit turn', city: 'hou', runsOn: 'Apartment units',
    sentence: 'I manage apartments and I need to scope the work on a unit between tenants.',
    tools: [['turn', 'Paint and flooring are priced by area. This takes the areas off the scan.'], ['record', 'The unit type on record tells me which finishes to expect.']],
    questions: [{ id: 'paint', text: 'Are the ceilings painted on every turn?', kind: 'choice', options: ['Yes', 'No'], pref: 'turn.ceilings', tool: 'turn' }] },
]

/** Which starting point a typed sentence is closest to. A stand-in for the composer's structured call. */
export function matchNeed(sentence: string): Need {
  const s = sentence.toLowerCase()
  const hit = (words: string[]) => words.some((w) => s.includes(w))
  if (hit(['fire', 'captain', 'crew', 'engine'])) return NEEDS[1]
  if (hit(['flood', 'hurricane', 'storm', 'water'])) return NEEDS[2]
  if (hit(['office', 'team', 'desk', 'suite', 'tenant'])) return NEEDS[3]
  if (hit(['manage', 'turn', 'paint', 'landlord'])) return NEEDS[4]
  return NEEDS[0]
}
