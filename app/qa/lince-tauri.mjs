// Lince — Tauri real: conecta por CDP (porta 9333) à janela main e age. Uso: node qa/lince-tauri.mjs <entrar|estado|sair>
import { chromium } from '@playwright/test';

const acao = process.argv[2] ?? 'estado';
const EMAIL = 'qa@sora.local', SENHA = 'sora-qa-senha-123';
const browser = await chromium.connectOverCDP('http://localhost:9333');
const paginas = browser.contexts().flatMap(c => c.pages());
const main = paginas.find(p => !p.url().includes('janela=ilha'));
const respostas = [];
main.on('response', r => { if (r.url().includes('/v1/auth')) respostas.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`); });
console.log('URL main:', main.url(), '| páginas:', paginas.map(p => p.url()).join(' , '));
await main.waitForLoadState('networkidle').catch(() => {});
await main.waitForTimeout(1000);
const heading = async () => (await main.locator('h1').first().innerText().catch(() => '(sem h1)'));
const noDesktop = await main.evaluate(() => Boolean(window.__TAURI_INTERNALS__));
console.log('Tauri internals presente:', noDesktop);
console.log('Estado inicial h1:', await heading());

if (acao === 'entrar') {
  if (/Entrar na Sora/.test(await heading())) {
    await main.getByLabel('E-mail').fill(EMAIL);
    await main.getByLabel('Senha').fill(SENHA);
    await main.getByRole('button', { name: 'Entrar', exact: true }).click();
    await main.waitForFunction(() => !document.body.innerText.includes('Entrar na Sora'), null, { timeout: 15000 });
    await main.waitForTimeout(1000);
  }
  console.log('Após entrar h1:', await heading(), '| URL', main.url());
}
if (acao === 'sair') {
  const sairNoOnboarding = await main.getByRole('button', { name: 'Abrir menu da conta' }).isVisible().catch(() => false);
  console.log('Onboarding tem menu da conta/Sair?', sairNoOnboarding);
  if (!sairNoOnboarding) await main.getByRole('button', { name: /Fazer isso depois/ }).click();
  await main.waitForTimeout(800);
  await main.getByRole('button', { name: 'Abrir menu da conta' }).click();
  await main.getByRole('menuitem', { name: 'Sair' }).click();
  await main.getByRole('heading', { name: /Entrar na Sora/ }).waitFor({ timeout: 8000 });
  console.log('Sair pela UI: voltou para Entrar');
}
const arm = await main.evaluate(() => JSON.stringify({ local: Object.keys(localStorage), session: Object.keys(sessionStorage), cookie: document.cookie }));
console.log('storage:', arm);
console.log('auth:', respostas.join(' | '));
await main.screenshot({ path: `qa/shots/lince/tauri-${acao}.png` });
await browser.close();
