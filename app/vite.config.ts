import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// /v1 → backend local (etapa 2). Mesma origem no navegador, então o cookie de renovação
// (httpOnly, path /v1/auth) funciona em http://localhost:5173 sem CORS.
const backend = process.env.SORA_BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/v1': { target: backend, changeOrigin: true, ws: false },
    },
  },
})
