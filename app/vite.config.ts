import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// /v1 → backend local. Mesma origem no navegador, então o cookie de renovação (httpOnly, path
// /v1/auth) funciona sem CORS. Etapa 5 (log/etapa5-interface.md): API 8200, Vite 5383 — dá para
// sobrepor com SORA_BACKEND_URL/PORT se precisar rodar outra etapa ao mesmo tempo.
const backend = process.env.SORA_BACKEND_URL ?? 'http://localhost:8200'
const porta = Number(process.env.PORT ?? 5383)

export default defineConfig({
  plugins: [react()],
  server: {
    port: porta,
    proxy: {
      '/v1': { target: backend, changeOrigin: true, ws: false },
    },
  },
})
