// C3 (Vela-6) — preparação do teste ao vivo do controle do PC no Tauri REAL (Windows).
// Entra na conta de QA pela tela, cria um bot com as ferramentas do computador, liga esse bot em
// Configurações → Computador (clicando no interruptor, como o usuário) e confere que o app de
// desktop se apresentou ao servidor com o bot ligado. Imprime ids e estado, sem credenciais.
// Com `--desligar <bot_id>`: desliga o bot pela mesma tela (limpeza no fim do teste).
//
// Pré-requisitos: API (8000) + Vite (5173) no ar e o app aberto com a porta de depuração do WebView2:
//   cd app/src-tauri
//   WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333 cargo run --no-default-features
// Uso: node qa/pc-tauri.mjs  (o resto do teste, que manda os comandos do bot, roda no backend)
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { QA_SENHA } from './entrar.mjs';

process.env.SORA_QA_BASE ??= 'http://localhost:5173';
const CDP = process.env.SORA_CDP ?? 'http://127.0.0.1:9333';
const API = process.env.SORA_QA_API ?? 'http://localhost:8000';
const EMAIL = process.env.SORA_QA_PC_EMAIL ?? 'qa-pc-e5@sora.local';
const NOME = process.env.SORA_QA_PC_NOME ?? 'Conta de QA'; // a barra lateral mostra o nome (o e-mail só aparece em Configurações → Conta)
const shots = join(dirname(fileURLToPath(import.meta.url)), 'shots', 'pc-tauri');
await mkdir(shots, { recursive: true });

async function api(caminho, { token, method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const r = await fetch(`${API}${caminho}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  return { status: r.status, corpo: t ? JSON.parse(t) : null };
}

async function garantirConta() {
  let r = await api('/v1/auth/entrar', { method: 'POST', body: { email: EMAIL, senha: QA_SENHA } });
  if (r.status === 401) {
    const { entrarNoContexto } = await import('./entrar.mjs');
    const navegador = await chromium.launch();
    await entrarNoContexto(await navegador.newContext(), { email: EMAIL });
    await navegador.close();
    r = await api('/v1/auth/entrar', { method: 'POST', body: { email: EMAIL, senha: QA_SENHA } });
  }
  assert.equal(r.status, 200, `login de QA na API: ${r.status}`);
  return r.corpo.token_acesso;
}

const desligar = process.argv[2] === '--desligar' ? process.argv[3] : null;
const browser = await chromium.connectOverCDP(CDP);
const main = browser.contexts().flatMap(c => c.pages()).find(p => !p.url().includes('janela=ilha'));
assert.ok(main, 'janela principal do app não encontrada pela porta de depuração');
assert.equal(await main.evaluate(() => Boolean(window.__TAURI_INTERNALS__)), true, 'main deveria rodar dentro do Tauri');

const token = await garantirConta();
// Trocar de origem depois do login perde a sessão em memória. Entre já na rota de destino.
await main.goto(`${process.env.SORA_QA_BASE}/configuracoes?secao=computador`, { waitUntil: 'domcontentloaded' });
if (!desligar) {
  await main.evaluate(() => sessionStorage.setItem('sora.onboarding-pulado.v1', '1'));
  await main.reload({ waitUntil: 'domcontentloaded' });
  await main.locator('.account-logout, input[type="password"]').first().waitFor({ state: 'attached', timeout: 20_000 });
  if (!(await main.locator('.shell-account').innerText().catch(() => '')).includes(NOME)) {
    if (await main.locator('.account-logout').count()) {
      await main.evaluate(() => document.querySelector('.account-logout')?.click());
      await main.getByLabel('E-mail').waitFor({ timeout: 10_000 });
    }
    await main.getByLabel('E-mail').fill(EMAIL);
    await main.getByLabel('Senha').fill(QA_SENHA);
    await main.getByRole('button', { name: 'Entrar', exact: true }).click();
    await main.locator('.account-logout, .shell-account').first().waitFor({ state: 'attached', timeout: 15_000 });
    await main.goto(`${process.env.SORA_QA_BASE}/configuracoes?secao=computador`, { waitUntil: 'domcontentloaded' });
  }
}

const bots = (await api('/v1/agentes', { token })).corpo;
let bot = bots.find(b => b.nome === 'Piloto do PC');
if (!bot && !desligar) {
  const criado = await api('/v1/agentes', { token, method: 'POST', body: { nome: 'Piloto do PC', funcao: 'Usa o computador', papel: 'Teste do C3', cor: '#56A8FF', ferramentas: ['computador_observar', 'computador_agir'] } });
  assert.equal(criado.status, 201, `criar bot: ${criado.status} ${JSON.stringify(criado.corpo)}`);
  bot = criado.corpo;
}
const botId = desligar ?? bot.id;

await main.getByRole('heading', { name: 'Computador' }).waitFor({ timeout: 15_000 });
const nome = bot?.nome ?? 'Piloto do PC';
const interruptor = main.getByRole('switch', { name: `${nome} pode usar este computador` });
await interruptor.waitFor({ timeout: 15_000 });
await main.getByText('Este computador está conectado à Sora.').waitFor({ timeout: 20_000 });
const querLigado = !desligar;
if ((await interruptor.isChecked()) !== querLigado) await main.locator('label.cfg-switch').filter({ has: interruptor }).click();
await main.waitForFunction(([n, v]) => {
  const el = document.querySelector(`input[aria-label="${n} pode usar este computador"]`);
  return el && el.checked === v && !el.disabled;
}, [nome, querLigado], { timeout: 10_000 });
await main.screenshot({ path: join(shots, desligar ? '99-desligado.png' : '01-ligado.png') });

const estado = (await api('/v1/computador-pc/estado', { token })).corpo;
assert.equal(estado.conectado, true, 'o app de desktop deveria estar conectado');
assert.equal(estado.autorizados.includes(botId), querLigado, `autorizados no servidor: ${JSON.stringify(estado.autorizados)}`);
const usuarioId = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString()).sub;
console.log(JSON.stringify({ bot_id: botId, usuario_id: usuarioId, estado }));
// sem browser.close(): numa conexão CDP ele fecharia o WebView2 do app
process.exit(0);
