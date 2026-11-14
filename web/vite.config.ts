import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API runs on 8787 by default. A workstream that runs its own server sets THRESHOLD_API.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': process.env.THRESHOLD_API ?? 'http://127.0.0.1:8787' } },
})
