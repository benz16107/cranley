// MapLibre 6 ships its worker as a separate ES module. Vite has to be told to bundle it and hand back the URL.
import { setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'

setWorkerUrl(workerUrl)

export * from 'maplibre-gl'
