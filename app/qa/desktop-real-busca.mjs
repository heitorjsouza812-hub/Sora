// Busca real (Tavily) pelo app de desktop: pede à Sora uma pergunta que exige busca, espera a resposta pela API
// e confere as fontes em chips na tela (no Tauri real). Conta de QA do desktop real; apaga a conversa no fim.
// Uso: SORA_QA_API=http://localhost:8200 node qa/desktop-real-busca.mjs
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { QA_SENHA } from './entrar.mjs';

const API = process.env.SORA_QA_API ?? 'http://localhost:8200';
const EMAIL = process.env.SORA_QA_DESK_EMAIL ?? 'qa-desktop-real@sora.local';
const shots = join(dirname(fileURLToPath(import.meta.url)), 'shots', 'desktop-real');
await mkdir(shots, { recursive: true });
const espera = ms => new Promise(r => setTimeout(r, ms));
async function api(caminho, { token, method = 'GET', body } = {}) {
  const r = await fetch(`${API}${caminho}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  return { status: r.status, corpo: t ? JSON.parse(t) : null };
}
const e = await api('/v1/auth/entrar', { method: 'POST', body: { email: EMAIL, senha: QA_SENHA } });
const token = e.corpo.token_acesso;
const sora = (await api('/v1/agentes/sora', { token })).corpo;
const pergunta = process.env.SORA_QA_PERGUNTA ?? 'Pesquise na web e me diga: qual foi o resultado do último jogo da seleção brasileira de futebol masculina? Cite as fontes.';
const nova = await api('/v1/conversas', { token, method: 'POST', body: { agente_id: sora.id, texto: pergunta, anexos: [] } });
assert.equal(nova.status, 201, `criar conversa: ${nova.status} ${JSON.stringify(nova.corpo)}`);
const id = nova.corpo.id;
console.log('conversa', id);
let msgs = [];
let final = null;
try {
  for (let i = 0; i < 90; i++) {
    await espera(2000);
    msgs = (await api(`/v1/conversas/${id}/mensagens`, { token })).corpo ?? [];
    const lista = Array.isArray(msgs) ? msgs : msgs.mensagens ?? [];
    final = lista.filter(m => m.autor === 'sora' || m.papel === 'assistente').at(-1);
    const pendentes = (await api('/v1/atencao', { token })).corpo.filter(p => p.tipo);
    if (pendentes.length) { console.log('pedido pendente:', pendentes.map(p => p.titulo).join(' | ')); }
    if (final && (final.texto ?? final.conteudo ?? '').length > 40) break;
  }
  const corpo = final ? (final.texto ?? final.conteudo ?? '') : '(sem resposta)';
  console.log('resposta (início):', JSON.stringify(corpo.slice(0, 500)));
  console.log('campos da mensagem:', final ? Object.keys(final).join(',') : '-');
  console.log('fontes na API:', JSON.stringify(final?.fontes ?? final?.metadados?.fontes ?? null)?.slice(0, 600));
  // na tela do app de desktop
  const browser = await chromium.connectOverCDP(process.env.SORA_CDP ?? 'http://127.0.0.1:9333');
  const main = browser.contexts().flatMap(c => c.pages()).find(p => !p.url().includes('janela=ilha'));
  await main.goto(`${process.env.SORA_QA_BASE ?? 'http://localhost:5173'}/`, { waitUntil: 'domcontentloaded' });
  await main.getByText(pergunta.slice(0, 30)).first().waitFor({ timeout: 20_000 }).catch(() => {});
  const ab = main.getByText(pergunta.slice(0, 30)).first(); await ab.click().catch(() => {}); await main.locator('nav.msg-fontes').first().waitFor({ timeout: 8000 }).catch(() => {});
  await espera(2500);
  await main.screenshot({ path: join(shots, '40-busca-tavily.png') });
  const chips = await main.locator('nav.msg-fontes a').evaluateAll(els => els.map(e => ({ t: e.textContent?.trim(), h: e.getAttribute('href') }))).catch(() => []);
  console.log('chips de fonte na tela:', JSON.stringify(chips).slice(0, 800));
} finally {
  const r = await api(`/v1/conversas/${id}`, { token, method: 'DELETE' }).catch(() => ({ status: 0 }));
  console.log('conversa de QA apagada →', r.status);
}
process.exit(0);
