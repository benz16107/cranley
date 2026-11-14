// Dev only. Until GET /api/scan/{sid}/splat exists, splats come from splat-proxy.mjs in this folder
// (run it with `node src/scene/dev/splat-proxy.mjs`; it listens on 8797 and caches in $THRESHOLD_DATA_DIR/cache/splat).
// engine/splat.ts tries the real route first and only then asks here, so this file can be deleted when the route lands.
export const splatUrlDev = (sid: string) => `http://${location.hostname}:8797/splat/${sid}`
