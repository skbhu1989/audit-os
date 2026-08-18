import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev server proxies /api to the FastAPI backend so the browser never needs
// CORS config during local development — set VITE_API_BASE at build time
// for a production deployment where frontend and backend are on different
// origins (see src/api/client.js).
//
// VITE_BASE_PATH matters specifically for GitHub Pages project sites, which
// serve from https://<user>.github.io/<repo>/ rather than the domain root —
// every asset path needs that /<repo>/ prefix or the deployed build 404s on
// its own JS/CSS. Defaults to '/' so nothing changes for any other
// deployment target (Render static site, a custom domain, local dev).
export default defineConfig({
  base: process.env.VITE_BASE_PATH || '/',
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
