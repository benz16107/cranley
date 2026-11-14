import type { ScanPlan } from '../workspace/types.ts'

const plans = new Map<string, Promise<ScanPlan>>()
/** One request per scan per session. The server caches on disk; this keeps the shared keys quiet. */
export function fetchPlan(sid: string): Promise<ScanPlan> {
  let p = plans.get(sid)
  if (!p) {
    p = fetch(`/api/scan/${encodeURIComponent(sid)}/plan`).then((r) => {
      if (!r.ok) throw new Error(r.status === 404 ? 'This scan is not in the index.' : `The plan did not load (${r.status}).`)
      return r.json()
    })
    p.catch(() => plans.delete(sid))
    plans.set(sid, p)
  }
  return p
}
export const panoFace = (sid: string, pano: string, face = 1) => `/api/scan/${sid}/pano/${pano}/${face}.jpg?res=2k`
