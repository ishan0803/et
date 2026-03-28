import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

/**
 * Custom Vite plugin to dynamically scan et_frames at build time.
 * Generates a virtual module `virtual:frame-list` that exports an array
 * of frame URLs sorted numerically.
 */
function frameListPlugin() {
  const virtualId = 'virtual:frame-list'
  const resolvedId = '\0' + virtualId

  return {
    name: 'frame-list',
    resolveId(id) {
      if (id === virtualId) return resolvedId
    },
    load(id) {
      if (id === resolvedId) {
        const dir = path.resolve(process.cwd(), 'public/et_frames')
        try {
          const files = fs.readdirSync(dir)
            .filter(f => /^frame_\d+.*\.gif$/.test(f))
            .sort((a, b) => {
              const na = parseInt(a.match(/frame_(\d+)/)[1])
              const nb = parseInt(b.match(/frame_(\d+)/)[1])
              return na - nb
            })
          const urls = files.map(f => `/et_frames/${f}`)
          return `export default ${JSON.stringify(urls)};`
        } catch {
          // Fallback if et_frames directory doesn't exist
          return `export default [];`
        }
      }
    }
  }
}

export default defineConfig({
  plugins: [react(), frameListPlugin()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/output': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
