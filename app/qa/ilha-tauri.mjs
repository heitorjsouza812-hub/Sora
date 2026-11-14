// Etapa 5 — Ilha no Tauri REAL (Windows): a janela da ilha só aparece com a principal fora de foco ou
// minimizada e some quando o app volta ao foco; dentro do app (janela principal) nada da ilha existe.
//
// Pré-requisitos: API (8200) + Vite (5383) no ar e o app aberto com a porta de depuração do WebView2:
//   cd app/src-tauri
//   WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333 cargo run --no-default-features
// Uso: SORA_QA_BASE=http://localhost:5383 node qa/ilha-tauri.mjs
// Foco/minimizar são feitos por qa/janelas.ps1 (user32); o estado das janelas nativas também.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { QA_SENHA } from './entrar.mjs';

process.env.SORA_QA_BASE ??= 'http://localhost:5383';
const CDP = process.env.SORA_CDP ?? 'http://127.0.0.1:9333';
const qaDir = dirname(fileURLToPath(import.meta.url));
const shots = join(qaDir, 'shots', 'ilha-tauri');
await mkdir(shots, { recursive: true });

const ps = acao => execFileSync('powershell', ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', join(qaDir, 'janelas.ps1'), acao],
  { encoding: 'utf8', windowsHide: true }).trim();
const estado = () => JSON.parse(ps('estado'));
const espera = ms => new Promise(r => setTimeout(r, ms));
async function ate(descricao, predicado, ms = 6000) {
  const fim = Date.now() + ms;
  let ultimo;
  while (Date.now() < fim) {
    ultimo = estado();
    if (predicado(ultimo)) return ultimo;
    await espera(150);
  }
  assert.fail(`${descricao}: estado final ${JSON.stringify(ultimo)}`);
}

