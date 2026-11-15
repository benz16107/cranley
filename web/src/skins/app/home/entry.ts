/* What pressing Start does, decided from what the person gave: a sentence, a building, or both. Pure, so it runs
   under `node --test`. */
export type Picked = { id: string; metro: string | null; scans: { sid: string }[] }
export type Entry =
  | { do: 'nothing' }
  /** A sentence alone: the agent composes a workspace, and its tools and questions arrive on Home. */
  | { do: 'compose'; text: string }
  /** A sentence about one building: a new investigation, asked on that building's page. */
  | { do: 'ask'; text: string; sid: string }
  /** A building alone: open it. One with several scans opens on the map, where its scans are listed. */
  | { do: 'scan'; sid: string }
  | { do: 'explore'; city?: string; b: string }

export function entry(text: string, at: Picked | null): Entry {
  const said = text.trim()
  if (!at) return said ? { do: 'compose', text: said } : { do: 'nothing' }
  const sid = at.scans[0]?.sid
  if (said && sid) return { do: 'ask', text: said, sid }
  return sid && at.scans.length === 1 ? { do: 'scan', sid } : { do: 'explore', city: at.metro ?? undefined, b: at.id }
}

/** An address as two lines: the street, then the rest. */
export function lines(address: string): [string, string] {
  const [street, ...rest] = address.split(',').map((x) => x.trim())
  return [street, rest.join(', ')]
}
