import type { Building } from '../../../core/index.ts'

/* The agent writes a scan or a property by its id ("the bedroom in <scan-id>", "property <property-id>"). A person reads
   names. Pure, so it runs under `node --test`. */
export function nameIds(all: Pick<Building, 'id' | 'address' | 'scans'>[]) {
  const ids = new Map<string, { name: string; address: string }>()
  for (const b of all) {
    const address = b.address.split(',')[0]
    if (/^p\d{6,}$/.test(b.id)) ids.set(b.id.slice(1), { name: address, address }) // a property's number
    for (const s of b.scans) ids.set(s.sid, { name: s.name, address })
  }
  return {
    /** One id's name and address, when the building list knows it. */
    of: (id: string) => ids.get(id),
    /** The text with each known id in words. Anything else, numbers included, is left exactly as written. */
    named: (text: string) => text.replace(/[A-Za-z0-9_]{6,}/g, (w) => ids.get(w)?.name ?? w),
  }
}
