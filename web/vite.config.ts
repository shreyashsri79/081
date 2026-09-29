import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: {
    port: 5181,
    // blend/server.py (FastAPI, C11) owns /api. Until it exists the app falls
    // back to the synthetic source in src/lib/synthetic.ts and says so.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8081', changeOrigin: true },
    },
  },
})
