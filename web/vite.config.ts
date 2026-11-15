import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// `vite preview` (the phone app's unit) sends no-cache on everything. Files under /assets/ carry their content hash in
// the name, so they never change: the browser may keep them for a year and stop asking.
const immutableAssets: Plugin = {
  name: 'immutable-assets',
  configurePreviewServer(server) {
    server.middlewares.use((req, res, next) => {
      if (req.url?.startsWith('/assets/')) {
        const set = res.setHeader.bind(res)
        res.setHeader = (k, v) => set(k, k.toLowerCase() === 'cache-control' ? 'public, max-age=31536000, immutable' : v)
        res.setHeader('Cache-Control', '')
      }
      next()
    })
  },
}

// The API runs on 8787 by default. A workstream that runs its own server sets THRESHOLD_API.
export default defineConfig({
  plugins: [react(), immutableAssets],
  worker: { format: 'es' },
  // The big libraries get chunks of their own. Left alone, the bundler puts our small shared modules (the building
  // list, the map style) in MapLibre's chunk, and then a page with no map downloads all of MapLibre to read them.
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'preload', test: /vite[\\/]preload-helper/, priority: 3 }, // else it lands in deck.gl's chunk and every lazy import pulls deck.gl
            { name: 'maplibre', test: /node_modules[\\/](\.pnpm[\\/][^\\/]+[\\/]node_modules[\\/])?maplibre-gl[\\/]/ },
            { name: 'deck', test: /node_modules[\\/](\.pnpm[\\/][^\\/]+[\\/]node_modules[\\/])?(@deck\.gl|deck\.gl|@luma\.gl|@math\.gl|@loaders\.gl|@probe\.gl|mjolnir\.js)[\\/]/ },
            { name: 'spark', test: /node_modules[\\/](\.pnpm[\\/][^\\/]+[\\/]node_modules[\\/])?@sparkjsdev[\\/]/ },
            { name: 'three', test: /node_modules[\\/](\.pnpm[\\/][^\\/]+[\\/]node_modules[\\/])?three[\\/]build[\\/]/, priority: 2 }, // above spark: a group takes its dependencies too, and three is Spark's
          ],
        },
      },
    },
  },
  // Tailnet names (linuxbox, linuxbox.<tailnet>) must be allowed or Vite answers 403.
  server: {
    allowedHosts: ['linuxbox', '.ts.net'],
    proxy: { '/api': process.env.THRESHOLD_API ?? 'http://127.0.0.1:8787' },
  },
})