const API = process.env.SORA_QA_API ?? 'http://localhost:8200';
async function api(caminho, { token, method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const r = await fetch(`${API}${caminho}`, { method, headers, body });
  const t = await r.text();
  return { status: r.status, corpo: t ? JSON.parse(t) : null };
}
/** Cria a conta de QA (convite do CLI) se ainda não existir; devolve o token de acesso. */
async function garantirConta(email) {
  let r = await api('/v1/auth/entrar', { method: 'POST', body: JSON.stringify({ email, senha: QA_SENHA }) });
  if (r.status === 401) {
    const { entrarNoContexto } = await import('./entrar.mjs');
    const ctx = await (await chromium.launch()).newContext();
    await entrarNoContexto(ctx, { email });
    await ctx.browser().close();
    r = await api('/v1/auth/entrar', { method: 'POST', body: JSON.stringify({ email, senha: QA_SENHA }) });
  }
  assert.equal(r.status, 200, `login de QA na API: ${r.status}`);
  return r.corpo.token_acesso;
}

const browser = await chromium.connectOverCDP(CDP);
const paginas = browser.contexts().flatMap(c => c.pages());
const main = paginas.find(p => !p.url().includes('janela=ilha'));
const ilha = paginas.find(p => p.url().includes('janela=ilha'));
assert.ok(main && ilha, `esperava as janelas main + ilha; achei ${paginas.map(p => p.url()).join(', ')}`);
const erros = [];
for (const [nome, p] of [['main', main], ['ilha', ilha]]) {
  p.on('pageerror', e => erros.push(`${nome} pageerror: ${e.message}`));
  p.on('console', m => { if (m.type() === 'error') erros.push(`${nome} console: ${m.text()}`); });
}

let falha;
let tokenLimpeza;
const conversasCriadas = [];
const atencaoAntes = new Set();
try {
  assert.equal(await main.evaluate(() => Boolean(window.__TAURI_INTERNALS__)), true, 'main deveria rodar dentro do Tauri');

  // ---- entra na conta de QA pela tela (o desktop guarda a sessão no cofre do sistema; pode haver outra conta lá) ----
  // sem provedor conectado a conta cairia no onboarding: o QA o deixa "para depois"
  await main.evaluate(() => sessionStorage.setItem('sora.onboarding-pulado.v1', '1'));
  await main.reload({ waitUntil: 'domcontentloaded' });
  await main.locator('.account-logout, input[type="password"]').first().waitFor({ state: 'attached', timeout: 20_000 });
  const emailQa = process.env.SORA_QA_ILHA_EMAIL ?? 'qa-ilha-e5@sora.local';
  await garantirConta(emailQa);
  if (!(await main.locator('.shell-account').innerText().catch(() => '')).includes(emailQa)) {
    if (await main.locator('.account-logout').count()) {
      await main.evaluate(() => document.querySelector('.account-logout')?.click());
      await main.getByLabel('E-mail').waitFor({ timeout: 10_000 });
    }
    await main.getByLabel('E-mail').fill(emailQa);
    await main.getByLabel('Senha').fill(QA_SENHA);
    await main.getByRole('button', { name: 'Entrar', exact: true }).click();
    await main.locator('.account-logout').waitFor({ state: 'attached', timeout: 15_000 });
  }
  await ilha.reload({ waitUntil: 'domcontentloaded' });
  await main.evaluate(() => {
    localStorage.setItem('sora.ilha.v1', JSON.stringify({ visivel: true, som: false, esconderOciosa: false, filtro: 'todos', ocultos: [], ilhaNoApp: false }));
    window.dispatchEvent(new StorageEvent('storage', { key: 'sora.ilha.v1' }));
  });
  await ilha.evaluate(() => window.dispatchEvent(new StorageEvent('storage', { key: 'sora.ilha.v1' })));

  // ---- 1. app em foco: ilha escondida e sem nenhum nó da ilha dentro do app ----
  ps('restaurar');
  await ate('com a Sora em foco a ilha deve estar escondida', e => e.principal.foco && !e.principal.minimizada && !e.ilha.visivel);
  assert.equal(await main.locator('.ilha-ancora, .ilha, [aria-label="Ilha da Sora"]').count(), 0, 'a janela principal não pode ter nada da ilha');
  await main.screenshot({ path: join(shots, '01-app-em-foco-sem-ilha.png') });
  console.log('ok 1: app em foco → ilha escondida e nenhum nó da ilha no app');

  // ---- 2. foco em outro programa: ilha aparece ----
  ps('foco-outra');
  const fora = await ate('fora de foco a ilha deve aparecer', e => !e.principal.foco && e.ilha.visivel);
  await espera(600);
  assert.equal(estado().ilha.foco, false, 'ao aparecer, a ilha não pode roubar o foco do outro programa');
  await ilha.waitForSelector('.ilha-ancora', { timeout: 5000 });
  await ilha.screenshot({ path: join(shots, '02-fora-de-foco-ilha-visivel.png') });
  console.log('ok 2: foco em outro programa → ilha visível', JSON.stringify(fora));

  // ---- 3. volta ao app: ilha some e o painel aberto fecha (reaparece compacta) ----
  await ilha.locator('.ilha-ancora').click({ position: { x: 400, y: 20 } }).catch(() => {});
  await ilha.locator('.ilha-ancora[data-modo="expandida"]').waitFor({ timeout: 3000 }).catch(() => {});
  const abertaAntes = await ilha.locator('.ilha-ancora[data-modo="expandida"]').count();
  ps('foco-sora');
  await ate('voltando ao app a ilha deve sumir', e => e.principal.foco && !e.ilha.visivel);
  await ilha.locator('.ilha-ancora:not([data-modo="expandida"])').waitFor({ timeout: 3000 });
  console.log(`ok 3: volta ao app → ilha some e o painel fecha (estava aberto: ${abertaAntes > 0})`);

  // ---- 4. minimizar: ilha aparece; restaurar: some ----
  ps('minimizar');
  const min = await ate('minimizada a ilha deve aparecer', e => e.principal.minimizada && e.ilha.visivel && !e.ilha.foco);
  await ilha.screenshot({ path: join(shots, '03-minimizada-ilha-visivel.png') });
  console.log('ok 4a: minimizada → ilha visível', JSON.stringify(min));
  ps('restaurar');
  const voltou = e => !e.principal.minimizada && e.principal.foco && !e.ilha.visivel;
  await espera(1500);
  if (!voltou(estado())) ps('foco-sora'); // o Windows às vezes nega o foco na 1ª tentativa (limite do teste, não do app)
  await ate('restaurada a ilha deve sumir', voltou);
  // a ilha precisa CONTINUAR escondida (antes ela reaparecia com a Sora em foco depois de restaurar)
  for (let i = 0; i < 8; i++) {
    await espera(250);
    const e = estado();
    assert.ok(!e.principal.foco || !e.ilha.visivel, `restaurada e em foco, a ilha reapareceu: ${JSON.stringify(e)}`);
  }
  console.log('ok 4b: restaurada → ilha some e continua escondida');

  // ---- 4c. dados reais: um pedido "Precisa de você" (pergunta da Sora, modelo falso) aparece na ilha e é respondido por ela ----
  const token = await garantirConta(emailQa);
  const sora = (await api('/v1/agentes/sora', { token })).corpo;
  for (const p of (await api('/v1/atencao', { token })).corpo) atencaoAntes.add(p.id);
  const nova = await api('/v1/conversas', { token, method: 'POST', body: JSON.stringify({ agente_id: sora.id, texto: '[pergunta] crie uma campanha de lançamento da minha cafeteria com pesquisa, textos e calendário', anexos: [] }) });
  assert.equal(nova.status, 201, 'conversa semente');
  tokenLimpeza = token;
  conversasCriadas.push(nova.corpo.id);
  let pendentes = [];
  for (let i = 0; i < 40 && !pendentes.length; i++) { await espera(500); pendentes = (await api('/v1/atencao', { token })).corpo.filter(p => !atencaoAntes.has(p.id)); }
  assert.ok(pendentes.length > 0, 'o servidor deveria ter um pedido de atenção (pergunta)');
  ps('foco-outra');
  await ate('fora de foco a ilha aparece', e => !e.principal.foco && e.ilha.visivel);
  await ilha.getByText('Precisa de você').first().waitFor({ timeout: 15_000 }).catch(async erro => {
    console.error('diagnóstico da ilha:', JSON.stringify((await ilha.locator('body').innerText().catch(() => '(sem acesso)')).slice(0, 400)), 'pedidos no servidor:', pendentes.length);
    throw erro;
  });
  await ilha.screenshot({ path: join(shots, '04-ilha-com-pedido-real.png') });
  const antes = pendentes.map(x => x.id);
  await ilha.locator('.ilha-pendencias').getByRole('button').first().click();
  let depois = antes;
  for (let i = 0; i < 25; i++) {
    depois = (await api('/v1/atencao', { token })).corpo.map(x => x.id);
    if (antes.some(id => !depois.includes(id))) break;
    await espera(400);
  }
  assert.ok(antes.some(id => !depois.includes(id)), `responder pela ilha deveria resolver um pedido no servidor (antes ${antes.length}, depois ${depois.length})`);
  // a ilha acompanha o servidor: mesmo número de cartões que pedidos pendentes (a cadeia pode abrir outro depois da resposta)
  let esperado = depois.length;
  for (let i = 0; i < 25; i++) {
    esperado = (await api('/v1/atencao', { token })).corpo.length;
    if ((await ilha.locator('.ilha-pendencias > *').count()) === esperado) break;
    await espera(400);
  }
  assert.equal(await ilha.locator('.ilha-pendencias > *').count(), esperado, 'a ilha mostra os mesmos pedidos que o servidor');
  console.log('ok 4c: pedido real aparece na ilha, é respondido por ela e some');
  ps('foco-sora');
  await ate('em foco, ilha escondida', e => e.principal.foco && !e.ilha.visivel);

  // ---- 5. preferência "Mostrar ilha" desligada: nunca aparece, mesmo fora de foco ----
  await main.evaluate(() => {
    const p = JSON.parse(localStorage.getItem('sora.ilha.v1') ?? '{}');
    localStorage.setItem('sora.ilha.v1', JSON.stringify({ ...p, visivel: false }));
    window.dispatchEvent(new StorageEvent('storage', { key: 'sora.ilha.v1' }));
  });
  await main.reload({ waitUntil: 'domcontentloaded' });
  await main.waitForTimeout(1200);
  ps('foco-outra');
  await espera(1800);
  assert.equal(estado().ilha.visivel, false, 'com "Mostrar ilha" desligado a ilha não pode aparecer');
  console.log('ok 5: preferência desligada → ilha não aparece mesmo fora de foco');
  await main.evaluate(() => {
    const p = JSON.parse(localStorage.getItem('sora.ilha.v1') ?? '{}');
    localStorage.setItem('sora.ilha.v1', JSON.stringify({ ...p, visivel: true }));
  });
  await main.reload({ waitUntil: 'domcontentloaded' });
  await ate('religada e fora de foco a ilha volta', e => !e.principal.foco && e.ilha.visivel);
  console.log('ok 5b: preferência religada → ilha volta');
  ps('foco-sora');
  await ate('fim: em foco, ilha escondida', e => e.principal.foco && !e.ilha.visivel);

  const relevantes = erros.filter(e => !/Failed to load resource|favicon/i.test(e));
  assert.deepEqual(relevantes, [], `console limpo:\n${relevantes.join('\n')}`);
} catch (erro) {
  falha = erro;
  try { await main.screenshot({ path: join(shots, 'FALHA-main.png') }); } catch { /* */ }
} finally {
  // fecha os pedidos que o teste abriu (apagar a conversa não os resolve) e apaga a conversa semente
  // com os especialistas que ela criou (senão a conta de QA acumula bots e cartões)
  if (tokenLimpeza) {
    const sobras = ((await api('/v1/atencao', { token: tokenLimpeza }).catch(() => ({ corpo: [] }))).corpo ?? []).filter(p => !atencaoAntes.has(p.id));
    for (const p of sobras) {
      const [caminho, corpo] = p.tipo === 'pergunta'
        ? [`/v1/perguntas/${p.id}/responder`, { valor: p.opcoes?.[0]?.valor ?? 'cancelar' }]
        : [`/v1/aprovacoes/${p.id}/decidir`, { decisao: 'negar' }];
      await api(caminho, { token: tokenLimpeza, method: 'POST', body: JSON.stringify(corpo) }).catch(() => {});
    }
  }
  for (const id of conversasCriadas) {
    const r = await api(`/v1/conversas/${id}`, { token: tokenLimpeza, method: 'DELETE' }).catch(() => ({ status: 0 }));
    if (r.status !== 204) console.error(`aviso: não consegui apagar a conversa de QA ${id} (${r.status})`);
  }
  await browser.close();
}
if (falha) { console.error(`FALHA Ilha no Tauri real: ${falha.stack ?? falha.message}`); process.exitCode = 1; }
else console.log('Ilha no Tauri real aprovada (conta de QA:', process.env.SORA_QA_ILHA_EMAIL ?? 'qa-ilha-e5@sora.local', ')');
