// Vela-12: aceitação ao vivo do controle do PC (C3) com modelo real, no app de desktop de verdade.
// O "usuário" é este script: pede pelo chat do bot NA JANELA DA SORA (como o Heitor faz), decide os
// cartões "Precisa de você" pela API (Permitir uma vez) e espera o bot terminar. Mede o tempo total.
// Pré-requisitos: app de desktop com a porta 9333 logado na conta de QA, bot "Piloto do PC" ligado
// em Configurações → Computador, API e worker com o código atual.
// Uso: node qa/pc-excel-live.mjs ["pedido"]   (SORA_QA_API, SORA_QA_DESK_EMAIL, SORA_QA_BOT)
// Pausa: SORA_QA_PAUSAR=1 chama /pausar (como a ponte, quando o usuário mexe no mouse) assim que o bot
// pega o PC, e só decide o cartão "Retomar?" depois de SORA_QA_DECIDIR_APOS_S (padrão 15 s): o turno
// precisa pausar de verdade e voltar pelo "Permitir".
import { execFileSync } from 'node:child_process';
import { writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { QA_SENHA } from './entrar.mjs';

const API = process.env.SORA_QA_API ?? 'http://localhost:8200';
const EMAIL = process.env.SORA_QA_DESK_EMAIL ?? 'qa-desktop-real@sora.local';
const CDP = process.env.SORA_CDP ?? 'http://127.0.0.1:9333';
const PRAZO_MS = Number(process.env.SORA_QA_PRAZO_MS ?? 8 * 60_000);
const PEDIDO = process.argv[2] ?? 'Abra o Excel no meu computador, crie uma planilha nova e preencha uma tabela pequena com 3 colunas (Produto, Quantidade, Preço) e 3 produtos. Confira na tela e me diga quando terminar.';
const espera = ms => new Promise(r => setTimeout(r, ms));
const saida = join(dirname(fileURLToPath(import.meta.url)), 'shots', 'pc-excel-live.json');

async function api(caminho, { token, method = 'GET', body } = {}) {
  const r = await fetch(`${API}${caminho}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  let corpo = null;
  try { corpo = t ? JSON.parse(t) : null; } catch { corpo = t; }
  return { status: r.status, corpo };
}
const token = (await api('/v1/auth/entrar', { method: 'POST', body: { email: EMAIL, senha: QA_SENHA } })).corpo.token_acesso;
const usuario = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString()).sub;
const bots = (await api('/v1/agentes', { token })).corpo;
const bot = process.env.SORA_QA_BOT ?? bots.find(b => b.nome === 'Piloto do PC')?.id;
if (!bot) throw new Error('bot "Piloto do PC" não encontrado');

const browser = await chromium.connectOverCDP(CDP);
const main = browser.contexts().flatMap(c => c.pages()).find(p => !p.url().includes('janela=ilha'));
await main.goto(`${new URL(main.url()).origin}/bots/${bot}`, { waitUntil: 'domcontentloaded' });
const campo = main.locator('textarea').last();
await campo.waitFor({ timeout: 20_000 });
await main.bringToFront();

const linha = [];
const anota = texto => { const t = ((Date.now() - inicio) / 1000).toFixed(1); linha.push(`${t}s ${texto}`); console.log(`${t}s ${texto}`); };
const SO_ACOMPANHAR = process.env.SORA_QA_SO_ACOMPANHAR === '1';
const inicio = Date.now() - (SO_ACOMPANHAR ? Number(process.env.SORA_QA_DESDE_S ?? 60) * 1000 : 0);
if (!SO_ACOMPANHAR) {
  await campo.fill(PEDIDO);
  await campo.press('Enter');
  anota('pedido enviado pelo chat da Sora');
}
let viuVez = false;

const PAUSAR = process.env.SORA_QA_PAUSAR === '1';
const DECIDIR_APOS_MS = Number(process.env.SORA_QA_DECIDIR_APOS_S ?? 15) * 1000;
let pausou = false;
let ultimaDecisao = 0;
const vistos = new Map();
const decididos = new Set();
let ultimaMensagem = null;
let parado = 0;
while (Date.now() - inicio < PRAZO_MS) {
  await espera(1000);
  const atencao = (await api('/v1/atencao', { token })).corpo ?? [];
  for (const p of atencao) {
    if (decididos.has(p.id) || p.agente_id !== bot) continue;
    if (!vistos.has(p.id)) { vistos.set(p.id, Date.now()); anota(`cartão: ${p.titulo} — ${(p.resumo ?? '').slice(0, 90)}`); }
    if (PAUSAR && /Retomar/.test(p.titulo ?? '') && Date.now() - vistos.get(p.id) < DECIDIR_APOS_MS) continue;
    decididos.add(p.id);
    const r = await api(`/v1/aprovacoes/${p.id}/decidir`, { method: 'POST', token, body: { decisao: 'permitir_uma_vez' } });
    ultimaDecisao = Date.now();
    anota(`  Permitir uma vez → HTTP ${r.status}${r.status !== 204 ? ' ' + JSON.stringify(r.corpo).slice(0, 160) : ''}`);
  }
  const conversas = (await api(`/v1/conversas?agente_id=${bot}`, { token })).corpo ?? [];
  const conversa = Array.isArray(conversas) ? conversas.find(c => c.agente_id === bot) ?? conversas[0] : null;
  if (!conversa) continue;
  const mensagens = (await api(`/v1/conversas/${conversa.id}/mensagens`, { token })).corpo ?? [];
  const lista = Array.isArray(mensagens) ? mensagens : mensagens.itens ?? [];
  const minhas = lista.filter(m => m.autor !== 'usuario' && new Date(m.criada_em).getTime() >= inicio - 2000).sort((a, b) => new Date(a.criada_em) - new Date(b.criada_em));
  const ultima = minhas.at(-1);
  if (ultima && ultima.id !== ultimaMensagem) {
    ultimaMensagem = ultima.id;
    anota(`bot: ${String(ultima.conteudo).replace(/\s+/g, ' ').slice(0, 220)}`);
  }
  const estado = (await api('/v1/computador-pc/estado', { token })).corpo;
  const trabalhando = estado?.vez?.agente_id === bot;
  if (trabalhando && !viuVez) { viuVez = true; anota('o bot pegou o PC'); }
  if (PAUSAR && !pausou && trabalhando) {
    pausou = true;
    const bruto = execFileSync('docker', ['exec', 'sora-e5-redis', 'redis-cli', 'get', `pc:sessao:${usuario}`], { encoding: 'utf8' }).trim();
    const sessaoId = JSON.parse(bruto).sessao_id;
    const r = await fetch(`${API}/v1/computador-pc/pausar`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, 'X-Sora-Cliente': 'desktop' }, body: JSON.stringify({ sessao_id: sessaoId, agente_id: bot }) });
    anota(`usuário "mexeu no mouse": /pausar → HTTP ${r.status}`);
  }
  const pendentes = [...vistos.keys()].filter(id => !decididos.has(id)).length;
  const recente = Date.now() - ultimaDecisao < 30_000; // a retomada leva um tempo para começar
  parado = viuVez && ultima && !trabalhando && !pendentes && !recente ? parado + 1 : 0;
  if (parado >= 12) break; // 12 s sem a vez do PC, sem cartão e com resposta: o turno acabou
}
const total = ((Date.now() - inicio) / 1000).toFixed(1);
anota(`fim: ${total}s`);
await writeFile(saida, JSON.stringify({ pedido: PEDIDO, total_s: Number(total), inicio: new Date(inicio).toISOString(), linha }, null, 2));
console.log('INICIO_ISO', new Date(inicio).toISOString());
process.exit(0);
