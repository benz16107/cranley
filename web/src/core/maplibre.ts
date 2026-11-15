// MapLibre's stylesheet is imported by index.ts: imported here, it would keep this module, and MapLibre, on every page.
// MapLibre 6 ships its worker as a separate ES module. Vite has to be told to bundle it and hand back the URL.
import { Map as MapLibreMap, setWorkerUrl, type MapOptions } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

let workerSet = false
/** MapLibre's Map, telling MapLibre where its worker is before the first map starts. Set at import time instead, the
    call would make every page that imports core download MapLibre (1 MB), map or not. */
export class Map extends MapLibreMap {
  constructor(options: MapOptions) {
    if (!workerSet) { setWorkerUrl(workerUrl); workerSet = true }
    super(options)
  }
}

export * from 'maplibre-gl'
