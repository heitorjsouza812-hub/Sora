// Teste real do desktop (Tauri v2, Windows) — LOGIN. Roda contra o app aberto com a porta de depuração:
//   cd app/src-tauri
//   WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333 cargo run --no-default-features
// Fase "entrar" (padrão): sai da conta atual, confere a tela Entrar, a mensagem de senha errada, a de
//   servidor fora (a rota do login é derrubada só dentro da página, a API nunca é tocada) e entra com a
//   conta de QA; confere que o login foi para o cofre do Windows (Credential Manager).
// Fase "reabrir": depois de fechar e abrir o app de novo, confere que a sessão voltou SEM digitar senha.
// Uso: SORA_QA_DESK_EMAIL=... node qa/desktop-real-login.mjs [entrar|reabrir]
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { QA_SENHA } from './entrar.mjs';

const CDP = process.env.SORA_CDP ?? 'http://127.0.0.1:9333';
const BASE = process.env.SORA_QA_BASE ?? 'http://localhost:5173';
const EMAIL = process.env.SORA_QA_DESK_EMAIL ?? 'qa-desktop-real@sora.local';
const fase = process.argv[2] ?? 'entrar';
const shots = join(dirname(fileURLToPath(import.meta.url)), 'shots', 'desktop-real');
await mkdir(shots, { recursive: true });

const browser = await chromium.connectOverCDP(CDP);
const main = browser.contexts().flatMap(c => c.pages()).find(p => !p.url().includes('janela=ilha'));
assert.ok(main, 'janela principal não encontrada pela porta de depuração');
assert.equal(await main.evaluate(() => Boolean(window.__TAURI_INTERNALS__)), true, 'main deveria rodar dentro do Tauri');
const erros = [];
main.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
main.on('console', m => { if (m.type() === 'error') erros.push(`console: ${m.text()}`); });

const cofre = () => {
  try { return execFileSync('cmdkey', ['/list'], { encoding: 'utf8' }).split(/\r?\n/).filter(l => /sora/i.test(l)).map(l => l.trim()); } catch { return []; }
};
const logado = () => main.locator('.shell-account').innerText({ timeout: 20_000 }).catch(() => '');

if (fase === 'reabrir') {
  // o app acabou de abrir: nada de digitar. Espera a sessão voltar sozinha pelo cofre.
  await main.waitForLoadState('domcontentloaded');
  await main.locator('.shell-account, input[type="password"], h1, h2').first().waitFor({ state: 'attached', timeout: 25_000 });
  await main.waitForTimeout(2500);
  // sem provedor a conta cai no onboarding ("QA, conecte sua primeira API"); com provedor, na barra lateral
  const tela = (await main.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 160);
  const conta = (await logado()) || tela;
  await main.screenshot({ path: join(shots, '04-reaberto.png') });
  // o onboarding tem um campo de chave de API (type=password); a tela de login é a que tem o campo E-mail
  assert.equal(await main.getByLabel('E-mail').count(), 0, `a tela pediu e-mail e senha de novo: ${tela}`);
  assert.ok(/QA/.test(conta) || conta.includes(EMAIL), `a sessão deveria voltar pelo cofre; tela: ${JSON.stringify(tela)}`);
  console.log('OK reabrir: sessão voltou pelo cofre do Windows sem digitar senha. Conta:', JSON.stringify(conta));
  console.log('cofre:', JSON.stringify(cofre()));
  const relev = erros.filter(e => !/Failed to load resource|favicon/i.test(e));
  console.log('erros de console:', relev.length ? relev : 'nenhum');
  process.exit(0);
}

// ---- 1. sair da conta que estiver aberta e chegar na tela Entrar ----
await main.evaluate(() => sessionStorage.setItem('sora.onboarding-pulado.v1', '1'));
await main.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
await main.locator('.shell-account, input[type="password"]').first().waitFor({ state: 'attached', timeout: 25_000 });
if (await main.locator('.account-logout').count()) {
  await main.evaluate(() => document.querySelector('.account-logout')?.click());
}
await main.getByLabel('E-mail').waitFor({ timeout: 15_000 });
await main.screenshot({ path: join(shots, '01-entrar.png') });
console.log('OK 1: tela Entrar visível depois de sair. Cofre:', JSON.stringify(cofre()));

// ---- 2. senha errada ----
await main.getByLabel('E-mail').fill(EMAIL);
await main.getByLabel('Senha').fill('senha-errada-123');
await main.getByRole('button', { name: 'Entrar', exact: true }).click();
const alerta = main.locator('.sessao-erro');
await alerta.waitFor({ timeout: 10_000 });
const msgSenha = (await alerta.innerText()).trim();
await main.screenshot({ path: join(shots, '02-senha-errada.png') });
console.log('OK 2a: senha errada →', JSON.stringify(msgSenha));
assert.ok(!/server|500|undefined|\[object/i.test(msgSenha), `mensagem de senha errada confusa: ${msgSenha}`);

// ---- 3. servidor fora (só dentro desta página) e erro 500 ----
await main.route('**/v1/auth/entrar', r => r.abort('connectionrefused'));
await main.getByRole('button', { name: 'Entrar', exact: true }).click();
await main.waitForFunction(() => document.querySelector('.sessao-erro')?.textContent && !/senha|incorret|inválid/i.test(document.querySelector('.sessao-erro').textContent), null, { timeout: 10_000 });
const msgFora = (await alerta.innerText()).trim();
await main.screenshot({ path: join(shots, '03a-servidor-fora.png') });
console.log('OK 2b: servidor fora →', JSON.stringify(msgFora));
await main.unroute('**/v1/auth/entrar');
await main.route('**/v1/auth/entrar', r => r.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Internal Server Error"}' }));
await main.getByRole('button', { name: 'Entrar', exact: true }).click();
await main.waitForFunction(msg => document.querySelector('.sessao-erro')?.textContent?.trim() !== msg, msgFora, { timeout: 10_000 });
const msg500 = (await alerta.innerText()).trim();
await main.screenshot({ path: join(shots, '03b-erro-500.png') });
console.log('OK 2c: erro 500 →', JSON.stringify(msg500));
await main.unroute('**/v1/auth/entrar');

// ---- 4. entra de verdade ----
await main.getByLabel('Senha').fill(QA_SENHA);
const resp = main.waitForResponse(r => r.url().includes('/v1/auth/entrar'), { timeout: 15_000 });
await main.getByRole('button', { name: 'Entrar', exact: true }).click();
const r = await resp;
console.log('login real → HTTP', r.status());
assert.equal(r.status(), 200, 'login real deveria dar 200');
await main.locator('.account-logout').waitFor({ state: 'attached', timeout: 15_000 });
await main.screenshot({ path: join(shots, '04-logado.png') });
const conta = await logado();
const avisoCofre = await main.getByText(/lembrar o login neste computador/i).count();
console.log('OK 3: logado. Conta:', JSON.stringify(conta), '| aviso de cofre falho:', avisoCofre ? 'SIM' : 'não');
console.log('cofre:', JSON.stringify(cofre()));
const relev = erros.filter(e => !/Failed to load resource|favicon/i.test(e));
console.log('erros de console:', relev.length ? relev : 'nenhum');
process.exit(0);
