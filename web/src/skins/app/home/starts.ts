import { NEEDS } from '../../../core/index.ts'

/* Starting points by who the person is. Picking one writes its sentence into the field, where it can be changed
   before it is sent. Where core has a need for that person its sentence is used as written, so a server that is not
   answering still plays the recorded composition for it. */
export type Start = { id: string; who: string; sentence: string; need?: string }

const need = (id: string) => NEEDS.find((n) => n.id === id)?.sentence ?? ''

export const STARTS: Start[] = [
  { id: 'renter', who: 'Renter', sentence: 'I am renting, and I want to check an apartment against its listing before I sign.' },
  { id: 'buyer', who: 'Buyer', sentence: 'I am buying a house and I want to know what could go wrong with it before I make an offer.' },
  { id: 'wheelchair', who: 'Wheelchair user', sentence: need('wheelchair'), need: 'wheelchair' },
  { id: 'restaurant', who: 'Restaurant owner', sentence: 'I am opening a restaurant and I need to know whether a space works for a kitchen and a dining room.' },
  { id: 'manager', who: 'Property manager', sentence: need('manager'), need: 'manager' },
  { id: 'fire', who: 'Fire crew', sentence: need('fire'), need: 'fire' },
  { id: 'insurer', who: 'Insurer', sentence: 'I underwrite home insurance and I need the flood and fire exposure of a house.' },
]
