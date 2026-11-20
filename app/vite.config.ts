import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Versão do app: uma fonte só (a do instalador do desktop), usada no "Relatar problema".
const versao = (JSON.parse(readFileSync(new URL('./src-tauri/tauri.conf.json', import.meta.url), 'utf-8')) as { version: string }).version

// https://vite.dev/config/
// /v1 → backend local. Mesma origem no navegador, então o cookie de renovação (httpOnly, path
// /v1/auth) funciona sem CORS. Padrão: API 8000, Vite 5173. Uma worktree paralela troca por
// SORA_BACKEND_URL e PORT, sem editar arquivos.
const backend = process.env.SORA_BACKEND_URL ?? 'http://localhost:8000'
const porta = Number(process.env.PORT ?? 5173)

export default defineConfig({
  plugins: [react()],
  define: { 'import.meta.env.VITE_SORA_VERSAO': JSON.stringify(versao) },
  server: {
    port: porta,
    proxy: {
      '/v1': { target: backend, changeOrigin: true, ws: false },
    },
  },
})
